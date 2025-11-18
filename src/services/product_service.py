import fdb  
import logging
from ..database import get_db_connection
from . import groups_service, stock_service
from ..utils.image_handler import get_product_image_url
from decimal import Decimal
from datetime import datetime, timedelta
# ALTERAÇÃO: Removido import não utilizado lru_cache

# ALTERAÇÃO: Logger definido no topo do módulo para uso em todas as funções
logger = logging.getLogger(__name__)  

def create_product(product_data):  
    name = product_data.get('name')  
    description = product_data.get('description')  
    price = product_data.get('price')  
    cost_price = product_data.get('cost_price', 0.0)  
    preparation_time_minutes = product_data.get('preparation_time_minutes', 0)  
    category_id = product_data.get('category_id')  
    ingredients = product_data.get('ingredients') or []
    if not name or not name.strip():  
        return (None, "INVALID_NAME", "Nome do produto é obrigatório")  
    if price is None or price <= 0:  
        return (None, "INVALID_PRICE", "Preço deve ser maior que zero")  
    if cost_price is not None and cost_price < 0:  
        return (None, "INVALID_COST_PRICE", "Preço de custo não pode ser negativo")  
    if preparation_time_minutes is not None and preparation_time_minutes < 0:  
        return (None, "INVALID_PREP_TIME", "Tempo de preparo não pode ser negativo")  
    if category_id is None:  
        return (None, "INVALID_CATEGORY", "Categoria é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # valida categoria existente e ativa  
        cur.execute("SELECT 1 FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))  
        if not cur.fetchone():  
            return (None, "CATEGORY_NOT_FOUND", "Categoria informada não existe ou está inativa")  
        sql_check = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND IS_ACTIVE = TRUE;"  
        cur.execute(sql_check, (name,))  
        if cur.fetchone():  
            return (None, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")  
        sql = "INSERT INTO PRODUCTS (NAME, DESCRIPTION, PRICE, COST_PRICE, PREPARATION_TIME_MINUTES, CATEGORY_ID, IMAGE_URL) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING ID;"  
        cur.execute(sql, (name, description, price, cost_price, preparation_time_minutes, category_id, None))  
        new_product_id = cur.fetchone()[0]  

        # Insere ingredientes, se fornecidos
        if ingredients:
            for item in ingredients:
                ingredient_id = item.get('ingredient_id')
                portions = item.get('portions', 0)
                min_quantity = item.get('min_quantity', 0)
                max_quantity = item.get('max_quantity', 0)

                if not ingredient_id and ingredient_id != 0:
                    raise ValueError("ingredient_id é obrigatório nos ingredientes")
                if portions is None or portions < 0:
                    raise ValueError("portions deve ser >= 0")
                if min_quantity is None or min_quantity < 0:
                    raise ValueError("min_quantity deve ser >= 0")
                if max_quantity is None or max_quantity < 0:
                    raise ValueError("max_quantity deve ser >= 0")
                if max_quantity and min_quantity and max_quantity < min_quantity:
                    raise ValueError("max_quantity não pode ser menor que min_quantity")

                # valida existência do ingrediente
                cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ingredient_id,))
                if not cur.fetchone():
                    raise ValueError(f"Ingrediente {ingredient_id} não encontrado")

                cur.execute(
                    """
                    INSERT INTO PRODUCT_INGREDIENTS (PRODUCT_ID, INGREDIENT_ID, PORTIONS, MIN_QUANTITY, MAX_QUANTITY)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (new_product_id, ingredient_id, portions, min_quantity, max_quantity)
                )
        
        # ALTERAÇÃO: Valida receita completa antes de commitar
        # Verifica se produto tem pelo menos um ingrediente obrigatório (PORTIONS > 0)
        cur.execute("""
            SELECT COUNT(*) FROM PRODUCT_INGREDIENTS
            WHERE PRODUCT_ID = ? AND PORTIONS > 0
        """, (new_product_id,))
        required_ingredients_count = cur.fetchone()[0] or 0
        
        if required_ingredients_count == 0:
            conn.rollback()
            return (None, "INCOMPLETE_RECIPE", "Produto deve ter pelo menos um ingrediente obrigatório (PORTIONS > 0) na receita")

        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após criar produto
        _invalidate_product_cache()
        
        return ({"id": new_product_id, "name": name, "description": description, "price": price, "cost_price": cost_price, "preparation_time_minutes": preparation_time_minutes, "category_id": category_id}, None, None)  
    except fdb.Error as e:  
        # ALTERAÇÃO: Logger já está definido no topo do módulo, não precisa redefinir
        logger.error(f"Erro ao criar produto: {e}", exc_info=True)
        if conn: conn.rollback()  
        return (None, "DATABASE_ERROR", "Erro interno do servidor")  
    except ValueError as ve:
        if conn: conn.rollback()
        return (None, "INVALID_INGREDIENTS", str(ve))
    finally:  
        if conn: conn.close()  


def _get_image_hash(image_url):
    """Gera hash da imagem baseado no arquivo"""
    if not image_url:
        return None
    try:
        import os
        import hashlib
        upload_dir = os.path.join(os.getcwd(), 'uploads', 'products')
        filename = os.path.basename(image_url)
        file_path = os.path.join(upload_dir, filename)
        if os.path.exists(file_path):
            # Gera hash baseado no conteúdo e data de modificação
            file_mtime = os.path.getmtime(file_path)
            file_size = os.path.getsize(file_path)
            hash_input = f"{filename}_{file_mtime}_{file_size}"
            return hashlib.md5(hash_input.encode()).hexdigest()[:8]
    except Exception as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.warning(f"Erro ao gerar hash da imagem: {e}", exc_info=True)
    return None

def _get_product_availability_status(product_id, cur, for_listing=False):
    """
    Verifica o status de disponibilidade do produto baseado na capacidade de produção.
    
    NOVO: Usa cálculo de capacidade ao invés de apenas verificar estoque.
    Produto disponível se capacidade >= 1.
    
    Args:
        product_id: ID do produto
        cur: Cursor do banco
        for_listing: Se True, usa estoque físico (sem reservas temporárias) para listagem.
                     Se False, usa estoque disponível (com reservas temporárias) para validação.
    """
    try:
        from . import stock_service
        
        # CORREÇÃO: Para listagem, calcula capacidade sem reservas temporárias
        # Para validação, calcula capacidade com reservas temporárias
        capacity_info = stock_service.calculate_product_capacity(product_id, cur=cur, include_extras=False, for_listing=for_listing)
        
        capacity = capacity_info.get('capacity', 0)
        is_available = capacity_info.get('is_available', False)
        
        if not is_available or capacity < 1:
            return "unavailable"
        elif capacity == 1:
            # Capacidade = 1: disponível mas limitado (travar aumento de quantidade)
            return "limited"
        else:
            # Capacidade > 1: disponível
            # Verifica se algum ingrediente está com estoque baixo
            limiting_ingredient = capacity_info.get('limiting_ingredient')
            if limiting_ingredient:
                # Se o insumo limitante tem estoque baixo, marca como low_stock
                available_stock = limiting_ingredient.get('available_stock', 0)
                consumption_per_unit = limiting_ingredient.get('consumption_per_unit', 0)
                
                # Se o estoque disponível é menos que 2x o consumo por unidade, está baixo
                if available_stock < (consumption_per_unit * 2):
                    return "low_stock"
            
            return "available"
            
    except Exception as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao verificar disponibilidade do produto {product_id}: {e}", exc_info=True)
        return "unknown"


def _batch_get_product_availability_status(product_ids, cur, for_listing=False):
    """
    OTIMIZAÇÃO: Calcula status de disponibilidade para múltiplos produtos de uma vez.
    Evita N+1 queries ao buscar ingredientes, estoque e calcular capacidade em batch.
    
    Args:
        product_ids: Lista de IDs de produtos
        cur: Cursor do banco
        for_listing: Se True, usa estoque físico (sem reservas temporárias) para listagem.
                     Se False, usa estoque disponível (com reservas temporárias) para validação.
    
    Returns:
        dict: {
            product_id: {
                'status': str,  # "available", "limited", "unavailable", "low_stock"
                'capacity': int,
                'is_available': bool,
                'limiting_ingredient': dict ou None
            }
        }
    """
    if not product_ids:
        logger.warning("[PRODUCT_SERVICE] _batch_get_product_availability_status chamado sem product_ids")
        return {}
    
    try:
        from . import stock_service
        # ALTERAÇÃO: Decimal já está importado no topo do módulo
        
        result = {}
        
        # LOG: Iniciando busca de ingredientes
        logger.info(f"[PRODUCT_SERVICE] _batch_get_product_availability_status: buscando ingredientes para {len(product_ids)} produtos")
        
        # Verifica se campo LOSS_PERCENTAGE existe antes de usar
        use_loss_percentage = False
        try:
            # Tenta buscar coluna LOSS_PERCENTAGE (pode não existir em versões antigas do schema)
            placeholders = ', '.join(['?' for _ in product_ids])
            cur.execute(f"""
                SELECT 
                    pi.PRODUCT_ID,
                    pi.INGREDIENT_ID,
                    pi.PORTIONS,
                    COALESCE(pi.LOSS_PERCENTAGE, 0) as LOSS_PERCENTAGE,
                    i.NAME,
                    i.BASE_PORTION_QUANTITY,
                    i.BASE_PORTION_UNIT,
                    i.STOCK_UNIT,
                    i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                WHERE pi.PRODUCT_ID IN ({placeholders})
                  AND pi.PORTIONS > 0
                  AND i.IS_AVAILABLE = TRUE
            """, tuple(product_ids))
            use_loss_percentage = True
            logger.debug(f"[PRODUCT_SERVICE] Query com LOSS_PERCENTAGE executada com sucesso")
        except fdb.Error as e:
            # Se campo não existe, usa query sem LOSS_PERCENTAGE
            error_msg = str(e).lower()
            if 'loss_percentage' in error_msg or 'unknown' in error_msg or 'column' in error_msg:
                logger.debug(f"[PRODUCT_SERVICE] Campo LOSS_PERCENTAGE não encontrado, usando query sem perdas para produtos em batch")
                placeholders = ', '.join(['?' for _ in product_ids])
                cur.execute(f"""
                    SELECT 
                        pi.PRODUCT_ID,
                        pi.INGREDIENT_ID,
                        pi.PORTIONS,
                        i.NAME,
                        i.BASE_PORTION_QUANTITY,
                        i.BASE_PORTION_UNIT,
                        i.STOCK_UNIT,
                        i.IS_AVAILABLE
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID IN ({placeholders})
                      AND pi.PORTIONS > 0
                      AND i.IS_AVAILABLE = TRUE
                """, tuple(product_ids))
                use_loss_percentage = False
            else:
                logger.error(f"[PRODUCT_SERVICE] Erro inesperado ao buscar ingredientes em batch: {e}", exc_info=True)
                # Se erro não relacionado a coluna, retorna status unknown para todos
                return {pid: {'status': 'unknown', 'capacity': 0, 'is_available': False, 'limiting_ingredient': None} 
                        for pid in product_ids}
        
        # Agrupa ingredientes por produto
        product_ingredients = {}
        ingredient_rows = cur.fetchall()
        logger.info(f"[PRODUCT_SERVICE] 🔍 Busca de ingredientes: {len(ingredient_rows)} ingredientes encontrados para {len(product_ids)} produtos")
        
        if len(ingredient_rows) == 0:
            logger.error(f"[PRODUCT_SERVICE] ❌ CRÍTICO: Nenhum ingrediente encontrado para os produtos! "
                         f"Verificar se há produtos com PORTIONS > 0 e ingredientes IS_AVAILABLE = TRUE")
            # LOG: Verificar se há produtos sem ingredientes
            placeholders_check = ', '.join(['?' for _ in product_ids])
            cur.execute(f"""
                SELECT p.ID, p.NAME, COUNT(pi.PRODUCT_ID) as total_ingredientes
                FROM PRODUCTS p
                LEFT JOIN PRODUCT_INGREDIENTS pi ON p.ID = pi.PRODUCT_ID AND pi.PORTIONS > 0
                WHERE p.ID IN ({placeholders_check})
                GROUP BY p.ID, p.NAME
            """, tuple(product_ids))
            for row in cur.fetchall():
                product_id, product_name, total_ing = row
                logger.warning(f"[PRODUCT_SERVICE]   → Produto {product_id} ({product_name}): {total_ing} ingredientes obrigatórios (PORTIONS > 0)")
        
        for row in ingredient_rows:
            if use_loss_percentage:
                product_id, ing_id, portions, loss_pct, name, base_portion_quantity, base_portion_unit, stock_unit, is_available = row
                loss_percentage = float(loss_pct or 0)
            else:
                product_id, ing_id, portions, name, base_portion_quantity, base_portion_unit, stock_unit, is_available = row
                loss_percentage = 0
            
            if product_id not in product_ingredients:
                product_ingredients[product_id] = []
            
            product_ingredients[product_id].append({
                'ingredient_id': ing_id,
                'portions': portions,
                'loss_percentage': loss_percentage,
                'name': name,
                'base_portion_quantity': base_portion_quantity,
                'base_portion_unit': base_portion_unit,
                'stock_unit': stock_unit,
                'is_available': is_available
            })
        
        # LOG: Ingredientes por produto
        for product_id, ingredients in product_ingredients.items():
            logger.debug(f"[PRODUCT_SERVICE] Produto {product_id} tem {len(ingredients)} ingredientes: "
                       f"{[ing['name'] for ing in ingredients]}")
        
        # OTIMIZAÇÃO: Busca estoque disponível de todos os ingredientes de uma vez
        all_ingredient_ids = set()
        for ingredients in product_ingredients.values():
            for ing in ingredients:
                all_ingredient_ids.add(ing['ingredient_id'])
        
        logger.info(f"[PRODUCT_SERVICE] Buscando estoque {'físico' if for_listing else 'disponível'} para {len(all_ingredient_ids)} ingredientes únicos")
        
        ingredient_availability = {}
        if all_ingredient_ids:
            # CORREÇÃO: Para listagem, usa estoque físico (sem reservas temporárias)
            # Para validação, usa estoque disponível (com reservas temporárias)
            if for_listing:
                ingredient_availability = stock_service._batch_get_ingredient_physical_stock(list(all_ingredient_ids), cur)
            else:
                ingredient_availability = stock_service._batch_get_ingredient_available_stock(list(all_ingredient_ids), cur)
            logger.info(f"[PRODUCT_SERVICE] Estoque {'físico' if for_listing else 'disponível'} retornado para {len(ingredient_availability)} ingredientes")
            
            # LOG: Estoque de alguns ingredientes
            for ing_id, stock in list(ingredient_availability.items())[:5]:
                logger.debug(f"[PRODUCT_SERVICE] Ingrediente {ing_id}: estoque disponível = {stock}")
        else:
            logger.warning(f"[PRODUCT_SERVICE] Nenhum ingrediente para buscar estoque!")
        
        # Calcula capacidade para cada produto
        for product_id in product_ids:
            if product_id not in product_ingredients or not product_ingredients[product_id]:
                # Produto sem ingredientes obrigatórios
                logger.warning(f"[PRODUCT_SERVICE] Produto {product_id} sem ingredientes obrigatórios (PORTIONS > 0)")
                result[product_id] = {
                    'status': 'unavailable',
                    'capacity': 0,
                    'is_available': False,
                    'limiting_ingredient': None
                }
                continue
            
            ingredients = product_ingredients[product_id]
            capacities = []
            min_capacity = None
            limiting_ingredient = None
            
            logger.debug(f"[PRODUCT_SERVICE] Calculando capacidade para produto {product_id} com {len(ingredients)} ingredientes")
            
            for ing in ingredients:
                ing_id = ing['ingredient_id']
                portions = ing['portions']
                loss_percentage = ing['loss_percentage']
                name = ing['name']
                base_portion_quantity = ing['base_portion_quantity']
                base_portion_unit = ing['base_portion_unit']
                stock_unit = ing['stock_unit']
                
                if not ing['is_available']:
                    logger.debug(f"[PRODUCT_SERVICE] Ingrediente {ing_id} ({name}) não disponível (IS_AVAILABLE = FALSE)")
                    continue
                
                # Obtém estoque disponível (já buscado em batch)
                available_stock = ingredient_availability.get(ing_id, Decimal('0'))
                
                # LOG: Estoque do ingrediente (SEMPRE logar se for 0 para diagnóstico)
                if available_stock <= 0:
                    logger.warning(f"[PRODUCT_SERVICE] ⚠️ Produto {product_id}, Ingrediente {ing_id} ({name}): "
                                 f"ESTOQUE DISPONÍVEL ZERO! "
                                 f"estoque_disponivel={available_stock}, portions={portions}, "
                                 f"base_portion_quantity={base_portion_quantity}, base_portion_unit={base_portion_unit}, "
                                 f"stock_unit={stock_unit}")
                else:
                    logger.debug(f"[PRODUCT_SERVICE] Produto {product_id}, Ingrediente {ing_id} ({name}): "
                               f"estoque_disponivel={available_stock}, portions={portions}, "
                               f"base_portion_quantity={base_portion_quantity}, base_portion_unit={base_portion_unit}, "
                               f"stock_unit={stock_unit}")
                
                # Calcula consumo por unidade
                try:
                    consumption_per_unit = stock_service.calculate_consumption_in_stock_unit(
                        portions=portions,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=1,
                        loss_percentage=loss_percentage
                    )
                    logger.debug(f"[PRODUCT_SERVICE] Consumo por unidade calculado: {consumption_per_unit} {stock_unit}")
                except ValueError as e:
                    logger.error(f"[PRODUCT_SERVICE] Erro ao calcular consumo para {name} (ingrediente {ing_id}): {e}", exc_info=True)
                    continue
                
                if consumption_per_unit <= 0:
                    logger.warning(f"[PRODUCT_SERVICE] Consumo por unidade <= 0 para {name} (ingrediente {ing_id}): {consumption_per_unit}")
                    continue
                
                # Calcula capacidade para este ingrediente
                capacity = int(available_stock / consumption_per_unit)
                capacities.append(capacity)
                
                logger.debug(f"[PRODUCT_SERVICE] Capacidade calculada para {name}: {capacity} unidades "
                           f"(estoque: {available_stock}, consumo: {consumption_per_unit})")
                
                # Identifica insumo limitante (menor capacidade)
                if min_capacity is None or capacity < min_capacity:
                    min_capacity = capacity
                    limiting_ingredient = {
                        'ingredient_id': ing_id,
                        'name': name,
                        'available_stock': float(available_stock),
                        'consumption_per_unit': float(consumption_per_unit),
                        'capacity': capacity,
                        'stock_unit': stock_unit
                    }
            
            # LOG: Capacidades calculadas (SEMPRE logar detalhes para diagnóstico)
            if not capacities or min_capacity is None or min_capacity < 1:
                logger.warning(f"[PRODUCT_SERVICE] ❌ Produto {product_id} INDISPONÍVEL: "
                             f"capacities={capacities}, min_capacity={min_capacity}, "
                             f"total_ingredientes={len(ingredients)}, "
                             f"ingredientes_com_estoque={len([ing for ing in ingredients if ingredient_availability.get(ing['ingredient_id'], Decimal('0')) > 0])}")
                # LOG: Detalhes dos ingredientes que causaram capacidade 0
                for ing in ingredients:
                    ing_id = ing['ingredient_id']
                    ing_stock = ingredient_availability.get(ing_id, Decimal('0'))
                    if ing_stock <= 0:
                        logger.warning(f"[PRODUCT_SERVICE]   → Ingrediente {ing_id} ({ing['name']}): "
                                     f"estoque_disponivel={ing_stock} {ing['stock_unit']}")
            else:
                logger.info(f"[PRODUCT_SERVICE] ✅ Produto {product_id} disponível: "
                           f"capacities={capacities}, min_capacity={min_capacity}")
            
            # Determina status de disponibilidade
            if not capacities or min_capacity is None or min_capacity < 1:
                result[product_id] = {
                    'status': 'unavailable',
                    'capacity': 0,
                    'is_available': False,
                    'limiting_ingredient': None
                }
            elif min_capacity == 1:
                logger.info(f"[PRODUCT_SERVICE] Produto {product_id} disponível (limitado): capacity=1")
                result[product_id] = {
                    'status': 'limited',
                    'capacity': 1,
                    'is_available': True,
                    'limiting_ingredient': limiting_ingredient
                }
            else:
                # Capacidade > 1: verifica se está baixo
                logger.info(f"[PRODUCT_SERVICE] Produto {product_id} disponível: capacity={min_capacity}")
                if limiting_ingredient:
                    # ALTERAÇÃO: Valores já são float (convertidos acima na linha 345-346)
                    available_stock = limiting_ingredient.get('available_stock', 0.0)
                    consumption_per_unit = limiting_ingredient.get('consumption_per_unit', 0.0)
                    
                    # Se o estoque disponível é menos que 2x o consumo por unidade, está baixo
                    if available_stock < (consumption_per_unit * 2.0):
                        result[product_id] = {
                            'status': 'low_stock',
                            'capacity': min_capacity,
                            'is_available': True,
                            'limiting_ingredient': limiting_ingredient
                        }
                    else:
                        result[product_id] = {
                            'status': 'available',
                            'capacity': min_capacity,
                            'is_available': True,
                            'limiting_ingredient': limiting_ingredient
                        }
                else:
                    result[product_id] = {
                        'status': 'available',
                        'capacity': min_capacity,
                        'is_available': True,
                        'limiting_ingredient': None
                    }
        
        # Produtos sem ingredientes obrigatórios recebem status unavailable
        for product_id in product_ids:
            if product_id not in result:
                logger.warning(f"[PRODUCT_SERVICE] Produto {product_id} não processado (sem ingredientes ou erro)")
                result[product_id] = {
                    'status': 'unavailable',
                    'capacity': 0,
                    'is_available': False,
                    'limiting_ingredient': None
                }
        
        # LOG: Resumo final
        available_count = sum(1 for r in result.values() if r.get('is_available', False))
        limited_count = sum(1 for r in result.values() if r.get('status') == 'limited')
        unavailable_count = sum(1 for r in result.values() if r.get('status') == 'unavailable')
        logger.info(f"[PRODUCT_SERVICE] _batch_get_product_availability_status concluído: "
                   f"{available_count} disponíveis, {limited_count} limitados, {unavailable_count} indisponíveis de {len(product_ids)} produtos")
        
        return result
        
    except Exception as e:
        logger.error(f"[PRODUCT_SERVICE] Erro ao calcular disponibilidade em batch: {e}", exc_info=True)
        # Retorna status unknown para todos os produtos em caso de erro
        return {pid: {'status': 'unknown', 'capacity': 0, 'is_available': False, 'limiting_ingredient': None} 
                for pid in product_ids}


def check_product_availability(product_id, quantity=1):
    """
    Verifica a disponibilidade completa de um produto, incluindo estoque de todos os ingredientes.
    Retorna informações detalhadas sobre disponibilidade.
    
    Args:
        product_id: ID do produto
        quantity: Quantidade desejada do produto (padrão: 1)
    
    Returns:
        dict: {
            'is_available': bool,
            'status': str,  # 'available', 'low_stock', 'unavailable', 'unknown'
            'message': str,
            'ingredients': [
                {
                    'ingredient_id': int,
                    'name': str,
                    'is_available': bool,
                    'current_stock': Decimal,
                    'required': Decimal,
                    'stock_unit': str
                }
            ]
        }
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se produto existe e está ativo
        cur.execute("SELECT ID, NAME FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;", (product_id,))
        product = cur.fetchone()
        if not product:
            return {
                'is_available': False,
                'status': 'unavailable',
                'message': 'Produto não encontrado ou inativo',
                'ingredients': []
            }
        
        # Busca ingredientes do produto com informações completas
        cur.execute("""
            SELECT 
                i.ID, 
                i.NAME, 
                pi.PORTIONS, 
                i.CURRENT_STOCK, 
                i.STOCK_UNIT,
                i.BASE_PORTION_QUANTITY,
                i.BASE_PORTION_UNIT,
                i.IS_AVAILABLE,
                i.STOCK_STATUS
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ?
        """, (product_id,))
        
        ingredients_info = []
        is_available = True
        has_low_stock = False
        
        for row in cur.fetchall():
            ing_id, name, portions, current_stock, stock_unit, base_portion_quantity, base_portion_unit, is_ing_available, stock_status = row
            
            if not is_ing_available or stock_status == 'out_of_stock':
                is_available = False
                ingredients_info.append({
                    'ingredient_id': ing_id,
                    'name': name,
                    'is_available': False,
                    'current_stock': Decimal(str(current_stock or 0)),
                    'required': Decimal('0'),
                    'stock_unit': stock_unit or 'un',
                    'reason': 'indisponível' if not is_ing_available else 'sem estoque'
                })
                continue
            
            # Calcula quantidade necessária convertida para unidade do estoque
            try:
                required_quantity = stock_service.calculate_consumption_in_stock_unit(
                    portions=portions or 0,
                    base_portion_quantity=base_portion_quantity or 1,
                    base_portion_unit=base_portion_unit or 'un',
                    stock_unit=stock_unit or 'un',
                    item_quantity=quantity
                )
            except ValueError as e:
                is_available = False
                ingredients_info.append({
                    'ingredient_id': ing_id,
                    'name': name,
                    'is_available': False,
                    'current_stock': Decimal(str(current_stock or 0)),
                    'required': Decimal('0'),
                    'stock_unit': stock_unit or 'un',
                    'reason': f'erro na conversão: {str(e)}'
                })
                continue
            
            current_stock_decimal = Decimal(str(current_stock or 0))
            
            if current_stock_decimal < required_quantity:
                is_available = False
                ingredients_info.append({
                    'ingredient_id': ing_id,
                    'name': name,
                    'is_available': False,
                    'current_stock': current_stock_decimal,
                    'required': required_quantity,
                    'stock_unit': stock_unit or 'un',
                    'reason': 'estoque insuficiente'
                })
            else:
                # Verifica se está com estoque baixo
                if stock_status == 'low' or (current_stock_decimal - required_quantity) < (current_stock_decimal * Decimal('0.2')):
                    has_low_stock = True
                
                ingredients_info.append({
                    'ingredient_id': ing_id,
                    'name': name,
                    'is_available': True,
                    'current_stock': current_stock_decimal,
                    'required': required_quantity,
                    'stock_unit': stock_unit or 'un',
                    'reason': None
                })
        
        if not ingredients_info:
            return {
                'is_available': False,
                'status': 'unavailable',
                'message': 'Produto sem ingredientes cadastrados',
                'ingredients': []
            }
        
        # Determina status final
        if not is_available:
            status = 'unavailable'
            message = 'Produto indisponível por falta de estoque de ingredientes'
        elif has_low_stock:
            status = 'low_stock'
            message = 'Produto disponível, mas com estoque baixo de alguns ingredientes'
        else:
            status = 'available'
            message = 'Produto disponível'
        
        return {
            'is_available': is_available,
            'status': status,
            'message': message,
            'ingredients': ingredients_info
        }
        
    except Exception as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao verificar disponibilidade do produto {product_id}: {e}", exc_info=True)
        return {
            'is_available': False,
            'status': 'unknown',
            'message': f'Erro ao verificar disponibilidade: {str(e)}',
            'ingredients': []
        }
    finally:
        if conn:
            conn.close()


def get_ingredient_max_available_quantity(ingredient_id, max_quantity_from_rule=None, item_quantity=1, base_portions=0, cur=None):
    """
    Calcula a quantidade máxima disponível de um ingrediente extra baseado em:
    1. MAX_QUANTITY definido na regra do produto (se fornecido)
    2. Estoque atual do ingrediente
    
    Retorna a menor quantidade entre os dois limites.
    
    OTIMIZAÇÃO DE PERFORMANCE: Aceita cursor opcional para reutilizar conexão existente,
    evitando múltiplas conexões ao banco quando chamada em loops.
    
    Args:
        ingredient_id: ID do ingrediente
        max_quantity_from_rule: MAX_QUANTITY da regra do produto (None se não limitado)
        item_quantity: Quantidade de itens do produto (padrão: 1)
        base_portions: Porções base do ingrediente no produto (padrão: 0 para extras)
        cur: Cursor opcional para reutilizar conexão (se None, cria nova conexão)
    
    Returns:
        dict: {
            'max_available': int,  # Quantidade máxima de porções extras disponíveis
            'limited_by': str,  # 'rule' ou 'stock' ou 'both'
            'stock_info': {
                'current_stock': Decimal,
                'stock_unit': str,
                'base_portion_quantity': Decimal,
                'base_portion_unit': str
            }
        }
    """
    # ALTERAÇÃO: Logger já está definido no topo do módulo
    conn = None
    should_close_conn = False
    
    try:
        # Se cursor não foi fornecido, cria nova conexão
        if cur is None:
            conn = get_db_connection()
            cur = conn.cursor()
            should_close_conn = True
        
        # Busca informações do ingrediente
        cur.execute("""
            SELECT 
                NAME, CURRENT_STOCK, STOCK_UNIT, BASE_PORTION_QUANTITY, 
                BASE_PORTION_UNIT, IS_AVAILABLE
            FROM INGREDIENTS
            WHERE ID = ?
        """, (ingredient_id,))
        
        result = cur.fetchone()
        if not result:
            return {
                'max_available': 0,
                'limited_by': 'not_found',
                'stock_info': None
            }
        
        name, current_stock, stock_unit, base_portion_quantity, base_portion_unit, is_available = result
        
        if not is_available:
            return {
                'max_available': 0,
                'limited_by': 'unavailable',
                'stock_info': {
                    'current_stock': Decimal(str(current_stock or 0)),
                    'stock_unit': stock_unit or 'un',
                    'base_portion_quantity': Decimal(str(base_portion_quantity or 1)),
                    'base_portion_unit': base_portion_unit or 'un'
                }
            }
        
        # IMPORTANTE: Usar estoque disponível (já considera reservas), não apenas CURRENT_STOCK
        from .stock_service import get_ingredient_available_stock
        available_stock_result = get_ingredient_available_stock(ingredient_id, cur)
        # get_ingredient_available_stock retorna Decimal diretamente, não um dicionário
        available_stock_decimal = available_stock_result if isinstance(available_stock_result, Decimal) else Decimal(str(available_stock_result or 0))
        
        current_stock_decimal = Decimal(str(current_stock or 0))
        base_portion_quantity_decimal = Decimal(str(base_portion_quantity or 1))
        stock_unit_str = stock_unit or 'un'
        base_portion_unit_str = base_portion_unit or 'un'
        
        # LOG: Estoque disponível
        logger.info(
            f"[get_ingredient_max_available_quantity] Estoque para ingrediente {ingredient_id} (item_quantity={item_quantity}): "
            f"current_stock={current_stock_decimal} {stock_unit_str}, "
            f"available_stock={available_stock_decimal} {stock_unit_str}"
        )
        
        # Calcula quantidade máxima baseada no estoque DISPONÍVEL (já considera reservas)
        # Precisa converter da unidade do estoque para a unidade da porção base
        max_from_stock = 0
        if available_stock_decimal > 0:
            try:
                # Converte estoque DISPONÍVEL para unidade da porção base
                from .stock_service import _convert_unit
                stock_in_base_unit = _convert_unit(
                    available_stock_decimal,  # CORREÇÃO: Usar estoque disponível, não total
                    stock_unit_str,
                    base_portion_unit_str
                )
                
                # Log de debug para verificar conversão e cálculo
                logger.debug(
                    f"[get_ingredient_max_available_quantity] Ingrediente {ingredient_id}: "
                    f"Estoque disponível: {available_stock_decimal} {stock_unit_str} → "
                    f"Convertido: {stock_in_base_unit} {base_portion_unit_str}"
                )
                
                # AJUSTE: Calcula quantas porções extras podem ser adicionadas
                # Considera as porções base já incluídas no produto
                # Fórmula: (base_portions * item_quantity + extras * item_quantity) * base_portion_quantity <= available_stock
                # Simplificando: (base_portions + extras) * base_portion_quantity * item_quantity <= available_stock
                # Então: extras <= (available_stock / (base_portion_quantity * item_quantity)) - base_portions
                if base_portion_quantity_decimal > 0:
                    # Converte estoque DISPONÍVEL para quantidade total de porções disponíveis
                    total_portions_available = stock_in_base_unit / base_portion_quantity_decimal
                    
                    # CORREÇÃO: base_portions é por item, então calcula total de porções base
                    base_portions_decimal = Decimal(str(base_portions or 0))
                    total_base_portions = base_portions_decimal * Decimal(str(item_quantity))
                    
                    # LOG: Valores de cálculo
                    logger.info(
                        f"[get_ingredient_max_available_quantity] Cálculo para ingrediente {ingredient_id} (item_quantity={item_quantity}): "
                        f"total_portions_available={total_portions_available}, "
                        f"base_portions_decimal={base_portions_decimal}, "
                        f"total_base_portions={total_base_portions}"
                    )
                    
                    # Se base_portions > 0, é um ingrediente da base
                    # CORREÇÃO CRÍTICA: Para ingredientes base, max_quantity representa o total de porções possíveis (base + extras)
                    # MAS precisa considerar que quando item_quantity muda, o consumo base muda proporcionalmente
                    # 
                    # Exemplo:
                    # - Estoque disponível = 0.12kg
                    # - base_portion_quantity = 0.03kg (30g)
                    # - base_portions = 2 porções por item
                    # - total_portions_available = 0.12 / 0.03 = 4 porções totais possíveis
                    #
                    # Quando item_quantity=2:
                    #   - total_base_portions = 2 × 2 = 4
                    #   - max_quantity = 4 (total: 4 base + 0 extras)
                    #
                    # Quando item_quantity=1:
                    #   - total_base_portions = 2 × 1 = 2
                    #   - max_quantity = 4 (total: 2 base + 2 extras) ← Deveria ser 4, não 2!
                    #
                    # O problema é que max_quantity deve ser o total (base + extras), não apenas extras.
                    # Então quando item_quantity diminui, o consumo base diminui, mas o max_quantity total permanece o mesmo
                    # porque o estoque disponível total não muda.
                    #
                    # Na verdade, para ingredientes base, max_quantity = total_portions_available sempre
                    # porque representa o total de porções possíveis (base + extras).
                    # O que muda com item_quantity é quanto desse total já está sendo usado pela base (total_base_portions).
                    if base_portions_decimal > 0:
                        # Para ingredientes base, max_from_stock é o total de porções possíveis (base + extras)
                        # Este valor é sempre total_portions_available porque representa o estoque total disponível
                        # Quando item_quantity muda, total_base_portions muda, mas total_portions_available não muda
                        # porque o estoque disponível total permanece o mesmo
                        max_from_stock = max(0, int(total_portions_available))
                        
                        # LOG: Valores detalhados
                        logger.info(
                            f"[get_ingredient_max_available_quantity] Ingrediente base {ingredient_id}: "
                            f"item_quantity={item_quantity}, "
                            f"base_portions={base_portions_decimal}, "
                            f"total_base_portions={total_base_portions}, "
                            f"total_portions_available={total_portions_available}, "
                            f"max_from_stock={max_from_stock}"
                        )
                    else:
                        # Para ingredientes extras (base_portions = 0), calcula apenas extras
                        # Calcula quantas porções extras totais podem ser adicionadas
                        max_extras_total = total_portions_available - total_base_portions
                        
                        # Divide pela quantidade de itens para ter extras disponíveis por item
                        if item_quantity > 0:
                            max_extras_per_item = max_extras_total / Decimal(str(item_quantity))
                        else:
                            max_extras_per_item = Decimal('0')
                        
                        # Arredonda para baixo e converte para int (não pode ser negativo)
                        max_from_stock = max(0, int(max_extras_per_item))
            except Exception as e:
                # ALTERAÇÃO: Substituído print() por logging estruturado
                logger.warning(f"Erro ao calcular quantidade máxima do estoque para ingrediente {ingredient_id}: {e}", exc_info=True)
                max_from_stock = 0
        
        # Determina o limite final (menor entre regra e estoque)
        limited_by = []
        max_available = 0
        
        if max_quantity_from_rule is not None and max_quantity_from_rule > 0:
            # Há limite da regra
            if max_from_stock > 0:
                # Compara com estoque
                max_available = min(max_quantity_from_rule, max_from_stock)
                if max_available == max_quantity_from_rule:
                    limited_by.append('rule')
                if max_available == max_from_stock:
                    limited_by.append('stock')
            else:
                # Sem estoque, usa regra (mas será 0 se não houver estoque)
                max_available = max_quantity_from_rule if max_from_stock > 0 else 0
                if max_available > 0:
                    limited_by.append('rule')
                else:
                    limited_by.append('stock')
        else:
            # Sem limite da regra, usa apenas estoque
            max_available = max_from_stock
            if max_available > 0:
                limited_by.append('stock')
        
        # LOG: Valores finais
        logger.info(
            f"[get_ingredient_max_available_quantity] Resultado final para ingrediente {ingredient_id} (item_quantity={item_quantity}): "
            f"max_quantity_from_rule={max_quantity_from_rule}, "
            f"max_from_stock={max_from_stock}, "
            f"max_available={max_available}, "
            f"limited_by={limited_by}"
        )
        
        return {
            'max_available': max_available,
            'limited_by': 'both' if len(limited_by) == 2 else (limited_by[0] if limited_by else 'none'),
            'stock_info': {
                'current_stock': current_stock_decimal,
                'stock_unit': stock_unit_str,
                'base_portion_quantity': base_portion_quantity_decimal,
                'base_portion_unit': base_portion_unit_str
            }
        }
        
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao calcular quantidade máxima disponível do ingrediente {ingredient_id}: {e}", exc_info=True)
        return {
            'max_available': 0,
            'limited_by': 'error',
            'stock_info': None
        }
    finally:
        # Fecha conexão apenas se foi criada nesta função
        if should_close_conn and conn:
            conn.close()

# OTIMIZAÇÃO DE PERFORMANCE: Cache em memória para listas de produtos
# Cache é invalidado quando produtos são criados/atualizados/deletados
_product_list_cache = {}
_product_list_cache_timestamp = {}
_product_list_cache_ttl = 60  # ALTERAÇÃO: Reduzido de 5 minutos para 60 segundos conforme especificação

def _invalidate_product_cache():
    """Invalida cache de produtos forçando refresh na próxima chamada"""
    global _product_list_cache, _product_list_cache_timestamp
    _product_list_cache = {}
    _product_list_cache_timestamp = {}

def _get_cache_key(name_filter, category_id, page, page_size, include_inactive):
    """Gera chave única para o cache baseada nos parâmetros"""
    return f"{name_filter or ''}_{category_id or ''}_{page}_{page_size}_{include_inactive}"

def _is_cache_valid(cache_key):
    """Verifica se o cache ainda é válido"""
    if cache_key not in _product_list_cache_timestamp:
        return False
    elapsed = (datetime.now() - _product_list_cache_timestamp[cache_key]).total_seconds()
    return elapsed < _product_list_cache_ttl

def list_products(name_filter=None, category_id=None, page=1, page_size=10, include_inactive=False, only_inactive=False, filter_unavailable=True):  
    """
    Lista produtos com cache em memória para melhor performance.
    Cache TTL: 60 segundos. Invalidado automaticamente quando produtos são modificados.
    
    ALTERAÇÃO: Agora usa calculate_product_capacity() diretamente para filtrar produtos
    com capacidade >= 1 ao invés de apenas verificar availability_status.
    
    ALTERAÇÃO: Adiciona suporte ao parâmetro only_inactive para filtrar apenas produtos inativos.
    """
    page = max(int(page or 1), 1)  
    page_size = max(int(page_size or 10), 1)  
    offset = (page - 1) * page_size  
    
    # ALTERAÇÃO: Se only_inactive=True, deve incluir inativos na query
    if only_inactive:
        include_inactive = True
    
    # OTIMIZAÇÃO: Verifica cache antes de consultar banco
    # Nota: Cache desabilitado para filtros de nome (busca dinâmica) e produtos inativos
    # Cache apenas para listagens padrão (sem filtro de nome, apenas ativos)
    use_cache = not name_filter and not include_inactive and not only_inactive
    cache_key = _get_cache_key(name_filter, category_id, page, page_size, include_inactive)
    
    if use_cache and _is_cache_valid(cache_key) and cache_key in _product_list_cache:
        return _product_list_cache[cache_key]
    
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # ALTERAÇÃO: Se only_inactive=True, filtrar apenas inativos; senão usar lógica padrão
        if only_inactive:
            where_clauses = ["p.IS_ACTIVE = FALSE"]  
        elif include_inactive:
            where_clauses = []  # Inclui ativos e inativos
        else:
            where_clauses = ["p.IS_ACTIVE = TRUE"]  # Apenas ativos
        params = []  
        if name_filter:  
            where_clauses.append("UPPER(p.NAME) LIKE UPPER(?)")  
            params.append(f"%{name_filter}%")
        if category_id:  
            where_clauses.append("p.CATEGORY_ID = ?")  
            params.append(category_id)
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"  
        # total  
        # ALTERAÇÃO: Query parametrizada - where_sql é construído de forma segura (apenas cláusulas fixas)
        cur.execute(f"SELECT COUNT(*) FROM PRODUCTS WHERE {where_sql.replace('p.', '')};", tuple(params))  
        total = cur.fetchone()[0] or 0  
        # page - Query com sintaxe FIRST/SKIP do Firebird
        # OTIMIZAÇÃO: Incluir nome da categoria via LEFT JOIN para evitar N+1
        query = f"""
            SELECT FIRST {page_size} SKIP {offset} 
                p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.COST_PRICE, 
                p.PREPARATION_TIME_MINUTES, p.CATEGORY_ID, p.IMAGE_URL, p.IS_ACTIVE,
                COALESCE(c.NAME, 'Sem categoria') as CATEGORY_NAME
            FROM PRODUCTS p
            LEFT JOIN CATEGORIES c ON p.CATEGORY_ID = c.ID
            WHERE {where_sql} 
            ORDER BY p.NAME
        """
        cur.execute(query, tuple(params))
        
        # Coleta todos os product_ids primeiro
        product_rows = cur.fetchall()
        product_ids = [row[0] for row in product_rows]
        items = []
        
        # Inicializa estruturas para armazenar dados batch
        availability_map = {}
        capacity_map = {}
        ingredients_map = {}
        
        # OTIMIZAÇÃO: Usa _batch_get_product_availability_status() para calcular disponibilidade de múltiplos produtos de uma vez
        # Evita N+1 queries ao buscar ingredientes, estoque e calcular capacidade em batch
        if product_ids:
            try:
                # LOG: Iniciando cálculo de disponibilidade em batch
                logger.info(f"[PRODUCT_SERVICE] Calculando disponibilidade para {len(product_ids)} produtos: {product_ids[:5]}...")
                
                # CORREÇÃO: Para listagem (filter_unavailable=True), usa estoque físico (sem reservas temporárias)
                # Para validação (filter_unavailable=False), usa estoque disponível (com reservas temporárias)
                for_listing = filter_unavailable
                batch_availability = _batch_get_product_availability_status(product_ids, cur, for_listing=for_listing)
                
                # LOG: Resultados do batch
                logger.info(f"[PRODUCT_SERVICE] batch_availability retornou {len(batch_availability)} produtos")
                
                # Processa resultados do batch
                for product_id in product_ids:
                    if product_id in batch_availability:
                        avail_info = batch_availability[product_id]
                        availability_status = avail_info.get('status', 'unknown')
                        capacity = avail_info.get('capacity', 0)
                        is_available = avail_info.get('is_available', False)
                        limiting_ingredient = avail_info.get('limiting_ingredient')
                        
                        # LOG: Detalhes de cada produto
                        if availability_status == 'unavailable' or capacity < 1:
                            logger.warning(f"[PRODUCT_SERVICE] Produto {product_id} indisponível: "
                                         f"status={availability_status}, capacity={capacity}, "
                                         f"is_available={is_available}")
                        else:
                            logger.debug(f"[PRODUCT_SERVICE] Produto {product_id} disponível: "
                                       f"status={availability_status}, capacity={capacity}")
                        
                        availability_map[product_id] = availability_status
                        capacity_map[product_id] = {
                            'capacity': capacity,
                            'is_available': is_available,
                            'limiting_ingredient': limiting_ingredient
                        }
                    else:
                        # Produto não encontrado no batch (erro)
                        logger.warning(f"[PRODUCT_SERVICE] Produto {product_id} não encontrado no batch_availability")
                        availability_map[product_id] = "unknown"
                        capacity_map[product_id] = {
                            'capacity': 0,
                            'is_available': False,
                            'limiting_ingredient': None
                        }
            except Exception as e:
                logger.error(f"[PRODUCT_SERVICE] Erro ao buscar capacidade em batch: {e}", exc_info=True)
                # Em caso de erro, marca todos como unknown
                for product_id in product_ids:
                    availability_map[product_id] = "unknown"
                    capacity_map[product_id] = {
                        'capacity': 0,
                        'is_available': False,
                        'limiting_ingredient': None
                    }
        
        # OTIMIZAÇÃO: Busca todos os ingredientes de uma vez
        if product_ids:
            try:
                placeholders = ', '.join(['?' for _ in product_ids])
                ingredients_query = f"""
                    SELECT pi.PRODUCT_ID, pi.INGREDIENT_ID, pi.PORTIONS, pi.MIN_QUANTITY, pi.MAX_QUANTITY
                    FROM PRODUCT_INGREDIENTS pi
                    WHERE pi.PRODUCT_ID IN ({placeholders})
                    ORDER BY pi.PRODUCT_ID, pi.INGREDIENT_ID
                """
                cur.execute(ingredients_query, tuple(product_ids))
                for row in cur.fetchall():
                    product_id = row[0]
                    if product_id not in ingredients_map:
                        ingredients_map[product_id] = []
                    ingredients_map[product_id].append({
                        "ingredient_id": row[1],
                        "portions": float(row[2]) if row[2] is not None else 0.0,
                        "min_quantity": int(row[3]) if row[3] is not None else 0,
                        "max_quantity": int(row[4]) if row[4] is not None else 0
                    })
            except Exception as e:
                # ALTERAÇÃO: Logger já está definido no topo do módulo
                logger.warning(f"Erro ao buscar ingredientes em batch: {e}", exc_info=True)
        
        # Processa os produtos com os dados já carregados
        for row in product_rows:
            product_id = row[0]
            
            # SIMPLIFICAÇÃO: Filtra produtos com capacidade < 1 usando availability_status
            # Verifica status de disponibilidade antes de adicionar à lista
            # Aplica filtro apenas se filter_unavailable=True (usuários normais)
            availability_status = availability_map.get(product_id, "unknown")
            capacity_info = capacity_map.get(product_id, {})
            capacity = capacity_info.get('capacity', 0)
            
            # LOG: Status de cada produto antes do filtro
            if filter_unavailable:
                logger.debug(f"[PRODUCT_SERVICE] Produto {product_id} (row[1]): "
                           f"availability_status={availability_status}, capacity={capacity}, "
                           f"filter_unavailable={filter_unavailable}")
            
            # Filtra produtos indisponíveis (unavailable = capacidade < 1)
            if filter_unavailable and availability_status == "unavailable":
                # Produto sem capacidade - não incluir na listagem para usuários normais
                # Mas não desativa no banco (IS_ACTIVE permanece TRUE)
                # Administradores ainda veem todos os produtos
                logger.debug(f"[PRODUCT_SERVICE] Produto {product_id} filtrado (unavailable): "
                           f"capacity={capacity}, status={availability_status}")
                continue
            
            item = {  
                "id": product_id,  
                "name": row[1],  
                "description": row[2],  
                "price": str(row[3]),  
                "cost_price": str(row[4]) if row[4] else "0.00",  
                "preparation_time_minutes": row[5] if row[5] else 0,  
                "category_id": row[6],
                "is_active": row[8] if len(row) > 8 else True,
                "category_name": row[9] if len(row) > 9 and row[9] else "Sem categoria"
            }
            # Adiciona URL da imagem do banco se existir
            if row[7]:  # IMAGE_URL
                item["image_url"] = row[7]
                try:
                    item["image_hash"] = _get_image_hash(row[7])
                except Exception as e:
                    # ALTERAÇÃO: Logger já está definido no topo do módulo
                    logger.warning(f"Erro ao gerar hash da imagem: {e}", exc_info=True)
                    item["image_hash"] = None
            
            # Adiciona status de disponibilidade (já carregado em batch)
            item["availability_status"] = availability_status
            
            # ALTERAÇÃO: Adiciona informação de capacidade ao produto
            item["capacity"] = capacity
            item["capacity_info"] = capacity_info
            
            # Adiciona ingredientes (já carregados em batch)
            item["ingredients"] = ingredients_map.get(product_id, [])
            
            items.append(item)  
        
        # ALTERAÇÃO: Ajustar total após filtrar produtos com capacidade < 1
        # Se filter_unavailable=True, ajusta o total para refletir apenas produtos disponíveis
        # Se filter_unavailable=False (admin), usa o total original
        if filter_unavailable:
            filtered_total = len(items)
            total_pages = (filtered_total + page_size - 1) // page_size if filtered_total > 0 else 0
            pagination_total = filtered_total
            
            # LOG: Estatísticas de filtragem
            logger.info(f"[PRODUCT_SERVICE] Filtragem aplicada: {len(product_rows)} produtos no banco, "
                       f"{filtered_total} produtos disponíveis após filtro, "
                       f"{len(product_rows) - filtered_total} produtos filtrados (unavailable)")
        else:
            # Admin vê todos os produtos, usa total original
            total_pages = (total + page_size - 1) // page_size
            pagination_total = total
            logger.info(f"[PRODUCT_SERVICE] Filtragem desabilitada (admin): {len(items)} produtos retornados")
        
        result = {  
            "items": items,  
            "pagination": {  
                "total": pagination_total,
                "page": page,  
                "page_size": page_size,  
                "total_pages": total_pages  
            }  
        }
        
        # LOG: Resultado final
        # ALTERAÇÃO: Logging otimizado (apenas quando necessário para diagnóstico)
        if len(items) == 0 or not use_cache:
            logger.info(f"[PRODUCT_SERVICE] list_products retornando {len(items)} produtos (total no banco: {total}, "
                       f"filtrados: {filtered_total if filter_unavailable else 'N/A'})")
        
        # OTIMIZAÇÃO: Salva resultado no cache se for cacheável
        if use_cache:
            _product_list_cache[cache_key] = result
            _product_list_cache_timestamp[cache_key] = datetime.now()
        
        return result
    except fdb.Error as e:  
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao listar produtos: {e}", exc_info=True)  
        return {  
            "items": [],  
            "pagination": {  
                "total": 0,  
                "page": page,  
                "page_size": page_size,  
                "total_pages": 0  
            }  
        }  
    finally:  
        if conn: conn.close()  


def get_product_by_id(product_id, quantity=1):  
    """
    Obtém produto por ID com cálculo de quantidade máxima de extras baseado no estoque.
    
    Args:
        product_id: ID do produto
        quantity: Quantidade do produto (padrão: 1) - usado para calcular max_available dos extras
    
    Returns:
        dict: Dados do produto com ingredientes e max_quantity já calculado
    """
    # ALTERAÇÃO: Logger já está definido no topo do módulo
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql = "SELECT ID, NAME, DESCRIPTION, PRICE, COST_PRICE, PREPARATION_TIME_MINUTES, CATEGORY_ID, IMAGE_URL FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"  
        cur.execute(sql, (product_id,))  
        row = cur.fetchone()  
        if row:  
            product_id = row[0]
            product = {"id": product_id, "name": row[1], "description": row[2], "price": str(row[3]), "cost_price": str(row[4]) if row[4] else "0.00", "preparation_time_minutes": row[5] if row[5] else 0, "category_id": row[6]}
            # Adiciona URL da imagem do banco se existir
            if row[7]:  # IMAGE_URL
                product["image_url"] = row[7]
                product["image_hash"] = _get_image_hash(row[7])
            
            # Adiciona status de disponibilidade baseado no estoque
            product["availability_status"] = _get_product_availability_status(product_id, cur)

            # Carrega ingredientes com regras e informações de disponibilidade
            cur.execute(
                """
                SELECT pi.INGREDIENT_ID, i.NAME, pi.PORTIONS, pi.MIN_QUANTITY, pi.MAX_QUANTITY,
                       i.ADDITIONAL_PRICE, i.IS_AVAILABLE, i.BASE_PORTION_QUANTITY, i.BASE_PORTION_UNIT,
                       i.STOCK_UNIT
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON i.ID = pi.INGREDIENT_ID
                WHERE pi.PRODUCT_ID = ?
                ORDER BY i.NAME
                """,
                (product_id,)
            )
            
            ingredients_rows = cur.fetchall()
            
            # Para cada ingrediente extra, calcula a quantidade atual de ingredientes base que usam o mesmo ingrediente
            # Isso será usado para ajustar o cálculo de max_available
            ingredients_data = []
            for r in ingredients_rows:
                ing_id = r[0]
                max_quantity_rule = int(r[4]) if r[4] is not None else None
                portions = float(r[2]) if r[2] is not None else 0.0
                
                # Para ingredientes extras, verifica se há ingredientes base que usam o mesmo ingrediente
                # e calcula quanto estoque já está sendo usado
                base_portions_for_calculation = Decimal('0')
                if portions == 0.0:  # É ingrediente extra
                    # Busca se há ingredientes base (portions > 0) que usam o mesmo ingrediente
                    cur.execute("""
                        SELECT pi.PORTIONS, i.BASE_PORTION_QUANTITY
                        FROM PRODUCT_INGREDIENTS pi
                        JOIN INGREDIENTS i ON i.ID = pi.INGREDIENT_ID
                        WHERE pi.PRODUCT_ID = ? 
                          AND pi.INGREDIENT_ID = ?
                          AND pi.PORTIONS > 0
                    """, (product_id, ing_id))
                    base_ingredient_row = cur.fetchone()
                    if base_ingredient_row:
                        # Há ingrediente base que usa o mesmo ingrediente
                        # base_portions é a quantidade de porções base POR ITEM do produto
                        # Exemplo: se PORTIONS = 1.0, significa 1 porção base por item
                        # Se quantity = 2, temos 2 porções base totais
                        # A função get_ingredient_max_available_quantity() espera base_portions como quantidade POR ITEM
                        # e multiplica internamente por item_quantity (linha 428)
                        # Então passamos apenas base_portions (por item), sem multiplicar por quantity
                        base_portions = float(base_ingredient_row[0]) if base_ingredient_row[0] is not None else 0.0
                        base_portions_for_calculation = Decimal(str(base_portions))
                    else:
                        # Não há ingrediente base que usa o mesmo ingrediente
                        base_portions_for_calculation = Decimal('0')
                else:
                    # Para ingredientes base (portions > 0), passa o próprio portions como base_portions
                    # Isso faz a função retornar o total de porções possíveis (não apenas extras)
                    base_portions_for_calculation = Decimal(str(portions))
                
                # IMPORTANTE: Calcula quantidade máxima disponível considerando a quantidade do produto
                # e a quantidade atual de ingredientes base que usam o mesmo ingrediente
                max_available_info = get_ingredient_max_available_quantity(
                    ingredient_id=ing_id,
                    max_quantity_from_rule=max_quantity_rule,
                    item_quantity=quantity,  # Usa a quantidade do produto passada como parâmetro
                    base_portions=float(base_portions_for_calculation),  # Para base: portions; Para extra: porções base que usam o mesmo ingrediente
                    cur=cur  # Reutiliza conexão existente
                )
                
                # IMPORTANTE: get_ingredient_max_available_quantity já retorna o menor entre regra e estoque
                # Para ingredientes base (portions > 0), retorna o total de porções possíveis
                # Para extras (portions = 0), retorna apenas extras disponíveis (sem incluir min_quantity)
                
                max_available_from_function = max_available_info.get('max_available', 0) if max_available_info else 0
                
                # Debug: log para ingredientes base problemáticos
                if portions > 0 and ing_id == 28:
                    logger.debug(
                        f"[get_product_by_id] Ingrediente base {ing_id} (portions={portions}): "
                        f"max_quantity_rule={max_quantity_rule}, "
                        f"base_portions_for_calculation={base_portions_for_calculation}, "
                        f"max_available_from_function={max_available_from_function}, "
                        f"limited_by={max_available_info.get('limited_by') if max_available_info else 'N/A'}"
                    )
                
                if portions == 0.0:  # É ingrediente extra
                    min_qty = int(r[3]) if r[3] is not None else 0
                    # max_available_from_function é apenas extras, então precisa somar com min_quantity
                    max_from_stock_total = min_qty + max_available_from_function if max_available_from_function > 0 else min_qty
                    
                    # Retorna o menor entre: quantidade baseada no estoque e quantidade máxima da regra
                    if max_quantity_rule is not None and max_quantity_rule > 0:
                        # Compara quantidade baseada no estoque com a regra e retorna o menor
                        effective_max_quantity = min(max_from_stock_total, max_quantity_rule)
                    else:
                        # Sem limite de regra, usa apenas a quantidade baseada no estoque
                        effective_max_quantity = max_from_stock_total
                else:  # É ingrediente base
                    # max_available_from_function já é o total de porções possíveis
                    # A função get_ingredient_max_available_quantity já retorna o menor entre regra e estoque
                    # Então podemos usar diretamente o valor retornado
                    effective_max_quantity = max_available_from_function if max_available_from_function > 0 else None
                
                ingredients_data.append({
                    "id": ing_id,  # Adiciona id para compatibilidade com mobile
                    "ingredient_id": ing_id,
                    "name": r[1],
                    "portions": portions,
                    "min_quantity": int(r[3]) if r[3] is not None else 0,
                    "max_quantity": effective_max_quantity,  # Menor entre regra e estoque (já calculado)
                    "additional_price": float(r[5]) if r[5] is not None else 0.0,
                    "is_available": bool(r[6]),
                    "availability_info": max_available_info if portions == 0.0 else None  # Info adicional para extras
                })
            
            product["ingredients"] = ingredients_data

            return product
        return None  
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar produto por ID: {e}", exc_info=True)  
        return None  
    finally:  
        if conn: conn.close()  


def update_product(product_id, update_data):  
    allowed_fields = ['name', 'description', 'price', 'cost_price', 'preparation_time_minutes', 'is_active', 'category_id']  
    fields_to_update = {k: v for k, v in update_data.items() if k in allowed_fields}  
    new_ingredients = update_data.get('ingredients') if isinstance(update_data, dict) else None
    if not fields_to_update:  
        # Permite atualizar apenas ingredientes
        if new_ingredients is None:
            return (False, "NO_VALID_FIELDS", "Nenhum campo válido para atualização foi fornecido")  
    if 'name' in fields_to_update:  
        name = fields_to_update['name']  
        if not name or not name.strip():  
            return (False, "INVALID_NAME", "Nome do produto é obrigatório")  
    if 'price' in fields_to_update:  
        price = fields_to_update['price']  
        if price is None or price <= 0:  
            return (False, "INVALID_PRICE", "Preço deve ser maior que zero")  
    if 'cost_price' in fields_to_update:  
        cost_price = fields_to_update['cost_price']  
        if cost_price is not None and cost_price < 0:  
            return (False, "INVALID_COST_PRICE", "Preço de custo não pode ser negativo")  
    if 'preparation_time_minutes' in fields_to_update:  
        prep_time = fields_to_update['preparation_time_minutes']  
        if prep_time is not None and prep_time < 0:  
            return (False, "INVALID_PREP_TIME", "Tempo de preparo não pode ser negativo")  
    if 'category_id' in fields_to_update:  
        category_id = fields_to_update['category_id']  
        if category_id == -1:  # Valor especial para remoção de categoria
            # Remove a categoria (define como NULL no banco)
            fields_to_update['category_id'] = None
        elif category_id is None:  
            return (False, "INVALID_CATEGORY", "Categoria é obrigatória")  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        sql_check_exists = "SELECT 1 FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"  
        cur.execute(sql_check_exists, (product_id,))  
        if not cur.fetchone():  
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado")  
        if 'name' in fields_to_update:  
            sql_check_name = "SELECT ID FROM PRODUCTS WHERE UPPER(NAME) = UPPER(?) AND ID <> ? AND IS_ACTIVE = TRUE;"  
            cur.execute(sql_check_name, (fields_to_update['name'], product_id))  
            if cur.fetchone():  
                return (False, "PRODUCT_NAME_EXISTS", "Já existe um produto com este nome")  
        if 'category_id' in fields_to_update and fields_to_update['category_id'] is not None:  
            cur.execute("SELECT 1 FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (fields_to_update['category_id'],))  
            if not cur.fetchone():  
                return (False, "CATEGORY_NOT_FOUND", "Categoria informada não existe ou está inativa")  
        set_parts = [f"{key} = ?" for key in fields_to_update]  
        values = list(fields_to_update.values())  
        values.append(product_id)  
        price_updated = 'price' in fields_to_update
        if set_parts:
            sql = f"UPDATE PRODUCTS SET {', '.join(set_parts)} WHERE ID = ? AND IS_ACTIVE = TRUE;"  
            cur.execute(sql, tuple(values))  

        # Atualização das regras de ingredientes, se fornecidas
        if new_ingredients is not None:
            # Busca estado atual
            cur.execute(
                "SELECT INGREDIENT_ID, PORTIONS, MIN_QUANTITY, MAX_QUANTITY FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ?",
                (product_id,)
            )
            current = {row[0]: {
                "portions": float(row[1]) if row[1] is not None else 0.0,
                "min_quantity": int(row[2]) if row[2] is not None else 0,
                "max_quantity": int(row[3]) if row[3] is not None else 0
            } for row in cur.fetchall()}

            # Normaliza nova lista
            desired = {}
            for item in (new_ingredients or []):
                ingredient_id = item.get('ingredient_id')
                portions = item.get('portions', 0)
                min_quantity = item.get('min_quantity', 0)
                max_quantity = item.get('max_quantity', 0)

                if ingredient_id is None:
                    return (False, "INVALID_INGREDIENTS", "ingredient_id é obrigatório")
                if portions is None or portions < 0:
                    return (False, "INVALID_INGREDIENTS", "portions deve ser >= 0")
                if min_quantity is None or min_quantity < 0:
                    return (False, "INVALID_INGREDIENTS", "min_quantity deve ser >= 0")
                if max_quantity is None or max_quantity < 0:
                    return (False, "INVALID_INGREDIENTS", "max_quantity deve ser >= 0")
                if max_quantity and min_quantity and max_quantity < min_quantity:
                    return (False, "INVALID_INGREDIENTS", "max_quantity não pode ser menor que min_quantity")

                desired[ingredient_id] = {
                    "portions": float(portions),
                    "min_quantity": int(min_quantity),
                    "max_quantity": int(max_quantity)
                }

            current_ids = set(current.keys())
            desired_ids = set(desired.keys())

            # Deletar removidos
            to_delete = current_ids - desired_ids
            if to_delete:
                # ALTERAÇÃO: Construção segura de placeholders - apenas IDs validados são usados
                # to_delete contém apenas IDs de ingredientes já validados no loop anterior
                placeholders = ', '.join(['?' for _ in to_delete])
                cur.execute(
                    f"DELETE FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ? AND INGREDIENT_ID IN ({placeholders})",
                    (product_id, *tuple(to_delete))
                )

            # Inserir adicionados
            to_insert = desired_ids - current_ids
            for ing_id in to_insert:
                vals = desired[ing_id]
                # valida existência do ingrediente
                cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ing_id,))
                if not cur.fetchone():
                    return (False, "INGREDIENT_NOT_FOUND", f"Ingrediente {ing_id} não encontrado")
                cur.execute(
                    """
                    INSERT INTO PRODUCT_INGREDIENTS (PRODUCT_ID, INGREDIENT_ID, PORTIONS, MIN_QUANTITY, MAX_QUANTITY)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (product_id, ing_id, vals['portions'], vals['min_quantity'], vals['max_quantity'])
                )

            # Atualizar alterados
            to_update = current_ids & desired_ids
            for ing_id in to_update:
                cur_vals = current[ing_id]
                new_vals = desired[ing_id]
                if (cur_vals['portions'] != new_vals['portions'] or
                    cur_vals['min_quantity'] != new_vals['min_quantity'] or
                    cur_vals['max_quantity'] != new_vals['max_quantity']):
                    cur.execute(
                        """
                        UPDATE PRODUCT_INGREDIENTS
                        SET PORTIONS = ?, MIN_QUANTITY = ?, MAX_QUANTITY = ?
                        WHERE PRODUCT_ID = ? AND INGREDIENT_ID = ?
                        """,
                        (new_vals['portions'], new_vals['min_quantity'], new_vals['max_quantity'], product_id, ing_id)
                    )
        
        # ALTERAÇÃO: Valida receita completa antes de commitar
        # Verifica se produto tem pelo menos um ingrediente obrigatório (PORTIONS > 0)
        if new_ingredients is not None:
            cur.execute("""
                SELECT COUNT(*) FROM PRODUCT_INGREDIENTS
                WHERE PRODUCT_ID = ? AND PORTIONS > 0
            """, (product_id,))
            required_ingredients_count = cur.fetchone()[0] or 0
            
            if required_ingredients_count == 0:
                conn.rollback()
                return (False, "INCOMPLETE_RECIPE", "Produto deve ter pelo menos um ingrediente obrigatório (PORTIONS > 0) na receita")

        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após atualizar produto
        _invalidate_product_cache()
        
        # Se o preço foi atualizado, recalcula os descontos das promoções após o commit
        if price_updated:
            try:
                from . import promotion_service
                promotion_service.recalculate_promotion_discount_value(product_id)
            except Exception as e:
                # ALTERAÇÃO: Logger já está definido no topo do módulo
                logger.warning(f"Erro ao recalcular desconto da promoção: {e}", exc_info=True)
                # Não falha a atualização do produto se o recálculo falhar
        
        return (True, None, "Produto atualizado com sucesso")  
    except fdb.Error as e:  
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao atualizar produto: {e}", exc_info=True)  
        if conn: conn.rollback()  
        return (False, "DATABASE_ERROR", "Erro interno do servidor")  
    except ValueError as ve:
        if conn: conn.rollback()
        return (False, "INVALID_INGREDIENTS", str(ve))
    finally:  
        if conn: conn.close()  


def deactivate_product(product_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Primeiro verifica se o produto existe
        sql_check = "SELECT ID FROM PRODUCTS WHERE ID = ?;"
        cur.execute(sql_check, (product_id,))
        if not cur.fetchone():
            return False  # Produto não existe
        
        # Atualiza o produto para inativo
        sql = "UPDATE PRODUCTS SET IS_ACTIVE = FALSE WHERE ID = ?;"  
        cur.execute(sql, (product_id,))  
        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após inativar produto
        _invalidate_product_cache()
        
        return True  # Sempre retorna True se o produto existe
    except fdb.Error as e:  
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao inativar produto: {e}", exc_info=True)  
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()  


def update_product_image_url(product_id, image_url):
    """Atualiza a URL da imagem do produto no banco de dados"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o produto existe
        sql_check = "SELECT ID FROM PRODUCTS WHERE ID = ?;"
        cur.execute(sql_check, (product_id,))
        if not cur.fetchone():
            return False  # Produto não existe
        
        # Atualiza a URL da imagem
        sql = "UPDATE PRODUCTS SET IMAGE_URL = ? WHERE ID = ?;"
        cur.execute(sql, (image_url, product_id))
        conn.commit()
        return True
    except fdb.Error as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao atualizar URL da imagem: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def reactivate_product(product_id):  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Primeiro verifica se o produto existe
        sql_check = "SELECT ID FROM PRODUCTS WHERE ID = ?;"
        cur.execute(sql_check, (product_id,))
        if not cur.fetchone():
            return False  # Produto não existe
        
        # Atualiza o produto para ativo
        sql = "UPDATE PRODUCTS SET IS_ACTIVE = TRUE WHERE ID = ?;"  
        cur.execute(sql, (product_id,))
        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após reativar produto
        _invalidate_product_cache()
        
        return True  # Sempre retorna True se o produto existe
    except fdb.Error as e:  
        # Uso de logger estruturado evita prints e expõe stack de forma controlada
        logger.exception("Erro ao reativar produto")
        if conn: conn.rollback()  
        return False  
    finally:  
        if conn: conn.close()


def search_products(name=None, category_id=None, page=1, page_size=10, include_inactive=False):  
    # Alias para list_products com mesmos filtros — mantém rota semanticamente distinta
    return list_products(name_filter=name, category_id=category_id, page=page, page_size=page_size, include_inactive=include_inactive)



def get_products_by_category_id(category_id, page=1, page_size=10, include_inactive=False, filter_unavailable=True):  
    """
    Busca produtos por ID da categoria específica
    """
    page = max(int(page or 1), 1)  
    page_size = max(int(page_size or 10), 1)  
    offset = (page - 1) * page_size  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        
        # Primeiro verifica se a categoria existe
        cur.execute("SELECT ID, NAME FROM CATEGORIES WHERE ID = ? AND IS_ACTIVE = TRUE;", (category_id,))  
        category_row = cur.fetchone()
        if not category_row:
            return (None, "CATEGORY_NOT_FOUND", "Categoria não encontrada ou inativa")
        
        category_name = category_row[1]
        
        # Monta a query para buscar produtos
        # IMPORTANTE: Sempre usar prefixo p. para evitar ambiguidade com tabela CATEGORIES no JOIN
        where_clauses = ["p.CATEGORY_ID = ?"]
        params = [category_id]
        
        if not include_inactive:
            where_clauses.append("p.IS_ACTIVE = TRUE")
            
        where_sql = " AND ".join(where_clauses)
        
        # Conta total de produtos na categoria
        # ALTERAÇÃO: Query parametrizada - where_sql é construído de forma segura (apenas cláusulas fixas)
        # Remove prefixo p. para a query de COUNT que não usa JOIN
        # IMPORTANTE: Garantir que IS_ACTIVE seja referenciado corretamente na query de COUNT
        # Construir query de COUNT de forma explícita para evitar ambiguidade
        count_where_clauses = ["CATEGORY_ID = ?"]
        if not include_inactive:
            count_where_clauses.append("IS_ACTIVE = TRUE")
        count_where_sql = " AND ".join(count_where_clauses)
        cur.execute(f"SELECT COUNT(*) FROM PRODUCTS WHERE {count_where_sql};", tuple(params))  
        total = cur.fetchone()[0] or 0  
        
        # Busca os produtos paginados - Query com sintaxe FIRST/SKIP do Firebird
        # OTIMIZAÇÃO: Incluir nome da categoria via LEFT JOIN para evitar N+1
        # IMPORTANTE: Especificar explicitamente p.IS_ACTIVE para evitar ambiguidade com c.IS_ACTIVE
        query = f"""
            SELECT FIRST {page_size} SKIP {offset} 
                p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.COST_PRICE, 
                p.PREPARATION_TIME_MINUTES, p.CATEGORY_ID, p.IMAGE_URL, p.IS_ACTIVE,
                COALESCE(c.NAME, 'Sem categoria') as CATEGORY_NAME
            FROM PRODUCTS p
            LEFT JOIN CATEGORIES c ON p.CATEGORY_ID = c.ID
            WHERE {where_sql}
            ORDER BY p.NAME
        """
        cur.execute(query, tuple(params))  
        
        # Coleta todos os product_ids primeiro
        product_rows = cur.fetchall()
        product_ids = [row[0] for row in product_rows]
        items = []
        
        # Inicializa estruturas para armazenar dados batch
        availability_map = {}
        ingredients_map = {}
        
        # OTIMIZAÇÃO: Busca todos os status de disponibilidade de uma vez
        if product_ids:
            try:
                placeholders = ', '.join(['?' for _ in product_ids])
                # CORREÇÃO: Query melhorada - busca apenas ingredientes obrigatórios (portions > 0)
                # Ingredientes extras (portions = 0) não afetam a disponibilidade do produto
                availability_query = f"""
                    SELECT 
                        pi.PRODUCT_ID,
                        MIN(CASE 
                            WHEN i.IS_AVAILABLE = FALSE 
                                 OR i.STOCK_STATUS = 'out_of_stock' 
                                 OR (i.CURRENT_STOCK IS NOT NULL AND i.CURRENT_STOCK = 0)
                            THEN 0 
                            ELSE 1 
                        END) as all_available,
                        MIN(CASE WHEN i.STOCK_STATUS = 'low' OR (i.CURRENT_STOCK IS NOT NULL AND i.MIN_STOCK_THRESHOLD IS NOT NULL AND i.CURRENT_STOCK <= i.MIN_STOCK_THRESHOLD) THEN 1 ELSE 0 END) as has_low_stock,
                        COUNT(pi.INGREDIENT_ID) as ingredient_count
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID IN ({placeholders})
                      AND pi.PORTIONS > 0
                    GROUP BY pi.PRODUCT_ID
                """
                cur.execute(availability_query, tuple(product_ids))
                products_with_ingredients = set()
                for row in cur.fetchall():
                    product_id = row[0]
                    all_av = row[1]
                    has_low = row[2]
                    ingredient_count = row[3]
                    products_with_ingredients.add(product_id)
                    
                    # CORREÇÃO: Tratar NULL como disponível
                    if all_av is None:
                        availability_map[product_id] = "available"
                    elif all_av == 0:
                        # Log para debug quando produto está indisponível
                        # CORREÇÃO: Busca apenas ingredientes obrigatórios indisponíveis para log
                        cur.execute("""
                            SELECT i.ID, i.NAME, i.IS_AVAILABLE, i.STOCK_STATUS, i.CURRENT_STOCK, pi.PORTIONS
                            FROM PRODUCT_INGREDIENTS pi
                            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                            WHERE pi.PRODUCT_ID = ? 
                              AND pi.PORTIONS > 0
                              AND (i.IS_AVAILABLE = FALSE 
                                   OR i.STOCK_STATUS = 'out_of_stock' 
                                   OR (i.CURRENT_STOCK IS NOT NULL AND i.CURRENT_STOCK = 0))
                        """, (product_id,))
                        unavailable_ingredients = cur.fetchall()
                        if unavailable_ingredients:
                            logger.warning(f"[get_products_by_category_id] Produto {product_id} marcado como unavailable. Ingredientes obrigatórios indisponíveis: {[f'{ing[1]} (ID:{ing[0]}, IS_AVAILABLE:{ing[2]}, STOCK_STATUS:{ing[3]}, CURRENT_STOCK:{ing[4]}, PORTIONS:{ing[5]})' for ing in unavailable_ingredients]}")
                        else:
                            # Se não encontrou ingredientes indisponíveis mas all_av = 0, pode ser problema na query
                            logger.warning(f"[get_products_by_category_id] Produto {product_id} marcado como unavailable mas nenhum ingrediente obrigatório indisponível encontrado. Verificando todos os ingredientes obrigatórios...")
                            cur.execute("""
                                SELECT i.ID, i.NAME, i.IS_AVAILABLE, i.STOCK_STATUS, i.CURRENT_STOCK, pi.PORTIONS
                                FROM PRODUCT_INGREDIENTS pi
                                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                                WHERE pi.PRODUCT_ID = ? AND pi.PORTIONS > 0
                            """, (product_id,))
                            all_required = cur.fetchall()
                            logger.warning(f"[get_products_by_category_id] Todos os ingredientes obrigatórios do produto {product_id}: {[f'{ing[1]} (ID:{ing[0]}, IS_AVAILABLE:{ing[2]}, STOCK_STATUS:{ing[3]}, CURRENT_STOCK:{ing[4]}, PORTIONS:{ing[5]})' for ing in all_required]}")
                        availability_map[product_id] = "unavailable"
                    elif has_low == 1:
                        availability_map[product_id] = "low_stock"
                    else:
                        availability_map[product_id] = "available"
                
                # Produtos sem ingredientes são considerados disponíveis (não dependem de estoque)
                for product_id in product_ids:
                    if product_id not in products_with_ingredients:
                        availability_map[product_id] = "available"
                        logger.debug(f"[get_products_by_category_id] Produto {product_id} sem ingredientes cadastrados, marcado como available")
            except Exception as e:
                # ALTERAÇÃO: Substituído print() por logging estruturado
                logger.error(f"Erro ao buscar disponibilidade em batch: {e}", exc_info=True)
        
        # OTIMIZAÇÃO: Busca todos os ingredientes de uma vez
        if product_ids:
            try:
                placeholders = ', '.join(['?' for _ in product_ids])
                ingredients_query = f"""
                    SELECT pi.PRODUCT_ID, pi.INGREDIENT_ID, pi.PORTIONS, pi.MIN_QUANTITY, pi.MAX_QUANTITY
                    FROM PRODUCT_INGREDIENTS pi
                    WHERE pi.PRODUCT_ID IN ({placeholders})
                    ORDER BY pi.PRODUCT_ID, pi.INGREDIENT_ID
                """
                cur.execute(ingredients_query, tuple(product_ids))
                for row in cur.fetchall():
                    product_id = row[0]
                    if product_id not in ingredients_map:
                        ingredients_map[product_id] = []
                    ingredients_map[product_id].append({
                        "ingredient_id": row[1],
                        "portions": float(row[2]) if row[2] is not None else 0.0,
                        "min_quantity": int(row[3]) if row[3] is not None else 0,
                        "max_quantity": int(row[4]) if row[4] is not None else 0
                    })
            except Exception as e:
                # ALTERAÇÃO: Logger já está definido no topo do módulo
                logger.warning(f"Erro ao buscar ingredientes em batch: {e}", exc_info=True)
        
        # Processa os produtos com os dados já carregados
        for row in product_rows:
            product_id = row[0]
            
            # CORREÇÃO: Filtrar produtos indisponíveis apenas no GET (não desativa no banco)
            # Verifica availability_status antes de adicionar à lista
            # Aplica filtro apenas se filter_unavailable=True (usuários normais)
            availability_status = availability_map.get(product_id, "unknown")
            if filter_unavailable and availability_status == "unavailable":
                # Produto indisponível - não incluir na listagem para usuários normais
                # Mas não desativa no banco (IS_ACTIVE permanece TRUE)
                # Administradores ainda veem todos os produtos
                continue
            
            item = {  
                "id": product_id,  
                "name": row[1],  
                "description": row[2],  
                "price": str(row[3]),  
                "cost_price": str(row[4]) if row[4] else "0.00",  
                "preparation_time_minutes": row[5] if row[5] else 0,  
                "category_id": row[6],
                "is_active": row[8] if len(row) > 8 else True,
                "category_name": row[9] if len(row) > 9 and row[9] else "Sem categoria"
            }
            # Adiciona URL da imagem do banco se existir
            if row[7]:  # IMAGE_URL
                item["image_url"] = row[7]
                try:
                    item["image_hash"] = _get_image_hash(row[7])
                except Exception as e:
                    # ALTERAÇÃO: Logger já está definido no topo do módulo
                    logger.warning(f"Erro ao gerar hash da imagem: {e}", exc_info=True)
                    item["image_hash"] = None
            
            # Adiciona status de disponibilidade (já carregado em batch)
            item["availability_status"] = availability_status
            
            # Adiciona ingredientes (já carregados em batch)
            item["ingredients"] = ingredients_map.get(product_id, [])
            
            items.append(item)  
        
        # CORREÇÃO: Ajustar total após filtrar produtos indisponíveis
        # Se filter_unavailable=True, ajusta o total para refletir apenas produtos disponíveis
        # Se filter_unavailable=False (admin), usa o total original
        if filter_unavailable:
            filtered_total = len(items)
            total_pages = (filtered_total + page_size - 1) // page_size if filtered_total > 0 else 0
            pagination_total = filtered_total
        else:
            # Admin vê todos os produtos, usa total original
            total_pages = (total + page_size - 1) // page_size
            pagination_total = total
        
        result = {  
            "category": {
                "id": category_id,
                "name": category_name
            },
            "items": items,  
            "pagination": {  
                "total": pagination_total,
                "page": page,  
                "page_size": page_size,  
                "total_pages": total_pages  
            }  
        }
        
        return (result, None, None)
        
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar produtos por categoria (Firebird): {e}", exc_info=True)  
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        # Captura qualquer outra exceção não relacionada ao banco de dados
        logger.error(f"Erro ao buscar produtos por categoria: {e}", exc_info=True)
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:  
        if conn: conn.close()


def get_menu_summary():  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        # CORREÇÃO: Adicionar CASTs explícitos e COALESCE para evitar erro SQLDA -804
        cur.execute("SELECT CAST(COUNT(*) AS INTEGER) FROM PRODUCTS WHERE IS_ACTIVE = TRUE")  
        total_items = cur.fetchone()[0] or 0
        cur.execute("SELECT CAST(COALESCE(AVG(PRICE), 0) AS NUMERIC(18,2)) FROM PRODUCTS WHERE IS_ACTIVE = TRUE AND PRICE > 0")  
        price_result = cur.fetchone()  
        avg_price = float(price_result[0]) if price_result and price_result[0] is not None else 0.0  
        cur.execute("""
            SELECT CAST(COALESCE(AVG(PRICE - COST_PRICE), 0) AS NUMERIC(18,2))
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PRICE > 0 AND COST_PRICE > 0
        """)  
        margin_result = cur.fetchone()  
        avg_margin = float(margin_result[0]) if margin_result and margin_result[0] is not None else 0.0  
        cur.execute("""
            SELECT CAST(COALESCE(AVG(PREPARATION_TIME_MINUTES), 0) AS NUMERIC(18,2))
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PREPARATION_TIME_MINUTES > 0
        """)  
        prep_result = cur.fetchone()  
        avg_prep_time = float(prep_result[0]) if prep_result and prep_result[0] is not None else 0.0  
        return {  
            "total_items": total_items,
            "average_price": round(avg_price, 2),
            "average_margin": round(avg_margin, 2),
            "average_preparation_time": round(avg_prep_time, 1)
        }
    except fdb.Error as e:  
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao buscar resumo do cardápio: {e}", exc_info=True)  
        return {  
            "total_items": 0,
            "average_price": 0.0,
            "average_margin": 0.0,
            "average_preparation_time": 0.0
        }
    finally:  
        if conn: conn.close()


def calculate_product_cost_by_ingredients(product_id):
    """
    Calcula o custo do produto baseado nas porções dos ingredientes
    """
    from .ingredient_service import calculate_product_cost_by_portions
    return calculate_product_cost_by_portions(product_id)


def consume_ingredients_for_sale(product_id, quantity=1):
    """
    Consome ingredientes do estoque quando um produto é vendido
    """
    from .ingredient_service import consume_ingredients_for_product
    return consume_ingredients_for_product(product_id, quantity)


def get_product_ingredients_with_costs(product_id):
    """
    Retorna os ingredientes do produto com cálculos de custo baseados em porções
    """
    from .ingredient_service import get_ingredients_for_product
    # Mantém retorno existente (custos com porções), porém tabela já possui min/max
    return get_ingredients_for_product(product_id)


def delete_product(product_id):
    """
    Exclui permanentemente um produto e todos os seus relacionamentos
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Verificar se o produto existe
        cur.execute("SELECT ID, NAME FROM PRODUCTS WHERE ID = ?", (product_id,))
        product = cur.fetchone()
        if not product:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado")
        
        product_name = product[1]
        
        # 2. Verificar se o produto tem pedidos associados
        cur.execute("""
            SELECT COUNT(*) FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE oi.PRODUCT_ID = ? AND o.STATUS NOT IN ('cancelled', 'delivered')
        """, (product_id,))
        active_orders = cur.fetchone()[0] or 0
        
        if active_orders > 0:
            return (False, "PRODUCT_IN_ACTIVE_ORDERS", 
                   f"Produto não pode ser excluído pois possui {active_orders} pedido(s) ativo(s)")
        
        # 3. Verificar se o produto tem itens no carrinho
        cur.execute("""
            SELECT COUNT(*) FROM CART_ITEMS ci
            JOIN CARTS c ON ci.CART_ID = c.ID
            WHERE ci.PRODUCT_ID = ? AND c.IS_ACTIVE = TRUE
        """, (product_id,))
        cart_items = cur.fetchone()[0] or 0
        
        if cart_items > 0:
            return (False, "PRODUCT_IN_CART", 
                   f"Produto não pode ser excluído pois está em {cart_items} carrinho(s) ativo(s)")
        
        # 4. Remover ingredientes relacionados (PRODUCT_INGREDIENTS)
        cur.execute("DELETE FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ?", (product_id,))
        ingredients_removed = cur.rowcount
        
        # 5. Remover extras relacionados (ORDER_ITEM_EXTRAS) - se existir
        cur.execute("""
            DELETE FROM ORDER_ITEM_EXTRAS 
            WHERE ORDER_ITEM_ID IN (
                SELECT ID FROM ORDER_ITEMS WHERE PRODUCT_ID = ?
            )
        """, (product_id,))
        extras_removed = cur.rowcount
        
        # 6. Remover itens de pedido relacionados (ORDER_ITEMS)
        cur.execute("DELETE FROM ORDER_ITEMS WHERE PRODUCT_ID = ?", (product_id,))
        order_items_removed = cur.rowcount
        
        # 7. Remover itens do carrinho relacionados (CART_ITEMS)
        cur.execute("DELETE FROM CART_ITEMS WHERE PRODUCT_ID = ?", (product_id,))
        cart_items_removed = cur.rowcount
        
        # 8. Remover extras do carrinho relacionados (CART_ITEM_EXTRAS) - se existir
        cur.execute("""
            DELETE FROM CART_ITEM_EXTRAS 
            WHERE CART_ITEM_ID IN (
                SELECT ID FROM CART_ITEMS WHERE PRODUCT_ID = ?
            )
        """, (product_id,))
        cart_extras_removed = cur.rowcount
        
        # 9. Finalmente, excluir o produto
        cur.execute("DELETE FROM PRODUCTS WHERE ID = ?", (product_id,))
        product_removed = cur.rowcount
        
        if product_removed == 0:
            return (False, "DELETE_FAILED", "Falha ao excluir o produto")
        
        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após deletar produto
        _invalidate_product_cache()
        
        # 10. Remover imagem do produto se existir
        try:
            from ..utils.image_handler import delete_product_image
            delete_product_image(product_id)
        except Exception as e:
            # ALTERAÇÃO: Logger já está definido no topo do módulo
            logger.warning(f"Erro ao remover imagem do produto {product_id}: {e}", exc_info=True)
        
        return (True, None, {
            "message": f"Produto '{product_name}' excluído permanentemente",
            "details": {
                "ingredients_removed": ingredients_removed,
                "order_items_removed": order_items_removed,
                "cart_items_removed": cart_items_removed,
                "extras_removed": extras_removed,
                "cart_extras_removed": cart_extras_removed
            }
        })
        
    except fdb.Error as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao excluir produto: {e}", exc_info=True)
        if conn: 
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro geral ao excluir produto: {e}", exc_info=True)
        if conn: 
            conn.rollback()
        return (False, "GENERAL_ERROR", "Erro interno do servidor")
    finally:
        if conn: 
            conn.close()  


def apply_group_to_product(product_id, group_id, default_min_quantity=0, default_max_quantity=1):
    """
    Aplica um template de grupo ao produto inserindo ingredientes como extras (PORTIONS=0)
    e regras padrão (min/max). Retorna lista dos ingredientes adicionados.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica produto
        cur.execute("SELECT 1 FROM PRODUCTS WHERE ID = ?", (product_id,))
        if not cur.fetchone():
            return (None, "PRODUCT_NOT_FOUND", "Produto não encontrado")

        # Carrega ingredientes do grupo
        group_ingredients = groups_service.get_ingredients_for_group(group_id)
        if group_ingredients is None:
            return (None, "GROUP_NOT_FOUND", "Grupo não encontrado")

        ingredient_ids = [gi.get('id') for gi in (group_ingredients or []) if gi and gi.get('id') is not None]
        if not ingredient_ids:
            return ([], None, "Nenhum ingrediente para aplicar")

        # Busca existentes
        cur.execute("SELECT INGREDIENT_ID FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID = ?", (product_id,))
        existing_ids = {row[0] for row in cur.fetchall()}

        added = []
        for ing_id in ingredient_ids:
            if ing_id in existing_ids:
                continue
            # valida existência do ingrediente
            cur.execute("SELECT 1 FROM INGREDIENTS WHERE ID = ?", (ing_id,))
            if not cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO PRODUCT_INGREDIENTS (PRODUCT_ID, INGREDIENT_ID, PORTIONS, MIN_QUANTITY, MAX_QUANTITY)
                VALUES (?, ?, 0, ?, ?)
                """,
                (product_id, ing_id, default_min_quantity, default_max_quantity)
            )
            added.append(ing_id)

        conn.commit()
        return (added, None, None)
    except fdb.Error as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao aplicar grupo ao produto: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn:
            conn.close()


def get_most_ordered_products(page=1, page_size=10):
    """
    Busca os produtos mais pedidos baseado no histórico de pedidos.
    Retorna produtos ordenados por quantidade total de itens vendidos.
    Utiliza paginação padrão do sistema.
    """
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 10), 1)
    offset = (page - 1) * page_size
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO: Conta total de produtos com vendas - considerar pedidos entregues E completos
        cur.execute("""
            SELECT COUNT(DISTINCT p.ID)
            FROM PRODUCTS p
            INNER JOIN ORDER_ITEMS oi ON p.ID = oi.PRODUCT_ID
            INNER JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE p.IS_ACTIVE = TRUE 
              AND o.STATUS IN ('delivered', 'completed')
        """)
        total = cur.fetchone()[0] or 0
        
        # ALTERAÇÃO: Query paginada que conta quantidades vendidas - incluir campos necessários para exibição
        # ALTERAÇÃO: Considerar pedidos entregues E completos conforme roteiro
        # ALTERAÇÃO: Firebird não suporta FETCH FIRST com placeholders, usar interpolação segura
        query = f"""
            SELECT FIRST {page_size} SKIP {offset}
                p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.IMAGE_URL, 
                p.PREPARATION_TIME_MINUTES, p.CATEGORY_ID,
                SUM(oi.QUANTITY) as total_pedidos
            FROM PRODUCTS p
            INNER JOIN ORDER_ITEMS oi ON p.ID = oi.PRODUCT_ID
            INNER JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE p.IS_ACTIVE = TRUE 
              AND o.STATUS IN ('delivered', 'completed')
            GROUP BY p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.IMAGE_URL, p.PREPARATION_TIME_MINUTES, p.CATEGORY_ID
            ORDER BY total_pedidos DESC
        """
        cur.execute(query)
        
        items = []
        for row in cur.fetchall():
            items.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": str(row[3]),
                "image_url": row[4] if row[4] else None,
                "preparation_time_minutes": row[5] if row[5] else 0,
                "category_id": row[6] if row[6] else None,
                "is_active": True,  # Já filtrado na query
                "total_pedidos": int(row[7]) if row[7] else 0
            })
            
            # Adiciona hash da imagem se existir
            if row[4]:
                try:
                    items[-1]["image_hash"] = _get_image_hash(row[4])
                except Exception:
                    items[-1]["image_hash"] = None
        
        total_pages = (total + page_size - 1) // page_size
        
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }
        
    except fdb.Error as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao buscar produtos mais pedidos: {e}", exc_info=True)
        return {
            "items": [],
            "pagination": {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
        }
    finally:
        if conn:
            conn.close()


def get_recently_added_products(page=1, page_size=10, days=30):
    """
    Busca os produtos mais recentemente adicionados ao catálogo.
    Retorna produtos criados nos últimos N dias, ordenados por data de criação descendente.
    
    Args:
        page: Número da página (padrão: 1)
        page_size: Tamanho da página (padrão: 10)
        days: Período em dias para considerar como novidade (padrão: 30 dias)
    
    Returns:
        Dict com items (lista de produtos) e pagination (metadados de paginação)
    """
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 10), 1)
    days = max(int(days or 30), 1)  # Mínimo 1 dia, padrão 30 dias
    offset = (page - 1) * page_size
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO: Calcula data limite baseada no período configurado
        # Produtos considerados novidades são aqueles criados nos últimos N dias
        date_limit = datetime.now() - timedelta(days=days)
        
        # ALTERAÇÃO: Conta total de produtos ativos criados no período
        # Se CREATED_AT for NULL (produtos antigos sem data), não são considerados novidades
        cur.execute("""
            SELECT COUNT(*) FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE 
            AND CREATED_AT IS NOT NULL
            AND CREATED_AT >= ?
        """, (date_limit,))
        total = cur.fetchone()[0] or 0
        
        # ALTERAÇÃO: Query paginada que busca produtos ativos ordenados por CREATED_AT descendente
        # Filtra apenas produtos criados nos últimos N dias
        # ALTERAÇÃO: Firebird não suporta FETCH FIRST com placeholders, usar interpolação segura
        query = f"""
            SELECT FIRST {page_size} SKIP {offset}
                p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.IMAGE_URL,
                p.PREPARATION_TIME_MINUTES, p.CATEGORY_ID,
                c.NAME as CATEGORY_NAME, p.CREATED_AT
            FROM PRODUCTS p
            LEFT JOIN CATEGORIES c ON p.CATEGORY_ID = c.ID
            WHERE p.IS_ACTIVE = TRUE
            AND p.CREATED_AT IS NOT NULL
            AND p.CREATED_AT >= ?
            ORDER BY p.CREATED_AT DESC
        """
        cur.execute(query, (date_limit,))
        
        items = []
        for row in cur.fetchall():
            created_at = row[8]  # CREATED_AT está na posição 8
            items.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": str(row[3]),
                "image_url": row[4] if row[4] else None,
                "preparation_time_minutes": row[5] if row[5] else 0,
                "category_id": row[6] if row[6] else None,
                "category_name": row[7] if row[7] else "Sem categoria",
                "created_at": created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else None,
                "is_active": True  # Já filtrado na query
            })
            
            # Adiciona hash da imagem se existir
            if row[4]:
                try:
                    items[-1]["image_hash"] = _get_image_hash(row[4])
                except Exception:
                    items[-1]["image_hash"] = None
        
        total_pages = (total + page_size - 1) // page_size
        
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }
        
    except fdb.Error as e:
        # ALTERAÇÃO: Logger já está definido no topo do módulo
        logger.error(f"Erro ao buscar produtos recentemente adicionados: {e}", exc_info=True)
        return {
            "items": [],
            "pagination": {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            }
        }
    finally:
        if conn:
            conn.close()
