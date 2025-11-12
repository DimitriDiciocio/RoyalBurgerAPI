from ..database import get_db_connection
from . import stock_service
import fdb
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

def _validate_cart_id(cart_id):
    """Valida se cart_id é um inteiro válido e converte se necessário"""
    # Converte para inteiro se for string
    if isinstance(cart_id, str):
        try:
            cart_id = int(cart_id)
        except (ValueError, TypeError):
            raise ValueError("cart_id deve ser um número inteiro válido")
    
    # Valida se é inteiro positivo
    if not isinstance(cart_id, int) or cart_id <= 0:
        raise ValueError("cart_id deve ser um inteiro positivo")
    
    return cart_id

def _calculate_cart_totals(items):
    """Calcula totais do carrinho de forma centralizada"""
    total_items = sum(item["quantity"] for item in items)
    subtotal = sum(item["item_subtotal"] for item in items)
    
    # Retorna apenas subtotal - taxas e descontos são aplicados no pedido
    return {
        "total_items": total_items,
        "subtotal": subtotal,
        "total": subtotal,
        "is_empty": len(items) == 0
    }

def get_or_create_cart(user_id):
    """
    Busca o carrinho ativo do usuário ou cria um novo se não existir
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca carrinho ativo do usuário
        sql = "SELECT ID, USER_ID, CREATED_AT, UPDATED_AT FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (user_id,))
        row = cur.fetchone()
        
        if row:
            return {
                "id": row[0],
                "user_id": row[1],
                "created_at": row[2],
                "updated_at": row[3]
            }
        
        # Se não existe, cria um novo carrinho
        sql = "INSERT INTO CARTS (USER_ID, IS_ACTIVE) VALUES (?, TRUE) RETURNING ID;"
        cur.execute(sql, (user_id,))
        cart_id = cur.fetchone()[0]
        conn.commit()
        
        # Retorna o carrinho criado (sem query adicional desnecessária)
        return {
            "id": cart_id,
            "user_id": user_id,
            "created_at": None,  # Será preenchido em próximo acesso se necessário
            "updated_at": None
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar/criar carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()


def get_cart_items(cart_id):
    """
    Busca todos os itens do carrinho com seus extras
    """
    conn = None
    try:
        cart_id = _validate_cart_id(cart_id)
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do carrinho
        sql = """
            SELECT 
                ci.ID,
                ci.PRODUCT_ID,
                ci.QUANTITY,
                CAST(ci.NOTES AS VARCHAR(1000)) as NOTES,
                p.NAME as PRODUCT_NAME,
                p.PRICE as PRODUCT_PRICE,
                p.DESCRIPTION as PRODUCT_DESCRIPTION,
                p.IMAGE_URL as PRODUCT_IMAGE_URL,
                p.PREPARATION_TIME_MINUTES as PRODUCT_PREPARATION_TIME
            FROM CART_ITEMS ci
            JOIN PRODUCTS p ON ci.PRODUCT_ID = p.ID
            WHERE ci.CART_ID = ?
            ORDER BY ci.CREATED_AT;
        """
        cur.execute(sql, (cart_id,))
        item_rows = cur.fetchall()
        
        if not item_rows:
            return []
        
        # OTIMIZAÇÃO: Buscar todos os extras de uma vez (evita N+1 queries)
        item_ids = [row[0] for row in item_rows]
        placeholders = ', '.join(['?' for _ in item_ids])
        extras_sql = f"""
            SELECT 
                cie.CART_ITEM_ID,
                cie.ID,
                cie.INGREDIENT_ID,
                cie.QUANTITY,
                COALESCE(cie.DELTA, cie.QUANTITY) as DELTA,
                COALESCE(cie.UNIT_PRICE, COALESCE(i.ADDITIONAL_PRICE, i.PRICE)) as UNIT_PRICE,
                cie.TYPE,
                i.NAME as INGREDIENT_NAME
            FROM CART_ITEM_EXTRAS cie
            JOIN INGREDIENTS i ON cie.INGREDIENT_ID = i.ID
            WHERE cie.CART_ITEM_ID IN ({placeholders})
            ORDER BY cie.CART_ITEM_ID, cie.TYPE, i.NAME;
        """
        cur.execute(extras_sql, tuple(item_ids))
        extras_rows = cur.fetchall()
        
        # Agrupar extras por cart_item_id
        extras_by_item = {}
        for extra_row in extras_rows:
            cart_item_id = extra_row[0]
            if cart_item_id not in extras_by_item:
                extras_by_item[cart_item_id] = []
            extras_by_item[cart_item_id].append(extra_row)
        
        items = []
        for row in item_rows:
            item_id = row[0]
            product_id = row[1]
            quantity = row[2]
            notes = row[3]
            product_name = row[4]
            product_price = float(row[5]) if row[5] else 0.0
            product_description = row[6]
            product_image_url = row[7]
            product_preparation_time = int(row[8]) if row[8] else 0
            
            # Processar extras do item (já buscados em batch)
            extras = []
            extras_total = 0.0
            base_modifications = []
            base_mods_total = 0.0
            
            for extra_row in extras_by_item.get(item_id, []):
                # extra_row: [CART_ITEM_ID, ID, INGREDIENT_ID, QUANTITY, DELTA, UNIT_PRICE, TYPE, INGREDIENT_NAME]
                row_id = extra_row[1]
                ingredient_id = extra_row[2]
                quantity = int(extra_row[3] or 0)  # QUANTITY é a quantidade total
                delta = int(extra_row[4] or 0)  # DELTA pode ser diferente para base_modifications
                unit_price = float(extra_row[5] or 0.0)
                row_type = (extra_row[6] or 'extra').lower()
                ingredient_name = extra_row[7]

                if row_type == 'extra':
                    # Para extras, QUANTITY é a quantidade total (incluindo min_quantity)
                    extras.append({
                        "id": row_id,
                        "ingredient_id": ingredient_id,
                        "quantity": quantity,  # Usa QUANTITY (quantidade total)
                        "ingredient_name": ingredient_name,
                        "ingredient_price": unit_price
                    })
                    if quantity > 0:
                        extras_total += unit_price * quantity
                else:  # base
                    base_modifications.append({
                        "ingredient_id": ingredient_id,
                        "delta": delta,
                        "ingredient_name": ingredient_name,
                        "ingredient_price": unit_price  # Incluir preço para exibição no mobile
                    })
                    if delta > 0:
                        base_mods_total += unit_price * delta
            
            # Calcula subtotal do item
            item_subtotal = (product_price + extras_total + base_mods_total) * quantity
            
            item = {
                "id": item_id,
                "product_id": product_id,
                "quantity": quantity,
                "notes": notes or "",
                "product": {
                    "id": product_id,
                    "name": product_name,
                    "price": product_price,
                    "description": product_description,
                    "image_url": product_image_url,
                    "preparation_time_minutes": product_preparation_time
                },
                "extras": extras,
                "base_modifications": base_modifications,
                "base_mods_total": base_mods_total,
                "extras_total": extras_total,
                "item_subtotal": item_subtotal
            }
            items.append(item)
        
        return items
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar itens do carrinho: {e}", exc_info=True)
        return []
    except ValueError as e:
        logger.warning(f"Erro de validação ao buscar itens do carrinho: {e}")
        return []
    finally:
        if conn: conn.close()


def get_active_cart_by_user_id(user_id):
    """
    Retorna o carrinho ativo do usuário (apenas metadados) ou None
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ID FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;", (user_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0]}
        return None
    except fdb.Error as e:
        logger.error(f"Erro ao buscar carrinho ativo do usuário: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()


def get_guest_cart_by_id(cart_id):
    """
    Retorna o carrinho convidado (USER_ID IS NULL) se existir e estiver ativo
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (cart_id,))
        row = cur.fetchone()
        if row:
            return {"id": row[0]}
        return None
    except fdb.Error as e:
        logger.error(f"Erro ao buscar carrinho convidado: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()


def create_guest_cart():
    """
    Cria um novo carrinho convidado (USER_ID = NULL) ou reutiliza existente
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se já existe um carrinho de convidado ativo
        cur.execute("SELECT ID FROM CARTS WHERE USER_ID IS NULL AND IS_ACTIVE = TRUE;")
        existing_cart = cur.fetchone()
        
        if existing_cart:
            # Reutiliza carrinho existente
            return {"id": existing_cart[0]}
        
        # Se não existe, cria novo carrinho
        # Usa uma abordagem que evita conflito de constraint
        try:
            cur.execute("INSERT INTO CARTS (USER_ID, IS_ACTIVE) VALUES (NULL, TRUE) RETURNING ID;")
            cart_id = cur.fetchone()[0]
            conn.commit()
            return {"id": cart_id}
        except fdb.Error as constraint_error:
            # Se falhou por constraint, tenta buscar novamente (pode ter sido criado por outra thread)
            if constraint_error.args[1] == -803:  # Violation of PRIMARY or UNIQUE KEY constraint
                cur.execute("SELECT ID FROM CARTS WHERE USER_ID IS NULL AND IS_ACTIVE = TRUE;")
                existing_cart = cur.fetchone()
                if existing_cart:
                    return {"id": existing_cart[0]}
                else:
                    raise constraint_error
            else:
                raise constraint_error
        
    except fdb.Error as e:
        logger.error(f"Erro ao criar carrinho convidado: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()


def get_cart_summary(user_id):
    """
    Retorna o resumo completo do carrinho do usuário
    """
    try:
        cart = get_or_create_cart(user_id)
        if not cart:
            return None
        
        items = get_cart_items(cart["id"])
        if items is None:
            return None

        # Validação de disponibilidade
        availability_alerts = _check_availability_alerts(items)
        
        # Calcula totais usando função centralizada
        summary = _calculate_cart_totals(items)
        summary["availability_alerts"] = availability_alerts
        
        return {
            "cart": cart,
            "items": items,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Erro ao calcular resumo do carrinho: {e}", exc_info=True)
        return None

def _check_availability_alerts(items):
    """Verifica alertas de disponibilidade de forma centralizada"""
    if not items:
        return []
    
    availability_alerts = []
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # OTIMIZAÇÃO: Coletar todos os product_ids e ingredient_ids de uma vez
        product_ids = [item["product_id"] for item in items]
        extra_ingredient_ids = set()
        for item in items:
            for extra in item.get("extras", []):
                extra_ingredient_ids.add(extra["ingredient_id"])
        
        # OTIMIZAÇÃO: Query única para ingredientes base de todos os produtos
        base_availability = {}
        if product_ids:
            placeholders = ', '.join(['?' for _ in product_ids])
            base_query = f"""
                SELECT pi.PRODUCT_ID, i.ID, i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
                WHERE pi.PRODUCT_ID IN ({placeholders})
            """
            cur.execute(base_query, tuple(product_ids))
            for row in cur.fetchall():
                product_id, ing_id, is_av = row
                base_availability[(product_id, ing_id)] = is_av
        
        # OTIMIZAÇÃO: Query única para extras
        extra_availability = {}
        if extra_ingredient_ids:
            placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
            extra_query = f"""
                SELECT ID, IS_AVAILABLE
                FROM INGREDIENTS
                WHERE ID IN ({placeholders})
            """
            cur.execute(extra_query, tuple(extra_ingredient_ids))
            for row in cur.fetchall():
                extra_availability[row[0]] = row[1]
        
        # OTIMIZAÇÃO: Processar resultados em memória
        for item in items:
            product_id = item["product_id"]
            
            # Verificar ingredientes base do produto
            for (prod_id, ing_id), is_av in base_availability.items():
                if prod_id == product_id and not is_av:
                    availability_alerts.append({
                        "product_id": product_id,
                        "ingredient_id": ing_id,
                        "issue": "ingredient_unavailable"
                    })
            
            # Verificar extras
            for extra in item.get("extras", []):
                ing_id = extra["ingredient_id"]
                if not extra_availability.get(ing_id, True):
                    availability_alerts.append({
                        "product_id": product_id,
                        "ingredient_id": ing_id,
                        "issue": "extra_unavailable"
                    })
    except Exception as e:
        logger.error(f"Erro ao verificar disponibilidade: {e}", exc_info=True)
    finally:
        if conn: conn.close()
    
    return availability_alerts


def add_item_to_cart(user_id, product_id, quantity, extras=None, notes=None, base_modifications=None):
    """
    Adiciona um item ao carrinho do usuário
    """
    conn = None
    try:
        # Validações de limites de segurança
        if quantity <= 0 or quantity > 999:
            return (False, "INVALID_QUANTITY", "Quantidade deve estar entre 1 e 999")
        
        if extras and len(extras) > 50:
            return (False, "TOO_MANY_EXTRAS", "Número máximo de extras por item: 50")
        
        if base_modifications and len(base_modifications) > 50:
            return (False, "TOO_MANY_MODIFICATIONS", "Número máximo de modificações: 50")
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca ou cria carrinho
        cart = get_or_create_cart(user_id)
        if not cart:
            return (False, "CART_ERROR", "Erro ao acessar carrinho")
        
        cart_id = cart["id"]
        
        # Valida limite de itens no carrinho
        cur.execute("SELECT COUNT(*) FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
        item_count = cur.fetchone()[0]
        if item_count >= 100:
            return (False, "CART_FULL", "Carrinho cheio. Máximo de 100 itens diferentes")
        
        # Verifica se produto existe e está ativo
        sql = "SELECT ID, NAME, PRICE FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (product_id,))
        product = cur.fetchone()
        if not product:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado ou inativo")
        
        # OTIMIZAÇÃO DE PERFORMANCE: Busca regras do produto uma única vez
        # e valida estoque do produto antes de validar extras
        rules = _get_product_rules(cur, product_id)
        
        # Verifica estoque suficiente para o produto
        stock_check = _check_product_stock_availability(cur, product_id, quantity)
        if not stock_check[0]:
            return (False, "INSUFFICIENT_STOCK", stock_check[1])
        
        # OTIMIZAÇÃO DE PERFORMANCE: Inicializa variáveis para reutilização
        ingredient_names = {}
        ingredient_availability = {}
        
        # OTIMIZAÇÃO DE PERFORMANCE: Valida extras em batch ao invés de loop individual
        # Verifica e valida extras conforme regras do produto (PORTIONS=0, min/max)
        if extras:
            # Coleta todos os IDs de ingredientes primeiro
            extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
            
            # Busca disponibilidade de todos os ingredientes de uma vez (1 query ao invés de N)
            ingredient_availability = _batch_get_ingredient_availability(extra_ingredient_ids, quantity, cur)
            
            # Busca nomes de ingredientes de uma vez para mensagens de erro
            if extra_ingredient_ids:
                placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                cur.execute(f"SELECT ID, NAME FROM INGREDIENTS WHERE ID IN ({placeholders})", tuple(extra_ingredient_ids))
                for row in cur.fetchall():
                    ingredient_names[row[0]] = row[1]
            
            # Valida cada extra usando dados já carregados em batch
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                
                # CORREÇÃO: Se o ingrediente não está nas regras do produto, verifica se ele existe e está disponível
                # Permite adicionar ingredientes que não estão cadastrados como extras do produto
                # (desde que não sejam da receita base)
                if not rule:
                    # Verifica se o ingrediente existe e está disponível
                    if ing_id not in ingredient_names:
                        return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente ID {ing_id} não encontrado")
                    # Se não está nas regras, assume que pode ser adicionado como extra (portions=0)
                    # Usa valores padrão: min=0, max=None (sem limite de regra)
                    min_q = 0
                    max_q_rule = None
                else:
                    # Se está nas regras, verifica se não é da receita base
                    if float(rule["portions"]) != 0.0:
                        return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                    min_q = int(rule["min_quantity"] or 0)
                    max_q_rule = int(rule["max_quantity"]) if rule["max_quantity"] else None
                
                # Obtém disponibilidade do cache em memória (já carregado em batch)
                max_available_info = ingredient_availability.get(ing_id)
                if not max_available_info:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não encontrado ou indisponível")
                
                max_q_available = max_available_info['max_available']
                
                # Aplica limite da regra se existir
                if max_q_rule is not None and max_q_rule > 0:
                    max_q_available = min(max_q_rule, max_q_available)
                    # Atualiza limited_by se necessário
                    if max_q_available == max_q_rule and max_available_info['max_available'] > max_q_rule:
                        max_available_info['limited_by'] = 'rule'
                
                # Valida quantidade mínima
                if qty < min_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra abaixo do mínimo permitido [{min_q}]")
                
                # IMPORTANTE: qty é a quantidade TOTAL (incluindo min_quantity)
                # max_q_available é a quantidade máxima de EXTRAS disponíveis (sem incluir min_quantity)
                # Então a quantidade total máxima permitida é: min_q + max_q_available
                max_total_qty = min_q + max_q_available
                
                # Valida quantidade máxima (considerando estoque)
                # Se max_q_available > 0, há estoque para extras adicionais
                if max_q_available > 0 and qty > max_total_qty:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra excede o disponível. "
                           f"Máximo permitido: {max_total_qty} (mínimo: {min_q} + extras: {max_q_available}) "
                           f"(limitado por {'regra' if max_available_info['limited_by'] == 'rule' else 'estoque'})")
                
                # Verifica se ingrediente está disponível
                # Se max_q_available é 0, não há estoque para extras adicionais (mas pode ter min_q > 0)
                # Se não tem stock_info, ingrediente não está disponível
                if not max_available_info['stock_info']:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                
                # Se max_q_available é 0 e qty > min_q, não há estoque suficiente
                if max_q_available == 0 and qty > min_q:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não tem estoque suficiente para a quantidade solicitada. "
                           f"Máximo permitido: {min_q}")
                
                # Verifica estoque suficiente para a quantidade solicitada com conversão de unidades
                stock_info = max_available_info['stock_info']
                base_portion_quantity = stock_info['base_portion_quantity']
                base_portion_unit = stock_info['base_portion_unit']
                stock_unit = stock_info['stock_unit']
                current_stock = stock_info['current_stock']
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=float(base_portion_quantity),
                        base_portion_unit=str(base_portion_unit),
                        stock_unit=str(stock_unit),
                        item_quantity=quantity
                    )
                except ValueError as e:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para '{ing_name}': {str(e)}")
                
                # Compara com estoque disponível
                if current_stock < required_quantity:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock:.3f} {stock_unit}")
        
        # OTIMIZAÇÃO DE PERFORMANCE: Verifica item existente antes de validar estoque novamente
        # Isso evita validações duplicadas de estoque
        existing_item_id = find_identical_cart_item(cart_id, product_id, extras or [], notes or "", base_modifications or [])
        
        if existing_item_id:
            # NOVA VALIDAÇÃO: Busca quantidade atual do item antes de incrementar
            cur.execute("SELECT QUANTITY FROM CART_ITEMS WHERE ID = ?", (existing_item_id,))
            existing_row = cur.fetchone()
            if existing_row:
                existing_quantity = existing_row[0]
                new_total_quantity = existing_quantity + quantity
                
                # OTIMIZAÇÃO: Valida estoque apenas para a quantidade adicional (não recalcula tudo)
                # Isso evita validar novamente o que já estava no carrinho
                stock_check_additional = _check_product_stock_availability(cur, product_id, quantity)  # Apenas quantidade adicional
                if not stock_check_additional[0]:
                    return (False, "INSUFFICIENT_STOCK", stock_check_additional[1])
                
                # OTIMIZAÇÃO: Valida estoque para extras com a nova quantidade total em batch
                # Reutiliza ingredient_availability se já foi carregado, senão busca novamente
                if extras:
                    # Recoleta IDs se necessário (pode não estar definido no escopo atual)
                    extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
                    if extra_ingredient_ids:
                        # Revalida disponibilidade com a nova quantidade total
                        ingredient_availability_total = _batch_get_ingredient_availability(extra_ingredient_ids, new_total_quantity, cur)
                        
                        # Reutiliza ingredient_names se já foi carregado
                        for extra in extras:
                            ing_id = extra.get("ingredient_id")
                            qty = int(extra.get("quantity", 1))
                            rule = rules.get(ing_id)
                            max_q_rule = int(rule["max_quantity"]) if rule and rule.get("max_quantity") else None
                            
                            # Obtém disponibilidade do cache em memória
                            max_available_info = ingredient_availability_total.get(ing_id)
                            if not max_available_info or not max_available_info.get('stock_info'):
                                ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                                return (False, "INSUFFICIENT_STOCK", 
                                       f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                            
                            # Aplica limite da regra
                            max_q_available = max_available_info['max_available']
                            if max_q_rule is not None and max_q_rule > 0:
                                max_q_available = min(max_q_rule, max_q_available)
                            
                            stock_info = max_available_info['stock_info']
                            base_portion_quantity = stock_info['base_portion_quantity']
                            base_portion_unit = stock_info['base_portion_unit']
                            stock_unit = stock_info['stock_unit']
                            current_stock = stock_info['current_stock']
                            
                            # Calcula consumo para a NOVA quantidade total
                            try:
                                required_quantity_total = stock_service.calculate_consumption_in_stock_unit(
                                    portions=qty,
                                    base_portion_quantity=float(base_portion_quantity),
                                    base_portion_unit=str(base_portion_unit),
                                    stock_unit=str(stock_unit),
                                    item_quantity=new_total_quantity  # ← Usa quantidade total
                                )
                            except ValueError as e:
                                ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                                return (False, "INSUFFICIENT_STOCK", 
                                       f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                            
                            # Compara com estoque disponível
                            if current_stock < required_quantity_total:
                                ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                                return (False, "INSUFFICIENT_STOCK", 
                                       f"Estoque insuficiente para extra '{ing_name}'. "
                                       f"Necessário: {required_quantity_total:.3f} {stock_unit}, "
                                       f"Disponível: {current_stock:.3f} {stock_unit}")
            
            # Incrementa quantidade do item existente
            sql = "UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;"
            cur.execute(sql, (quantity, existing_item_id))
        else:
            # Cria novo item
            sql = "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;"
            cur.execute(sql, (cart_id, product_id, quantity, notes))
            new_item_id = cur.fetchone()[0]
            
            # OTIMIZAÇÃO: Busca preços de ingredientes em batch ao invés de queries individuais
            # Adiciona extras se fornecidos (TYPE='extra')
            if extras:
                logger.info(f"[add_item_to_cart] Processando {len(extras)} extras para item {new_item_id}")
                # Coleta IDs de ingredientes e busca preços de uma vez
                extra_ingredient_ids = [ex.get("ingredient_id") for ex in extras if ex.get("ingredient_id")]
                ingredient_prices = {}
                if extra_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(extra_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        ingredient_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere extras usando preços já carregados
                extras_inserted = 0
                for extra in extras:
                    ingredient_id = extra.get("ingredient_id")
                    extra_quantity = int(extra.get("quantity", 1))
                    
                    # IMPORTANTE: Valida quantidade antes de inserir
                    if extra_quantity <= 0:
                        logger.warning(f"[add_item_to_cart] Extra com quantidade inválida: ingredient_id={ingredient_id}, qty={extra_quantity}, extra_data={extra}")
                        continue
                    
                    # CORREÇÃO: Busca preço mesmo se não estava no batch inicial (para ingredientes não cadastrados como extras)
                    unit_price = ingredient_prices.get(ingredient_id, 0.0)
                    if unit_price == 0.0:
                        # Tenta buscar preço diretamente do banco
                        cur.execute(
                            "SELECT COALESCE(ADDITIONAL_PRICE, PRICE, 0) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE",
                            (ingredient_id,)
                        )
                        price_row = cur.fetchone()
                        if price_row:
                            unit_price = float(price_row[0] or 0.0)
                            ingredient_prices[ingredient_id] = unit_price  # Adiciona ao cache
                    
                    if unit_price > 0:  # Só insere se ingrediente existe e tem preço
                        sql_extra = (
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) "
                            "VALUES (?, ?, ?, 'extra', ?, ?);"
                        )
                        cur.execute(sql_extra, (new_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price))
                        extras_inserted += 1
                        logger.info(f"[add_item_to_cart] Extra inserido: item_id={new_item_id}, ingredient_id={ingredient_id}, quantity={extra_quantity}, price={unit_price}")
                    else:
                        logger.warning(f"[add_item_to_cart] Extra não inserido - preço zero ou ingrediente não encontrado: ingredient_id={ingredient_id}, unit_price={unit_price}, quantity={extra_quantity}")
                
                logger.info(f"[add_item_to_cart] Total de extras inseridos: {extras_inserted} de {len(extras)}")

            # Adiciona modificações de base (TYPE='base')
            if base_modifications:
                rules = _get_product_rules(cur, product_id)
                # OTIMIZAÇÃO: Busca preços de ingredientes de base em batch
                base_mod_ingredient_ids = []
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                        rule = rules.get(ing_id)
                        if rule and float(rule["portions"]) != 0.0 and delta != 0:
                            base_mod_ingredient_ids.append(ing_id)
                    except (ValueError, TypeError, AttributeError):
                        continue
                
                base_mod_prices = {}
                if base_mod_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in base_mod_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(base_mod_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        base_mod_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere modificações de base usando preços já carregados
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                    except (ValueError, TypeError, AttributeError):
                        continue
                    rule = rules.get(ing_id)
                    if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                        continue
                    
                    unit_price = base_mod_prices.get(ing_id, 0.0)
                    if unit_price >= 0:  # Permite preço zero
                        cur.execute(
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                            (new_item_id, ing_id, delta, unit_price)
                        )
        
        conn.commit()
        return (True, None, "Item adicionado ao carrinho com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao adicionar item ao carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def add_item_to_cart_by_cart_id(cart_id, product_id, quantity, extras=None, notes=None, base_modifications=None):
    """
    Adiciona item ao carrinho identificado por cart_id (convidado)
    """
    conn = None
    try:
        # Validações de limites de segurança
        if quantity <= 0 or quantity > 999:
            return (False, "INVALID_QUANTITY", "Quantidade deve estar entre 1 e 999")
        
        if extras and len(extras) > 50:
            return (False, "TOO_MANY_EXTRAS", "Número máximo de extras por item: 50")
        
        if base_modifications and len(base_modifications) > 50:
            return (False, "TOO_MANY_MODIFICATIONS", "Número máximo de modificações: 50")
        
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Valida limite de itens no carrinho
        cur.execute("SELECT COUNT(*) FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
        item_count = cur.fetchone()[0]
        if item_count >= 100:
            return (False, "CART_FULL", "Carrinho cheio. Máximo de 100 itens diferentes")

        # Verifica existência do carrinho convidado ativo
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (cart_id,))
        if not cur.fetchone():
            return (False, "CART_NOT_FOUND", "Carrinho convidado não encontrado")

        # Verifica se produto existe e está ativo
        sql = "SELECT ID, NAME, PRICE FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (product_id,))
        product = cur.fetchone()
        if not product:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado ou inativo")

        # Verifica estoque suficiente para o produto
        stock_check = _check_product_stock_availability(cur, product_id, quantity)
        if not stock_check[0]:
            return (False, "INSUFFICIENT_STOCK", stock_check[1])

        # OTIMIZAÇÃO DE PERFORMANCE: Valida extras em batch ao invés de loop individual
        # Verifica e valida extras conforme regras do produto (PORTIONS=0, min/max)
        rules = _get_product_rules(cur, product_id)
        
        if extras:
            # Coleta todos os IDs de ingredientes primeiro
            extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
            
            # Busca disponibilidade de todos os ingredientes de uma vez (1 query ao invés de N)
            ingredient_availability = _batch_get_ingredient_availability(extra_ingredient_ids, quantity, cur)
            
            # Busca nomes de ingredientes de uma vez para mensagens de erro
            ingredient_names = {}
            if extra_ingredient_ids:
                placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                cur.execute(f"SELECT ID, NAME FROM INGREDIENTS WHERE ID IN ({placeholders})", tuple(extra_ingredient_ids))
                for row in cur.fetchall():
                    ingredient_names[row[0]] = row[1]
            
            # Valida cada extra usando dados já carregados em batch
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", "Um ou mais extras não são permitidos para este produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q_rule = int(rule["max_quantity"]) if rule["max_quantity"] else None
                
                # Obtém disponibilidade do cache em memória (já carregado em batch)
                max_available_info = ingredient_availability.get(ing_id)
                if not max_available_info:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não encontrado ou indisponível")
                
                max_q_available = max_available_info['max_available']
                
                # Aplica limite da regra se existir
                if max_q_rule is not None and max_q_rule > 0:
                    max_q_available = min(max_q_rule, max_q_available)
                    # Atualiza limited_by se necessário
                    if max_q_available == max_q_rule and max_available_info['max_available'] > max_q_rule:
                        max_available_info['limited_by'] = 'rule'
                
                # Valida quantidade mínima
                if qty < min_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra abaixo do mínimo permitido [{min_q}]")
                
                # IMPORTANTE: qty é a quantidade TOTAL (incluindo min_quantity)
                # max_q_available é a quantidade máxima de EXTRAS disponíveis (sem incluir min_quantity)
                # Então a quantidade total máxima permitida é: min_q + max_q_available
                max_total_qty = min_q + max_q_available
                
                # Valida quantidade máxima (considerando estoque)
                # Se max_q_available > 0, há estoque para extras adicionais
                if max_q_available > 0 and qty > max_total_qty:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra excede o disponível. "
                           f"Máximo permitido: {max_total_qty} (mínimo: {min_q} + extras: {max_q_available}) "
                           f"(limitado por {'regra' if max_available_info['limited_by'] == 'rule' else 'estoque'})")
                
                # Verifica se ingrediente está disponível
                # Se max_q_available é 0, não há estoque para extras adicionais (mas pode ter min_q > 0)
                # Se não tem stock_info, ingrediente não está disponível
                if not max_available_info['stock_info']:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                
                # Se max_q_available é 0 e qty > min_q, não há estoque suficiente
                if max_q_available == 0 and qty > min_q:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não tem estoque suficiente para a quantidade solicitada. "
                           f"Máximo permitido: {min_q}")
                
                # Verifica estoque suficiente para a quantidade solicitada com conversão de unidades
                stock_info = max_available_info['stock_info']
                base_portion_quantity = stock_info['base_portion_quantity']
                base_portion_unit = stock_info['base_portion_unit']
                stock_unit = stock_info['stock_unit']
                current_stock = stock_info['current_stock']
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=float(base_portion_quantity),
                        base_portion_unit=str(base_portion_unit),
                        stock_unit=str(stock_unit),
                        item_quantity=quantity
                    )
                except ValueError as e:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para '{ing_name}': {str(e)}")
                
                # Compara com estoque disponível
                if current_stock < required_quantity:
                    ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock:.3f} {stock_unit}")

        # Verifica item idêntico (inclui base_mods)
        existing_item_id = find_identical_cart_item(cart_id, product_id, extras or [], notes or "", base_modifications or [])

        if existing_item_id:
            # NOVA VALIDAÇÃO: Busca quantidade atual do item antes de incrementar
            cur.execute("SELECT QUANTITY FROM CART_ITEMS WHERE ID = ?", (existing_item_id,))
            existing_row = cur.fetchone()
            if existing_row:
                existing_quantity = existing_row[0]
                new_total_quantity = existing_quantity + quantity
                
                # Valida estoque para a nova quantidade total do produto
                stock_check_total = _check_product_stock_availability(cur, product_id, new_total_quantity)
                if not stock_check_total[0]:
                    return (False, "INSUFFICIENT_STOCK", stock_check_total[1])
                
                # OTIMIZAÇÃO: Valida estoque para extras com a nova quantidade total em batch
                if extras:
                    # Revalida disponibilidade com a nova quantidade total
                    extra_ingredient_ids = [extra.get("ingredient_id") for extra in extras if extra.get("ingredient_id")]
                    ingredient_availability_total = _batch_get_ingredient_availability(extra_ingredient_ids, new_total_quantity, cur)
                    
                    # Busca nomes de ingredientes de uma vez
                    ingredient_names = {}
                    if extra_ingredient_ids:
                        placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                        cur.execute(f"SELECT ID, NAME FROM INGREDIENTS WHERE ID IN ({placeholders})", tuple(extra_ingredient_ids))
                        for row in cur.fetchall():
                            ingredient_names[row[0]] = row[1]
                    
                    for extra in extras:
                        ing_id = extra.get("ingredient_id")
                        qty = int(extra.get("quantity", 1))
                        
                        # Obtém disponibilidade do cache em memória
                        max_available_info = ingredient_availability_total.get(ing_id)
                        if not max_available_info or not max_available_info.get('stock_info'):
                            ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                        
                        stock_info = max_available_info['stock_info']
                        base_portion_quantity = stock_info['base_portion_quantity']
                        base_portion_unit = stock_info['base_portion_unit']
                        stock_unit = stock_info['stock_unit']
                        current_stock = stock_info['current_stock']
                        
                        # Calcula consumo para a NOVA quantidade total
                        try:
                            required_quantity_total = stock_service.calculate_consumption_in_stock_unit(
                                portions=qty,
                                base_portion_quantity=float(base_portion_quantity),
                                base_portion_unit=str(base_portion_unit),
                                stock_unit=str(stock_unit),
                                item_quantity=new_total_quantity  # ← Usa quantidade total
                            )
                        except ValueError as e:
                            ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                        
                        current_stock_decimal = Decimal(str(current_stock))
                        
                        if current_stock_decimal < required_quantity_total:
                            ing_name = ingredient_names.get(ing_id, 'Ingrediente')
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Estoque insuficiente para extra '{ing_name}'. "
                                   f"Necessário: {required_quantity_total:.3f} {stock_unit}, "
                                   f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            sql = "UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;"
            cur.execute(sql, (quantity, existing_item_id))
        else:
            sql = "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;"
            cur.execute(sql, (cart_id, product_id, quantity, notes))
            new_item_id = cur.fetchone()[0]

            # OTIMIZAÇÃO: Busca preços de ingredientes em batch
            if extras:
                # Coleta IDs de ingredientes e busca preços de uma vez
                extra_ingredient_ids = [ex.get("ingredient_id") for ex in extras if ex.get("ingredient_id")]
                ingredient_prices = {}
                if extra_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(extra_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        ingredient_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere extras usando preços já carregados
                for extra in extras:
                    ingredient_id = extra.get("ingredient_id")
                    extra_quantity = int(extra.get("quantity", 1))
                    if extra_quantity <= 0:
                        continue
                    
                    unit_price = ingredient_prices.get(ingredient_id, 0.0)
                    if unit_price > 0:  # Só insere se ingrediente existe e tem preço
                        cur.execute(
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                            (new_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price)
                        )

            if base_modifications:
                rules = _get_product_rules(cur, product_id)
                # OTIMIZAÇÃO: Busca preços de ingredientes de base em batch
                base_mod_ingredient_ids = []
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                        rule = rules.get(ing_id)
                        if rule and float(rule["portions"]) != 0.0 and delta != 0:
                            base_mod_ingredient_ids.append(ing_id)
                    except (ValueError, TypeError, AttributeError):
                        continue
                
                base_mod_prices = {}
                if base_mod_ingredient_ids:
                    placeholders = ', '.join(['?' for _ in base_mod_ingredient_ids])
                    cur.execute(
                        f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = TRUE;",
                        tuple(base_mod_ingredient_ids)
                    )
                    for row in cur.fetchall():
                        base_mod_prices[row[0]] = float(row[1] or 0.0)
                
                # Insere modificações de base usando preços já carregados
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                    except (ValueError, TypeError, AttributeError):
                        continue
                    rule = rules.get(ing_id)
                    if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                        continue
                    
                    unit_price = base_mod_prices.get(ing_id, 0.0)
                    if unit_price >= 0:  # Permite preço zero
                        cur.execute(
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                            (new_item_id, ing_id, delta, unit_price)
                        )

        conn.commit()
        return (True, None, "Item adicionado ao carrinho com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao adicionar item ao carrinho por cart_id: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def find_identical_cart_item(cart_id, product_id, extras, notes, base_modifications=None):
    """
    Verifica se já existe um item idêntico no carrinho (mesmo produto e mesmos extras)
    
    OTIMIZAÇÃO DE PERFORMANCE: Busca todos os extras de todos os itens de uma vez,
    evitando N+1 queries quando há múltiplos itens do mesmo produto.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do mesmo produto
        sql = "SELECT ID, CAST(NOTES AS VARCHAR(1000)) FROM CART_ITEMS WHERE CART_ID = ? AND PRODUCT_ID = ?;"
        cur.execute(sql, (cart_id, product_id))
        items = cur.fetchall()
        
        if not items:
            return None
        
        # OTIMIZAÇÃO: Busca todos os extras de todos os itens de uma vez (evita N+1)
        item_ids = [item[0] for item in items]
        placeholders = ', '.join(['?' for _ in item_ids])
        cur.execute(
            f"""
            SELECT CART_ITEM_ID, INGREDIENT_ID, COALESCE(DELTA, QUANTITY) AS DELTA, TYPE 
            FROM CART_ITEM_EXTRAS 
            WHERE CART_ITEM_ID IN ({placeholders})
            ORDER BY CART_ITEM_ID, TYPE, INGREDIENT_ID;
            """,
            tuple(item_ids)
        )
        all_extras_rows = cur.fetchall()
        
        # Agrupa extras por cart_item_id
        extras_by_item = {}
        for row in all_extras_rows:
            item_id = row[0]
            if item_id not in extras_by_item:
                extras_by_item[item_id] = {'extras': [], 'base': []}
            row_type = (row[3] or 'extra').lower()
            if row_type == 'extra':
                extras_by_item[item_id]['extras'].append((row[1], int(row[2])))
            elif row_type == 'base' and int(row[2]) != 0:
                extras_by_item[item_id]['base'].append((row[1], int(row[2])))
        
        # Normaliza listas de extras desejados
        wanted_extras = []
        for ex in (extras or []):
            try:
                wanted_extras.append((int(ex.get("ingredient_id")), int(ex.get("quantity", 1))))
            except (ValueError, TypeError, AttributeError):
                continue
        wanted_extras.sort()

        wanted_base = []
        for bm in (base_modifications or []):
            try:
                d = int(bm.get("delta", 0))
                if d != 0:
                    wanted_base.append((int(bm.get("ingredient_id")), d))
            except (ValueError, TypeError, AttributeError):
                continue
        wanted_base.sort()
        
        # Compara cada item com os extras desejados
        for item_id, existing_notes in items:
            item_extras_data = extras_by_item.get(item_id, {'extras': [], 'base': []})
            existing_extras = sorted(item_extras_data['extras'])
            existing_base = sorted(item_extras_data['base'])

            extras_match = (existing_extras == wanted_extras)
            base_match = (existing_base == wanted_base)

            if extras_match and base_match and (existing_notes or "") == (notes or ""):
                return item_id
        
        return None
        
    except fdb.Error as e:
        logger.error(f"Erro ao verificar item idêntico: {e}", exc_info=True)
        return None
    finally:
        if conn: conn.close()


def update_cart_item(user_id, cart_item_id, quantity=None, extras=None, notes=None, base_modifications=None):
    """
    Atualiza um item do carrinho
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o item pertence ao usuário e busca informações necessárias
        sql = """
            SELECT ci.ID, ci.PRODUCT_ID, ci.QUANTITY FROM CART_ITEMS ci
            JOIN CARTS c ON ci.CART_ID = c.ID
            WHERE ci.ID = ? AND c.USER_ID = ? AND c.IS_ACTIVE = TRUE;
        """
        cur.execute(sql, (cart_item_id, user_id))
        row = cur.fetchone()
        if not row:
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no seu carrinho")
        
        current_product_id = row[1]
        
        # CORREÇÃO: Se quantidade está sendo atualizada, valida estoque para a nova quantidade
        if quantity is not None:
            if quantity <= 0:
                return (False, "INVALID_QUANTITY", "Quantidade deve ser maior que zero")
            
            # Valida estoque do produto para a nova quantidade
            stock_check = _check_product_stock_availability(cur, current_product_id, quantity)
            if not stock_check[0]:
                return (False, "INSUFFICIENT_STOCK", stock_check[1])
            
            # Valida estoque dos extras existentes para a nova quantidade
            # Busca extras atuais do item
            cur.execute("""
                SELECT cie.INGREDIENT_ID, cie.QUANTITY
                FROM CART_ITEM_EXTRAS cie
                WHERE cie.CART_ITEM_ID = ? AND cie.TYPE = 'extra'
            """, (cart_item_id,))
            existing_extras = cur.fetchall()
            
            for ing_id, extra_qty in existing_extras:
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo para a NOVA quantidade
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=extra_qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=quantity  # ← Nova quantidade
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            # Atualiza quantidade após validação
            sql = "UPDATE CART_ITEMS SET QUANTITY = ? WHERE ID = ?;"
            cur.execute(sql, (quantity, cart_item_id))
        
        # Atualiza notes se fornecido
        if notes is not None:
            sql = "UPDATE CART_ITEMS SET NOTES = ? WHERE ID = ?;"
            cur.execute(sql, (notes, cart_item_id))
        
        # Atualiza extras se fornecidos (independente de notes)
        if extras is not None:
            # Valida conforme regras do produto deste item
            cur.execute("SELECT PRODUCT_ID, QUANTITY FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
            row = cur.fetchone()
            if not row:
                return (False, "ITEM_NOT_FOUND", "Item não encontrado")
            product_id = row[0]
            item_quantity = row[1]  # Quantidade do item no carrinho (pode ter sido atualizada)
            
            rules = _get_product_rules(cur, product_id)
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", "Um ou mais extras não são permitidos para este produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Quantidade de extra fora do intervalo permitido [{min_q}, {max_q or '∞'}]")
                
                # VALIDAÇÃO DE ESTOQUE com conversão de unidades
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=item_quantity  # Usa quantidade do item no carrinho
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                # Converte current_stock para Decimal para comparação precisa
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            # Remove e recria apenas linhas TYPE='extra'
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'extra';", (cart_item_id,))
            for extra in extras:
                ingredient_id = extra.get("ingredient_id")
                extra_quantity = int(extra.get("quantity", 1))
                if extra_quantity <= 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ingredient_id,))
                rowp = cur.fetchone()
                if rowp:
                    unit_price = float(rowp[0] or 0.0)
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                        (cart_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price)
                    )
        
        # Atualiza base_modifications se fornecido
        if base_modifications is not None:
            # Remove e recria TYPE='base'
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'base';", (cart_item_id,))
            # Precisamos do product_id para validar regras
            cur.execute("SELECT PRODUCT_ID FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
            row = cur.fetchone()
            if not row:
                return (False, "ITEM_NOT_FOUND", "Item não encontrado")
            product_id = row[0]
            rules = _get_product_rules(cur, product_id)
            for bm in base_modifications:
                try:
                    ing_id = int(bm.get("ingredient_id"))
                    delta = int(bm.get("delta", 0))
                except Exception:
                    continue
                rule = rules.get(ing_id)
                if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ing_id,))
                rowp = cur.fetchone()
                unit_price = float(rowp[0] or 0.0) if rowp else 0.0
                cur.execute(
                    "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                    (cart_item_id, ing_id, delta, unit_price)
                )
        
        conn.commit()
        return (True, None, "Item atualizado com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar item do carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def update_cart_item_by_cart(cart_id, cart_item_id, quantity=None, extras=None, notes=None, base_modifications=None):
    """
    Atualiza um item do carrinho para carrinho convidado (por cart_id)
    """
    conn = None
    try:
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica se o item pertence ao carrinho convidado e busca informações necessárias
        sql = (
            "SELECT ci.ID, ci.PRODUCT_ID, ci.QUANTITY FROM CART_ITEMS ci "
            "JOIN CARTS c ON ci.CART_ID = c.ID "
            "WHERE ci.ID = ? AND c.ID = ? AND c.USER_ID IS NULL AND c.IS_ACTIVE = TRUE;"
        )
        cur.execute(sql, (cart_item_id, cart_id))
        row = cur.fetchone()
        if not row:
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no carrinho informado")

        current_product_id = row[1]

        # CORREÇÃO: Se quantidade está sendo atualizada, valida estoque para a nova quantidade
        if quantity is not None:
            if quantity <= 0:
                return (False, "INVALID_QUANTITY", "Quantidade deve ser maior que zero")
            
            # Valida estoque do produto para a nova quantidade
            stock_check = _check_product_stock_availability(cur, current_product_id, quantity)
            if not stock_check[0]:
                return (False, "INSUFFICIENT_STOCK", stock_check[1])
            
            # Valida estoque dos extras existentes para a nova quantidade
            # Busca extras atuais do item
            cur.execute("""
                SELECT cie.INGREDIENT_ID, cie.QUANTITY
                FROM CART_ITEM_EXTRAS cie
                WHERE cie.CART_ITEM_ID = ? AND cie.TYPE = 'extra'
            """, (cart_item_id,))
            existing_extras = cur.fetchall()
            
            for ing_id, extra_qty in existing_extras:
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo para a NOVA quantidade
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=extra_qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=quantity  # ← Nova quantidade
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")
            
            # Atualiza quantidade após validação
            cur.execute("UPDATE CART_ITEMS SET QUANTITY = ? WHERE ID = ?;", (quantity, cart_item_id))

        # Atualiza notes se fornecido (independente de extras)
        if notes is not None:
            cur.execute("UPDATE CART_ITEMS SET NOTES = ? WHERE ID = ?;", (notes, cart_item_id))

        # Atualiza extras se fornecidos (independente de notes)
        if extras is not None:
            # Valida conforme regras do produto deste item
            cur.execute("SELECT PRODUCT_ID, QUANTITY FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
            row = cur.fetchone()
            if not row:
                return (False, "ITEM_NOT_FOUND", "Item não encontrado")
            product_id = row[0]
            item_quantity = row[1]  # Quantidade do item no carrinho (pode ter sido atualizada)
            
            rules = _get_product_rules(cur, product_id)
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", "Um ou mais extras não são permitidos para este produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", "Um dos extras selecionados já faz parte da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Quantidade de extra fora do intervalo permitido [{min_q}, {max_q or '∞'}]")
                
                # VALIDAÇÃO DE ESTOQUE com conversão de unidades
                cur.execute("""
                    SELECT BASE_PORTION_QUANTITY, BASE_PORTION_UNIT, STOCK_UNIT, CURRENT_STOCK, NAME
                    FROM INGREDIENTS
                    WHERE ID = ? AND IS_AVAILABLE = TRUE
                """, (ing_id,))
                ing_info = cur.fetchone()
                if not ing_info:
                    return (False, "INSUFFICIENT_STOCK", "Ingrediente do extra não encontrado ou indisponível")
                
                base_portion_quantity = ing_info[0] or 1
                base_portion_unit = ing_info[1] or 'un'
                stock_unit = ing_info[2] or 'un'
                current_stock = ing_info[3] or 0
                ing_name = ing_info[4]
                
                # Calcula consumo convertido para unidade do estoque
                try:
                    required_quantity = stock_service.calculate_consumption_in_stock_unit(
                        portions=qty,
                        base_portion_quantity=base_portion_quantity,
                        base_portion_unit=base_portion_unit,
                        stock_unit=stock_unit,
                        item_quantity=item_quantity  # Usa quantidade do item no carrinho
                    )
                except ValueError as e:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                
                # Converte current_stock para Decimal para comparação precisa
                current_stock_decimal = Decimal(str(current_stock))
                
                if current_stock_decimal < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra '{ing_name}'. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock_decimal:.3f} {stock_unit}")

            # Remove e recria apenas TYPE='extra'
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'extra';", (cart_item_id,))
            for extra in extras:
                ingredient_id = extra.get("ingredient_id")
                extra_quantity = int(extra.get("quantity", 1))
                if extra_quantity <= 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ingredient_id,))
                rowp = cur.fetchone()
                if rowp:
                    unit_price = float(rowp[0] or 0.0)
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                        (cart_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price)
                    )

        # Atualiza base_modifications se fornecido
        if base_modifications is not None:
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? AND TYPE = 'base';", (cart_item_id,))
            cur.execute("SELECT PRODUCT_ID FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
            row = cur.fetchone()
            if not row:
                return (False, "ITEM_NOT_FOUND", "Item não encontrado")
            product_id = row[0]
            rules = _get_product_rules(cur, product_id)
            for bm in base_modifications:
                try:
                    ing_id = int(bm.get("ingredient_id"))
                    delta = int(bm.get("delta", 0))
                except Exception:
                    continue
                rule = rules.get(ing_id)
                if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                    continue
                cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ing_id,))
                rowp = cur.fetchone()
                unit_price = float(rowp[0] or 0.0) if rowp else 0.0
                cur.execute(
                    "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                    (cart_item_id, ing_id, delta, unit_price)
                )

        conn.commit()
        return (True, None, "Item atualizado com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao atualizar item do carrinho por cart_id: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def _get_product_rules(cur, product_id):
    """Busca regras de ingredientes para um produto e retorna dict por ingredient_id"""
    cur.execute(
        """
        SELECT INGREDIENT_ID, PORTIONS, MIN_QUANTITY, MAX_QUANTITY
        FROM PRODUCT_INGREDIENTS
        WHERE PRODUCT_ID = ?
        """,
        (product_id,)
    )
    rules = {}
    for row in cur.fetchall():
        rules[row[0]] = {
            "portions": float(row[1] or 0),
            "min_quantity": int(row[2] or 0),
            "max_quantity": int(row[3] or 0)
        }
    return rules


def _batch_get_ingredient_availability(ingredient_ids, item_quantity, cur):
    """
    OTIMIZAÇÃO DE PERFORMANCE: Busca disponibilidade de múltiplos ingredientes em uma única query.
    Evita N+1 queries quando validando extras em batch.
    
    Args:
        ingredient_ids: Lista de IDs de ingredientes
        item_quantity: Quantidade de itens do produto
        cur: Cursor do banco de dados
    
    Returns:
        dict: {ingredient_id: max_available_info}
    """
    if not ingredient_ids:
        return {}
    
    from .product_service import get_ingredient_max_available_quantity
    
    # Busca informações de todos os ingredientes de uma vez
    placeholders = ', '.join(['?' for _ in ingredient_ids])
    cur.execute(f"""
        SELECT 
            ID, NAME, CURRENT_STOCK, STOCK_UNIT, BASE_PORTION_QUANTITY, 
            BASE_PORTION_UNIT, IS_AVAILABLE
        FROM INGREDIENTS
        WHERE ID IN ({placeholders})
    """, tuple(ingredient_ids))
    
    ingredients_data = {}
    for row in cur.fetchall():
        ing_id, name, current_stock, stock_unit, base_portion_quantity, base_portion_unit, is_available = row
        
        if not is_available:
            ingredients_data[ing_id] = {
                'max_available': 0,
                'limited_by': 'unavailable',
                'stock_info': {
                    'current_stock': Decimal(str(current_stock or 0)),
                    'stock_unit': stock_unit or 'un',
                    'base_portion_quantity': Decimal(str(base_portion_quantity or 1)),
                    'base_portion_unit': base_portion_unit or 'un'
                }
            }
            continue
        
        # IMPORTANTE: Para extras (portions = 0), usa get_ingredient_max_available_quantity
        # que já calcula corretamente considerando estoque e quantidade do produto
        # Como não temos max_quantity_from_rule aqui, passa None (será aplicado depois na validação)
        try:
            max_available_info = get_ingredient_max_available_quantity(
                ingredient_id=ing_id,
                max_quantity_from_rule=None,  # Será aplicado na validação individual
                item_quantity=item_quantity,
                base_portions=0,  # Extras sempre têm portions = 0
                cur=cur  # Reutiliza conexão existente
            )
            
            ingredients_data[ing_id] = max_available_info
        except Exception as e:
            logger.warning(f"Erro ao calcular quantidade máxima para ingrediente {ing_id}: {e}", exc_info=True)
            # Fallback: retorna disponibilidade zero em caso de erro
            current_stock_decimal = Decimal(str(current_stock or 0))
            ingredients_data[ing_id] = {
                'max_available': 0,
                'limited_by': 'error',
                'stock_info': {
                    'current_stock': current_stock_decimal,
                    'stock_unit': stock_unit or 'un',
                    'base_portion_quantity': Decimal(str(base_portion_quantity or 1)),
                    'base_portion_unit': base_portion_unit or 'un'
                }
            }
    
    return ingredients_data


def _check_product_stock_availability(cur, product_id, quantity):
    """
    Verifica se há estoque suficiente para um produto.
    Faz conversão correta de unidades antes de verificar.
    Retorna (is_available, message)
    """
    try:
        # Busca ingredientes do produto com informações completas de unidades
        cur.execute("""
            SELECT 
                i.ID, 
                i.NAME, 
                pi.PORTIONS, 
                i.CURRENT_STOCK, 
                i.STOCK_UNIT,
                i.BASE_PORTION_QUANTITY,
                i.BASE_PORTION_UNIT
            FROM PRODUCT_INGREDIENTS pi
            JOIN INGREDIENTS i ON pi.INGREDIENT_ID = i.ID
            WHERE pi.PRODUCT_ID = ? AND i.IS_AVAILABLE = TRUE
        """, (product_id,))
        
        ingredients = cur.fetchall()
        if not ingredients:
            return (True, "Produto sem ingredientes cadastrados")
        
        for row in ingredients:
            name = row[1]
            portions = row[2] or 0
            current_stock = row[3] or 0
            stock_unit = row[4] or 'un'
            base_portion_quantity = row[5] or 1
            base_portion_unit = row[6] or 'un'
            
            # Calcula consumo convertido para unidade do estoque
            try:
                required_quantity = stock_service.calculate_consumption_in_stock_unit(
                    portions=portions,
                    base_portion_quantity=base_portion_quantity,
                    base_portion_unit=base_portion_unit,
                    stock_unit=stock_unit,
                    item_quantity=quantity
                )
            except ValueError as e:
                return (False, f"Erro na conversão de unidades para '{name}': {str(e)}")
            
            # Converte current_stock para Decimal para comparação precisa
            current_stock_decimal = Decimal(str(current_stock))
            
            if current_stock_decimal < required_quantity:
                return (False, f"Estoque insuficiente de '{name}'. Necessário: {required_quantity:.3f} {stock_unit}, Disponível: {current_stock_decimal:.3f} {stock_unit}")
        
        return (True, "Estoque disponível")
        
    except Exception as e:
        logger.error(f"Erro ao verificar estoque do produto: {e}", exc_info=True)
        return (False, "Erro ao verificar disponibilidade de estoque")


def _check_ingredient_stock_availability(cur, ingredient_id, quantity):
    """
    Verifica se há estoque suficiente para um ingrediente específico.
    Retorna (is_available, message)
    """
    try:
        cur.execute("""
            SELECT NAME, CURRENT_STOCK, STOCK_UNIT, IS_AVAILABLE
            FROM INGREDIENTS
            WHERE ID = ?
        """, (ingredient_id,))
        
        result = cur.fetchone()
        if not result:
            return (False, "Ingrediente não encontrado")
        
        name, current_stock, stock_unit, is_available = result
        
        if not is_available:
            return (False, f"Ingrediente '{name}' não está disponível")
        
        current_stock = float(current_stock or 0)
        if current_stock < quantity:
            return (False, f"Estoque insuficiente de '{name}'. Necessário: {quantity:.2f} {stock_unit}, Disponível: {current_stock:.2f} {stock_unit}")
        
        return (True, "Estoque disponível")
        
    except Exception as e:
        logger.error(f"Erro ao verificar estoque do ingrediente: {e}", exc_info=True)
        return (False, "Erro ao verificar disponibilidade de estoque")


def remove_cart_item(user_id, cart_item_id):
    """
    Remove um item do carrinho
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o item pertence ao usuário
        sql = """
            SELECT ci.ID FROM CART_ITEMS ci
            JOIN CARTS c ON ci.CART_ID = c.ID
            WHERE ci.ID = ? AND c.USER_ID = ? AND c.IS_ACTIVE = TRUE;
        """
        cur.execute(sql, (cart_item_id, user_id))
        if not cur.fetchone():
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no seu carrinho")
        
        # CORREÇÃO: Remove explicitamente os extras antes de remover o item
        # (garante remoção mesmo se não houver cascade configurado)
        cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?;", (cart_item_id,))
        
        # Remove o item
        sql = "DELETE FROM CART_ITEMS WHERE ID = ?;"
        cur.execute(sql, (cart_item_id,))
        
        conn.commit()
        return (True, None, "Item removido do carrinho com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao remover item do carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def remove_cart_item_by_cart(cart_id, cart_item_id):
    """
    Remove item do carrinho convidado (por cart_id)
    """
    conn = None
    try:
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()

        sql = (
            "SELECT ci.ID FROM CART_ITEMS ci "
            "JOIN CARTS c ON ci.CART_ID = c.ID "
            "WHERE ci.ID = ? AND c.ID = ? AND c.USER_ID IS NULL AND c.IS_ACTIVE = TRUE;"
        )
        cur.execute(sql, (cart_item_id, cart_id))
        if not cur.fetchone():
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no carrinho informado")

        # CORREÇÃO: Remove explicitamente os extras antes de remover o item
        # (garante remoção mesmo se não houver cascade configurado)
        cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?;", (cart_item_id,))
        
        # Remove o item
        cur.execute("DELETE FROM CART_ITEMS WHERE ID = ?;", (cart_item_id,))
        conn.commit()
        return (True, None, "Item removido do carrinho com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao remover item do carrinho por cart_id: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def clear_cart(user_id):
    """
    Limpa todo o carrinho do usuário
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca carrinho ativo
        sql = "SELECT ID FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (user_id,))
        cart = cur.fetchone()
        
        if cart:
            cart_id = cart[0]
            # Remove todos os itens (cascade remove os extras)
            sql = "DELETE FROM CART_ITEMS WHERE CART_ID = ?;"
            cur.execute(sql, (cart_id,))
        
        conn.commit()
        return (True, None, "Carrinho limpo com sucesso")
        
    except fdb.Error as e:
        logger.error(f"Erro ao limpar carrinho: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_cart_for_order(user_id):
    """
    Busca o carrinho do usuário para conversão em pedido
    Retorna os dados necessários para criar o pedido
    """
    cart_summary = get_cart_summary(user_id)
    if not cart_summary or cart_summary["summary"]["is_empty"]:
        return None
    
    # Converte para formato de pedido
    order_items = []
    for item in cart_summary["items"]:
        order_item = {
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "extras": [],
            "base_modifications": []
        }
        
        for extra in item["extras"]:
            order_item["extras"].append({
                "ingredient_id": extra["ingredient_id"],
                "quantity": extra["quantity"]
            })
        
        for base_mod in item.get("base_modifications", []):
            order_item["base_modifications"].append({
                "ingredient_id": base_mod["ingredient_id"],
                "delta": base_mod["delta"]
            })
        
        order_items.append(order_item)
    
    return {
        "cart_id": cart_summary["cart"]["id"],
        "items": order_items,
        "total_amount": cart_summary["summary"]["subtotal"]
    }


def get_cart_summary_by_cart_id(cart_id):
    """
    Retorna o resumo do carrinho por cart_id (convidado)
    """
    items = get_cart_items(cart_id)
    if items is None:
        return None

    # OTIMIZAÇÃO: Usar função otimizada de disponibilidade (seção 1.7)
    availability_alerts = _check_availability_alerts(items)

    # Calcula totais
    total_items = sum(item["quantity"] for item in items)
    subtotal = sum(item["item_subtotal"] for item in items)

    return {
        "cart": {"id": cart_id, "user_id": None},
        "items": items,
        "summary": {
            "total_items": total_items,
            "subtotal": subtotal,
            "total": subtotal,
            "is_empty": len(items) == 0,
            "availability_alerts": availability_alerts
        }
    }


def validate_guest_cart_for_order(cart_id):
    """
    Valida se um carrinho de convidado pode ser convertido em pedido.
    Verifica disponibilidade de produtos e ingredientes.
    Retorna (is_valid, alerts, total_amount)
    """
    conn = None
    try:
        # Valida e converte cart_id
        cart_id = _validate_cart_id(cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o carrinho existe e está ativo
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (cart_id,))
        if not cur.fetchone():
            return (False, ["Carrinho não encontrado ou inativo"], 0.0)
        
        # Busca itens do carrinho
        items = get_cart_items(cart_id)
        if not items:
            return (False, ["Carrinho vazio"], 0.0)
        
        alerts = []
        total_amount = 0.0
        
        for item in items:
            product_id = item["product_id"]
            quantity = item["quantity"]
            
            # Verifica se produto está ativo
            cur.execute("SELECT IS_ACTIVE, PRICE FROM PRODUCTS WHERE ID = ?;", (product_id,))
            product_row = cur.fetchone()
            if not product_row or not product_row[0]:
                alerts.append(f"Produto {item['product']['name']} não está mais disponível")
                continue
            
            product_price = float(product_row[1]) if product_row[1] else 0.0
            item_total = product_price * quantity
            
            # Verifica ingredientes base do produto
            cur.execute(
                """
                SELECT i.ID, i.NAME, i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON i.ID = pi.INGREDIENT_ID
                WHERE pi.PRODUCT_ID = ?
                """,
                (product_id,)
            )
            for ing_id, ing_name, is_available in cur.fetchall():
                if not is_available:
                    alerts.append(f"Ingrediente '{ing_name}' do produto '{item['product']['name']}' está indisponível")
            
            # Verifica extras
            for extra in item.get("extras", []):
                extra_id = extra["ingredient_id"]
                extra_qty = extra["quantity"]
                
                cur.execute("SELECT NAME, IS_AVAILABLE, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ?;", (extra_id,))
                extra_row = cur.fetchone()
                if not extra_row:
                    alerts.append(f"Extra {extra_id} não encontrado")
                    continue
                
                extra_name, is_available, extra_price = extra_row
                if not is_available:
                    alerts.append(f"Extra '{extra_name}' está indisponível")
                else:
                    item_total += float(extra_price) * extra_qty
            
            total_amount += item_total
        
        is_valid = len(alerts) == 0
        return (is_valid, alerts, total_amount)
        
    except fdb.Error as e:
        logger.error(f"Erro ao validar carrinho de convidado: {e}", exc_info=True)
        return (False, ["Erro interno do servidor"], 0.0)
    finally:
        if conn: conn.close()


def claim_guest_cart(guest_cart_id, user_id):
    """
    Reivindica um carrinho convidado para um usuário.
    V1: Se o usuário não possui carrinho ativo, apenas atualiza USER_ID.
    V2-lite: Se já possui carrinho ativo, mescla itens do convidado e desativa o convidado.
    """
    conn = None
    try:
        # Valida e converte guest_cart_id
        guest_cart_id = _validate_cart_id(guest_cart_id)
        
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica carrinho convidado
        cur.execute("SELECT ID FROM CARTS WHERE ID = ? AND USER_ID IS NULL AND IS_ACTIVE = TRUE;", (guest_cart_id,))
        guest_row = cur.fetchone()
        if not guest_row:
            return (False, "CART_NOT_FOUND", "Carrinho convidado não encontrado")

        # Verifica se usuário já possui carrinho ativo
        cur.execute("SELECT ID FROM CARTS WHERE USER_ID = ? AND IS_ACTIVE = TRUE;", (user_id,))
        user_cart_row = cur.fetchone()

        if not user_cart_row:
            # Atualiza o carrinho convidado para o usuário
            cur.execute("UPDATE CARTS SET USER_ID = ? WHERE ID = ? AND USER_ID IS NULL;", (user_id, guest_cart_id))
            if cur.rowcount == 0:
                return (False, "CONFLICT", "Carrinho já foi reivindicado")
            conn.commit()
            return (True, None, "Carrinho reivindicado com sucesso")

        # Mescla itens: usa carrinho existente do usuário
        user_cart_id = user_cart_row[0]

        # Copia itens do convidado para o carrinho do usuário (mescla por item idêntico)
        cur.execute("SELECT ID, PRODUCT_ID, QUANTITY, CAST(NOTES AS VARCHAR(1000)) FROM CART_ITEMS WHERE CART_ID = ?;", (guest_cart_id,))
        guest_items = cur.fetchall()
        for item_id, product_id, quantity, notes in guest_items:
            # Busca extras e base_modifications do item convidado (com TYPE, DELTA, UNIT_PRICE)
            cur.execute(
                "SELECT INGREDIENT_ID, COALESCE(DELTA, QUANTITY) AS DELTA, TYPE, UNIT_PRICE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? ORDER BY TYPE, INGREDIENT_ID;",
                (item_id,)
            )
            extras_rows = cur.fetchall()
            
            # Separa extras e base_modifications
            extras = []
            base_modifications = []
            for r in extras_rows:
                row_type = (r[2] or 'extra').lower()
                if row_type == 'extra':
                    extras.append({"ingredient_id": r[0], "quantity": r[1]})
                elif row_type == 'base':
                    base_modifications.append({"ingredient_id": r[0], "delta": r[1]})

            # Verifica item idêntico no carrinho do usuário (inclui base_modifications)
            identical_id = find_identical_cart_item(user_cart_id, product_id, extras, notes or "", base_modifications)
            if identical_id:
                cur.execute("UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;", (quantity, identical_id))
            else:
                cur.execute(
                    "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;",
                    (user_cart_id, product_id, quantity, notes)
                )
                new_user_item_id = cur.fetchone()[0]
                
                # Insere extras (TYPE='extra')
                for ex in extras:
                    cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ?;", (ex["ingredient_id"],))
                    price_row = cur.fetchone()
                    unit_price = float(price_row[0] or 0.0) if price_row else 0.0
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);",
                        (new_user_item_id, ex["ingredient_id"], ex["quantity"], ex["quantity"], unit_price)
                    )
                
                # Insere base_modifications (TYPE='base')
                for bm in base_modifications:
                    cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ?;", (bm["ingredient_id"],))
                    price_row = cur.fetchone()
                    unit_price = float(price_row[0] or 0.0) if price_row else 0.0
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);",
                        (new_user_item_id, bm["ingredient_id"], bm["delta"], unit_price)
                    )

        # Deleta o carrinho convidado após mesclar (os itens já foram copiados)
        # Usa DELETE em vez de UPDATE para evitar violação da constraint UK_CARTS_USER_ACTIVE
        # As foreign keys têm ON DELETE CASCADE, então os itens e extras serão deletados automaticamente
        cur.execute("DELETE FROM CARTS WHERE ID = ?;", (guest_cart_id,))
        conn.commit()
        return (True, None, "Carrinho mesclado com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao reivindicar carrinho convidado: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()
