import fdb  
from ..database import get_db_connection
from . import groups_service, stock_service
from ..utils.image_handler import get_product_image_url
from decimal import Decimal
from datetime import datetime
from functools import lru_cache  

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

        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após criar produto
        _invalidate_product_cache()
        
        return ({"id": new_product_id, "name": name, "description": description, "price": price, "cost_price": cost_price, "preparation_time_minutes": preparation_time_minutes, "category_id": category_id}, None, None)  
    except fdb.Error as e:  
        # ALTERAÇÃO: Substituído print() por logging estruturado
        import logging
        logger = logging.getLogger(__name__)
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
        print(f"Erro ao gerar hash da imagem: {e}")
    return None

def _get_product_availability_status(product_id, cur):
    """Verifica o status de disponibilidade do produto baseado no estoque dos ingredientes"""
    try:
        # Busca ingredientes do produto
        sql = """
            SELECT i.IS_AVAILABLE, i.STOCK_STATUS, i.CURRENT_STOCK, i.MIN_STOCK_THRESHOLD
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE
        """
        cur.execute(sql, (product_id,))
        ingredients = cur.fetchall()
        
        if not ingredients:
            return "unavailable"  # Produto sem ingredientes
        
        has_unavailable = False
        has_low_stock = False
        
        for is_available, stock_status, current_stock, min_threshold in ingredients:
            if not is_available or stock_status == 'out_of_stock':
                has_unavailable = True
                break
            elif stock_status == 'low' or (current_stock and min_threshold and current_stock <= min_threshold):
                has_low_stock = True
        
        if has_unavailable:
            return "unavailable"
        elif has_low_stock:
            return "low_stock"
        else:
            return "available"
            
    except Exception as e:
        print(f"Erro ao verificar disponibilidade do produto {product_id}: {e}")
        return "unknown"


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
        print(f"Erro ao verificar disponibilidade do produto {product_id}: {e}")
        return {
            'is_available': False,
            'status': 'unknown',
            'message': f'Erro ao verificar disponibilidade: {str(e)}',
            'ingredients': []
        }
    finally:
        if conn:
            conn.close()


def get_ingredient_max_available_quantity(ingredient_id, max_quantity_from_rule=None, item_quantity=1, cur=None):
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
        cur: Cursor opcional para reutilizar conexão (se None, cria nova conexão)
    
    Returns:
        dict: {
            'max_available': int,  # Quantidade máxima disponível
            'limited_by': str,  # 'rule' ou 'stock' ou 'both'
            'stock_info': {
                'current_stock': Decimal,
                'stock_unit': str,
                'base_portion_quantity': Decimal,
                'base_portion_unit': str
            }
        }
    """
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
        
        current_stock_decimal = Decimal(str(current_stock or 0))
        base_portion_quantity_decimal = Decimal(str(base_portion_quantity or 1))
        stock_unit_str = stock_unit or 'un'
        base_portion_unit_str = base_portion_unit or 'un'
        
        # Calcula quantidade máxima baseada no estoque
        # Precisa converter da unidade do estoque para a unidade da porção base
        max_from_stock = 0
        if current_stock_decimal > 0:
            try:
                # Converte estoque para unidade da porção base
                # Usa calculate_consumption_in_stock_unit de forma reversa
                # Para converter de stock_unit para base_portion_unit, usa a função interna
                from .stock_service import _convert_unit
                stock_in_base_unit = _convert_unit(
                    current_stock_decimal,
                    stock_unit_str,
                    base_portion_unit_str
                )
                
                # Calcula quantas porções base cabem no estoque disponível
                # Divide pelo item_quantity para ter a quantidade por item
                if base_portion_quantity_decimal > 0:
                    max_portions_from_stock = stock_in_base_unit / base_portion_quantity_decimal
                    # Arredonda para baixo e converte para int
                    max_from_stock = int(max_portions_from_stock // item_quantity)
            except Exception as e:
                print(f"Erro ao calcular quantidade máxima do estoque para ingrediente {ingredient_id}: {e}")
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
        print(f"Erro ao calcular quantidade máxima disponível do ingrediente {ingredient_id}: {e}")
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
_product_list_cache_ttl = 300  # 5 minutos de TTL

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

def list_products(name_filter=None, category_id=None, page=1, page_size=10, include_inactive=False):  
    """
    Lista produtos com cache em memória para melhor performance.
    Cache TTL: 5 minutos. Invalidado automaticamente quando produtos são modificados.
    """
    page = max(int(page or 1), 1)  
    page_size = max(int(page_size or 10), 1)  
    offset = (page - 1) * page_size  
    
    # OTIMIZAÇÃO: Verifica cache antes de consultar banco
    # Nota: Cache desabilitado para filtros de nome (busca dinâmica) e produtos inativos
    # Cache apenas para listagens padrão (sem filtro de nome, apenas ativos)
    use_cache = not name_filter and not include_inactive
    cache_key = _get_cache_key(name_filter, category_id, page, page_size, include_inactive)
    
    if use_cache and _is_cache_valid(cache_key) and cache_key in _product_list_cache:
        return _product_list_cache[cache_key]
    
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        where_clauses = [] if include_inactive else ["IS_ACTIVE = TRUE"]  
        params = []  
        if name_filter:  
            where_clauses.append("UPPER(NAME) LIKE UPPER(?)")  
            params.append(f"%{name_filter}%")  
        if category_id:  
            where_clauses.append("CATEGORY_ID = ?")  
            params.append(category_id)  
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"  
        # total  
        cur.execute(f"SELECT COUNT(*) FROM PRODUCTS WHERE {where_sql};", tuple(params))  
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
        ingredients_map = {}
        
        # OTIMIZAÇÃO: Busca todos os status de disponibilidade de uma vez
        if product_ids:
            try:
                placeholders = ', '.join(['?' for _ in product_ids])
                availability_query = f"""
                    SELECT 
                        pi.PRODUCT_ID,
                        MIN(CASE WHEN i.IS_AVAILABLE = FALSE OR i.STOCK_STATUS = 'out_of_stock' THEN 0 ELSE 1 END) as all_available,
                        MIN(CASE WHEN i.STOCK_STATUS = 'low' OR (i.CURRENT_STOCK <= i.MIN_STOCK_THRESHOLD) THEN 1 ELSE 0 END) as has_low_stock
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID IN ({placeholders})
                    GROUP BY pi.PRODUCT_ID
                """
                cur.execute(availability_query, tuple(product_ids))
                for row in cur.fetchall():
                    product_id = row[0]
                    all_av = row[1]
                    has_low = row[2]
                    if all_av == 0:
                        availability_map[product_id] = "unavailable"
                    elif has_low == 1:
                        availability_map[product_id] = "low_stock"
                    else:
                        availability_map[product_id] = "available"
            except Exception as e:
                print(f"Erro ao buscar disponibilidade em batch: {e}")
        
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
                print(f"Erro ao buscar ingredientes em batch: {e}")
        
        # Processa os produtos com os dados já carregados
        for row in product_rows:
            product_id = row[0]
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
                    print(f"Erro ao gerar hash da imagem: {e}")
                    item["image_hash"] = None
            
            # Adiciona status de disponibilidade (já carregado em batch)
            item["availability_status"] = availability_map.get(product_id, "unknown")
            
            # Adiciona ingredientes (já carregados em batch)
            item["ingredients"] = ingredients_map.get(product_id, [])
            
            items.append(item)  
        
        total_pages = (total + page_size - 1) // page_size  
        result = {  
            "items": items,  
            "pagination": {  
                "total": total,  
                "page": page,  
                "page_size": page_size,  
                "total_pages": total_pages  
            }  
        }
        
        # OTIMIZAÇÃO: Salva resultado no cache se for cacheável
        if use_cache:
            _product_list_cache[cache_key] = result
            _product_list_cache_timestamp[cache_key] = datetime.now()
        
        return result
    except fdb.Error as e:  
        print(f"Erro ao listar produtos: {e}")  
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


def get_product_by_id(product_id):  
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
                       i.ADDITIONAL_PRICE, i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON i.ID = pi.INGREDIENT_ID
                WHERE pi.PRODUCT_ID = ?
                ORDER BY i.NAME
                """,
                (product_id,)
            )
            ingredients_data = []
            for r in cur.fetchall():
                ing_id = r[0]
                max_quantity_rule = int(r[4]) if r[4] is not None else None
                
                # OTIMIZAÇÃO: Passa cursor para reutilizar conexão existente
                # Calcula quantidade máxima disponível baseada no estoque e na regra
                max_available_info = get_ingredient_max_available_quantity(
                    ingredient_id=ing_id,
                    max_quantity_from_rule=max_quantity_rule,
                    item_quantity=1,  # Por padrão, verifica para 1 item
                    cur=cur  # Reutiliza conexão existente
                )
                
                # Se é um ingrediente extra (portions = 0), usa max_available calculado
                # Se não, mantém max_quantity da regra
                portions = float(r[2]) if r[2] is not None else 0.0
                if portions == 0.0:  # É um ingrediente extra
                    effective_max_quantity = max_available_info['max_available']
                else:  # É ingrediente da base, não tem limite de quantidade extra
                    effective_max_quantity = max_quantity_rule if max_quantity_rule else None
                
                ingredients_data.append({
                    "ingredient_id": ing_id,
                    "name": r[1],
                    "portions": portions,
                    "min_quantity": int(r[3]) if r[3] is not None else 0,
                    "max_quantity": effective_max_quantity,  # Usa quantidade máxima disponível
                    "max_quantity_rule": max_quantity_rule,  # Mantém a regra original para referência
                    "additional_price": float(r[5]) if r[5] is not None else 0.0,
                    "is_available": bool(r[6]),
                    "availability_info": max_available_info if portions == 0.0 else None  # Info adicional para extras
                })
            
            product["ingredients"] = ingredients_data

            return product
        return None  
    except fdb.Error as e:  
        print(f"Erro ao buscar produto por ID: {e}")  
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

        conn.commit()
        
        # OTIMIZAÇÃO: Invalida cache após atualizar produto
        _invalidate_product_cache()
        
        # Se o preço foi atualizado, recalcula os descontos das promoções após o commit
        if price_updated:
            try:
                from . import promotion_service
                promotion_service.recalculate_promotion_discount_value(product_id)
            except Exception as e:
                print(f"Erro ao recalcular desconto da promoção: {e}")
                # Não falha a atualização do produto se o recálculo falhar
        
        return (True, None, "Produto atualizado com sucesso")  
    except fdb.Error as e:  
        print(f"Erro ao atualizar produto: {e}")  
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
        print(f"Erro ao inativar produto: {e}")  
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
        print(f"Erro ao atualizar URL da imagem: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()


import logging
logger = logging.getLogger(__name__)

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



def get_products_by_category_id(category_id, page=1, page_size=10, include_inactive=False):  
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
        where_clauses = ["CATEGORY_ID = ?"]
        params = [category_id]
        
        if not include_inactive:
            where_clauses.append("IS_ACTIVE = TRUE")
            
        where_sql = " AND ".join(where_clauses)
        
        # Conta total de produtos na categoria
        cur.execute(f"SELECT COUNT(*) FROM PRODUCTS WHERE {where_sql};", tuple(params))  
        total = cur.fetchone()[0] or 0  
        
        # Busca os produtos paginados - Query com sintaxe FIRST/SKIP do Firebird
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
        ingredients_map = {}
        
        # OTIMIZAÇÃO: Busca todos os status de disponibilidade de uma vez
        if product_ids:
            try:
                placeholders = ', '.join(['?' for _ in product_ids])
                availability_query = f"""
                    SELECT 
                        pi.PRODUCT_ID,
                        MIN(CASE WHEN i.IS_AVAILABLE = FALSE OR i.STOCK_STATUS = 'out_of_stock' THEN 0 ELSE 1 END) as all_available,
                        MIN(CASE WHEN i.STOCK_STATUS = 'low' OR (i.CURRENT_STOCK <= i.MIN_STOCK_THRESHOLD) THEN 1 ELSE 0 END) as has_low_stock
                    FROM PRODUCT_INGREDIENTS pi
                    JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                    WHERE pi.PRODUCT_ID IN ({placeholders})
                    GROUP BY pi.PRODUCT_ID
                """
                cur.execute(availability_query, tuple(product_ids))
                for row in cur.fetchall():
                    product_id = row[0]
                    all_av = row[1]
                    has_low = row[2]
                    if all_av == 0:
                        availability_map[product_id] = "unavailable"
                    elif has_low == 1:
                        availability_map[product_id] = "low_stock"
                    else:
                        availability_map[product_id] = "available"
            except Exception as e:
                print(f"Erro ao buscar disponibilidade em batch: {e}")
        
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
                print(f"Erro ao buscar ingredientes em batch: {e}")
        
        # Processa os produtos com os dados já carregados
        for row in product_rows:
            product_id = row[0]
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
                    print(f"Erro ao gerar hash da imagem: {e}")
                    item["image_hash"] = None
            
            # Adiciona status de disponibilidade (já carregado em batch)
            item["availability_status"] = availability_map.get(product_id, "unknown")
            
            # Adiciona ingredientes (já carregados em batch)
            item["ingredients"] = ingredients_map.get(product_id, [])
            
            items.append(item)  
            
        total_pages = (total + page_size - 1) // page_size  
        
        result = {  
            "category": {
                "id": category_id,
                "name": category_name
            },
            "items": items,  
            "pagination": {  
                "total": total,  
                "page": page,  
                "page_size": page_size,  
                "total_pages": total_pages  
            }  
        }
        
        return (result, None, None)
        
    except fdb.Error as e:  
        print(f"Erro ao buscar produtos por categoria: {e}")  
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:  
        if conn: conn.close()


def get_menu_summary():  
    conn = None  
    try:  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("SELECT COUNT(*) FROM PRODUCTS WHERE IS_ACTIVE = TRUE")  
        total_items = cur.fetchone()[0]  
        cur.execute("SELECT AVG(PRICE) FROM PRODUCTS WHERE IS_ACTIVE = TRUE AND PRICE > 0")  
        price_result = cur.fetchone()  
        avg_price = float(price_result[0]) if price_result and price_result[0] else 0.0  
        cur.execute("""
            SELECT AVG(PRICE - COST_PRICE) 
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PRICE > 0 AND COST_PRICE > 0
        """)  
        margin_result = cur.fetchone()  
        avg_margin = float(margin_result[0]) if margin_result and margin_result[0] else 0.0  
        cur.execute("""
            SELECT AVG(PREPARATION_TIME_MINUTES) 
            FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE AND PREPARATION_TIME_MINUTES > 0
        """)  
        prep_result = cur.fetchone()  
        avg_prep_time = float(prep_result[0]) if prep_result and prep_result[0] else 0.0  
        return {  
            "total_items": total_items,
            "average_price": round(avg_price, 2),
            "average_margin": round(avg_margin, 2),
            "average_preparation_time": round(avg_prep_time, 1)
        }
    except fdb.Error as e:  
        print(f"Erro ao buscar resumo do cardápio: {e}")  
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
            print(f"Aviso: Erro ao remover imagem do produto {product_id}: {e}")
        
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
        print(f"Erro ao excluir produto: {e}")
        if conn: 
            conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        print(f"Erro geral ao excluir produto: {e}")
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
        print(f"Erro ao aplicar grupo ao produto: {e}")
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
        
        # Conta total de produtos com vendas
        cur.execute("""
            SELECT COUNT(DISTINCT p.ID)
            FROM PRODUCTS p
            INNER JOIN ORDER_ITEMS oi ON p.ID = oi.PRODUCT_ID
            INNER JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE p.IS_ACTIVE = TRUE 
              AND o.STATUS = 'completed'
        """)
        total = cur.fetchone()[0] or 0
        
        # Query paginada que conta quantidades vendidas
        cur.execute("""
            SELECT 
                p.ID,
                p.NAME,
                p.DESCRIPTION,
                p.PRICE,
                p.IMAGE_URL,
                SUM(oi.QUANTITY) as total_sold
            FROM PRODUCTS p
            INNER JOIN ORDER_ITEMS oi ON p.ID = oi.PRODUCT_ID
            INNER JOIN ORDERS o ON oi.ORDER_ID = o.ID
            WHERE p.IS_ACTIVE = TRUE 
              AND o.STATUS = 'completed'
            GROUP BY p.ID, p.NAME, p.DESCRIPTION, p.PRICE, p.IMAGE_URL
            ORDER BY total_sold DESC
            FETCH FIRST ? ROWS SKIP ?
        """, (page_size, offset))
        
        items = []
        for row in cur.fetchall():
            items.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": str(row[3]),
                "image_url": row[4] if row[4] else None,
                "total_sold": int(row[5]) if row[5] else 0
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
        print(f"Erro ao buscar produtos mais pedidos: {e}")
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


def get_recently_added_products(page=1, page_size=10):
    """
    Busca os produtos mais recentemente adicionados ao catálogo.
    Retorna produtos ordenados por data de criação (ID descendente).
    Utiliza paginação padrão do sistema.
    """
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 10), 1)
    offset = (page - 1) * page_size
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Conta total de produtos ativos
        cur.execute("""
            SELECT COUNT(*) FROM PRODUCTS 
            WHERE IS_ACTIVE = TRUE
        """)
        total = cur.fetchone()[0] or 0
        
        # Query paginada que busca produtos ativos ordenados por ID descendente
        # Nota: Firebird não tem CREATED_AT em PRODUCTS por padrão, usa ID como proxy
        cur.execute("""
            SELECT 
                p.ID,
                p.NAME,
                p.DESCRIPTION,
                p.PRICE,
                p.IMAGE_URL,
                p.CATEGORY_ID,
                c.NAME as CATEGORY_NAME
            FROM PRODUCTS p
            LEFT JOIN CATEGORIES c ON p.CATEGORY_ID = c.ID
            WHERE p.IS_ACTIVE = TRUE
            ORDER BY p.ID DESC
            FETCH FIRST ? ROWS SKIP ?
        """, (page_size, offset))
        
        items = []
        for row in cur.fetchall():
            items.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "price": str(row[3]),
                "image_url": row[4] if row[4] else None,
                "category_id": row[5],
                "category_name": row[6] if row[6] else "Sem categoria"
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
        print(f"Erro ao buscar produtos recentemente adicionados: {e}")
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
