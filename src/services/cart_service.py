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
                p.IMAGE_URL as PRODUCT_IMAGE_URL
            FROM CART_ITEMS ci
            JOIN PRODUCTS p ON ci.PRODUCT_ID = p.ID
            WHERE ci.CART_ID = ?
            ORDER BY ci.CREATED_AT;
        """
        cur.execute(sql, (cart_id,))
        items = []
        
        for row in cur.fetchall():
            item_id = row[0]
            product_id = row[1]
            quantity = row[2]
            notes = row[3]
            product_name = row[4]
            product_price = float(row[5]) if row[5] else 0.0
            product_description = row[6]
            product_image_url = row[7]
            
            # Busca extras do item
            extras_sql = """
                SELECT 
                    cie.ID,
                    cie.INGREDIENT_ID,
                    COALESCE(cie.DELTA, cie.QUANTITY) as DELTA,
                    COALESCE(cie.UNIT_PRICE, COALESCE(i.ADDITIONAL_PRICE, i.PRICE)) as UNIT_PRICE,
                    cie.TYPE,
                    i.NAME as INGREDIENT_NAME
                FROM CART_ITEM_EXTRAS cie
                JOIN INGREDIENTS i ON cie.INGREDIENT_ID = i.ID
                WHERE cie.CART_ITEM_ID = ?
                ORDER BY cie.TYPE, i.NAME;
            """
            cur.execute(extras_sql, (item_id,))
            extras = []
            extras_total = 0.0
            base_modifications = []
            base_mods_total = 0.0
            
            for extra_row in cur.fetchall():
                row_id = extra_row[0]
                ingredient_id = extra_row[1]
                delta = int(extra_row[2] or 0)
                unit_price = float(extra_row[3] or 0.0)
                row_type = (extra_row[4] or 'extra').lower()
                ingredient_name = extra_row[5]

                if row_type == 'extra':
                    extras.append({
                        "id": row_id,
                        "ingredient_id": ingredient_id,
                        "quantity": delta,
                        "ingredient_name": ingredient_name,
                        "ingredient_price": unit_price
                    })
                    if delta > 0:
                        extras_total += unit_price * delta
                else:  # base
                    base_modifications.append({
                        "ingredient_id": ingredient_id,
                        "delta": delta,
                        "ingredient_name": ingredient_name
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
                    "image_url": product_image_url
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
    availability_alerts = []
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        for item in items:
            # Disponibilidade de ingredientes base do produto
            cur.execute(
                """
                SELECT i.ID, i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON i.ID = pi.INGREDIENT_ID
                WHERE pi.PRODUCT_ID = ?
                """,
                (item["product_id"],)
            )
            for ing_id, is_av in cur.fetchall():
                if not is_av:
                    availability_alerts.append({
                        "product_id": item["product_id"],
                        "ingredient_id": ing_id,
                        "issue": "ingredient_unavailable"
                    })
            
            # Disponibilidade de extras
            for extra in item.get("extras", []):
                cur.execute("SELECT IS_AVAILABLE FROM INGREDIENTS WHERE ID = ?", (extra["ingredient_id"],))
                row = cur.fetchone()
                if row and row[0] is False:
                    availability_alerts.append({
                        "product_id": item["product_id"],
                        "ingredient_id": extra["ingredient_id"],
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
        
        # Verifica estoque suficiente para o produto
        stock_check = _check_product_stock_availability(cur, product_id, quantity)
        if not stock_check[0]:
            return (False, "INSUFFICIENT_STOCK", stock_check[1])
        
        # Verifica e valida extras conforme regras do produto (PORTIONS=0, min/max)
        rules = _get_product_rules(cur, product_id)
        if extras:
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
                
                # Verifica disponibilidade em tempo real do ingrediente
                from .product_service import get_ingredient_max_available_quantity
                max_available_info = get_ingredient_max_available_quantity(
                    ingredient_id=ing_id,
                    max_quantity_from_rule=max_q_rule,
                    item_quantity=quantity
                )
                
                max_q_available = max_available_info['max_available']
                
                # Usa o menor entre a regra e o estoque disponível
                effective_max_q = max_q_available
                if max_q_rule is not None and max_q_rule > 0:
                    effective_max_q = min(max_q_rule, max_q_available)
                
                # Valida quantidade mínima
                if qty < min_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra abaixo do mínimo permitido [{min_q}]")
                
                # Valida quantidade máxima (considerando estoque)
                if effective_max_q > 0 and qty > effective_max_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra excede o disponível. "
                           f"Máximo permitido: {effective_max_q} "
                           f"(limitado por {'regra' if max_available_info['limited_by'] == 'rule' else 'estoque'})")
                
                # Verifica se ingrediente está disponível
                if not max_available_info['stock_info'] or max_q_available == 0:
                    # Busca nome do ingrediente para mensagem de erro
                    cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ?", (ing_id,))
                    ing_name_row = cur.fetchone()
                    ing_name = ing_name_row[0] if ing_name_row else 'Ingrediente'
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                
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
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades: {str(e)}")
                
                # Compara com estoque disponível
                if current_stock < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra. "
                           f"Necessário: {required_quantity:.3f} {stock_unit}, "
                           f"Disponível: {current_stock:.3f} {stock_unit}")
        
        # Verifica se já existe um item idêntico (produto, extras, notes e base_mods)
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
                
                # Valida estoque para extras com a nova quantidade total
                if extras:
                    for extra in extras:
                        ing_id = extra.get("ingredient_id")
                        qty = int(extra.get("quantity", 1))
                        rule = rules.get(ing_id)
                        max_q_rule = int(rule["max_quantity"]) if rule and rule.get("max_quantity") else None
                        
                        # Verifica disponibilidade em tempo real para a nova quantidade total
                        from .product_service import get_ingredient_max_available_quantity
                        max_available_info = get_ingredient_max_available_quantity(
                            ingredient_id=ing_id,
                            max_quantity_from_rule=max_q_rule,
                            item_quantity=new_total_quantity
                        )
                        
                        # Verifica estoque suficiente para a quantidade solicitada com conversão de unidades
                        stock_info = max_available_info.get('stock_info')
                        if not stock_info:
                            cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ?", (ing_id,))
                            ing_name_row = cur.fetchone()
                            ing_name = ing_name_row[0] if ing_name_row else 'Ingrediente'
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                        
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
                            cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ?", (ing_id,))
                            ing_name_row = cur.fetchone()
                            ing_name = ing_name_row[0] if ing_name_row else 'Ingrediente'
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                        
                        # Compara com estoque disponível
                        if current_stock < required_quantity_total:
                            cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ?", (ing_id,))
                            ing_name_row = cur.fetchone()
                            ing_name = ing_name_row[0] if ing_name_row else 'Ingrediente'
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
            
            # Adiciona extras se fornecidos (TYPE='extra')
            if extras:
                for extra in extras:
                    ingredient_id = extra.get("ingredient_id")
                    extra_quantity = int(extra.get("quantity", 1))
                    if extra_quantity <= 0:
                        continue
                    # Verifica se ingrediente existe e obtém preço
                    cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ingredient_id,))
                    rowp = cur.fetchone()
                    if rowp:
                        unit_price = float(rowp[0] or 0.0)
                        sql_extra = (
                            "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) "
                            "VALUES (?, ?, ?, 'extra', ?, ?);"
                        )
                        cur.execute(sql_extra, (new_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price))

            # Adiciona modificações de base (TYPE='base')
            if base_modifications:
                rules = _get_product_rules(cur, product_id)
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                    except (ValueError, TypeError, AttributeError):
                        # Ignora modificações com formato inválido
                        continue
                    rule = rules.get(ing_id)
                    if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                        continue
                    cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ing_id,))
                    rowp = cur.fetchone()
                    unit_price = float(rowp[0] or 0.0) if rowp else 0.0
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

        # Verifica e valida extras conforme regras do produto (PORTIONS=0, min/max)
        rules = _get_product_rules(cur, product_id)
        if extras:
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
                
                # Verifica disponibilidade em tempo real do ingrediente
                from .product_service import get_ingredient_max_available_quantity
                max_available_info = get_ingredient_max_available_quantity(
                    ingredient_id=ing_id,
                    max_quantity_from_rule=max_q_rule,
                    item_quantity=quantity
                )
                
                max_q_available = max_available_info['max_available']
                
                # Usa o menor entre a regra e o estoque disponível
                effective_max_q = max_q_available
                if max_q_rule is not None and max_q_rule > 0:
                    effective_max_q = min(max_q_rule, max_q_available)
                
                # Valida quantidade mínima
                if qty < min_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra abaixo do mínimo permitido [{min_q}]")
                
                # Valida quantidade máxima (considerando estoque)
                if effective_max_q > 0 and qty > effective_max_q:
                    return (False, "EXTRA_OUT_OF_RANGE", 
                           f"Quantidade de extra excede o disponível. "
                           f"Máximo permitido: {effective_max_q} "
                           f"(limitado por {'regra' if max_available_info['limited_by'] == 'rule' else 'estoque'})")
                
                # Verifica se ingrediente está disponível
                if not max_available_info['stock_info'] or max_q_available == 0:
                    # Busca nome do ingrediente para mensagem de erro
                    cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ?", (ing_id,))
                    ing_name_row = cur.fetchone()
                    ing_name = ing_name_row[0] if ing_name_row else 'Ingrediente'
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Ingrediente '{ing_name}' não disponível ou sem estoque")
                
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
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Erro na conversão de unidades: {str(e)}")
                
                # Compara com estoque disponível
                if current_stock < required_quantity:
                    return (False, "INSUFFICIENT_STOCK", 
                           f"Estoque insuficiente para extra. "
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
                
                # Valida estoque para extras com a nova quantidade total
                if extras:
                    for extra in extras:
                        ing_id = extra.get("ingredient_id")
                        qty = int(extra.get("quantity", 1))
                        
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
                        
                        # Calcula consumo para a NOVA quantidade total
                        try:
                            required_quantity_total = stock_service.calculate_consumption_in_stock_unit(
                                portions=qty,
                                base_portion_quantity=base_portion_quantity,
                                base_portion_unit=base_portion_unit,
                                stock_unit=stock_unit,
                                item_quantity=new_total_quantity  # ← Usa quantidade total
                            )
                        except ValueError as e:
                            return (False, "INSUFFICIENT_STOCK", 
                                   f"Erro na conversão de unidades para extra '{ing_name}': {str(e)}")
                        
                        current_stock_decimal = Decimal(str(current_stock))
                        
                        if current_stock_decimal < required_quantity_total:
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

            if extras:
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
                            (new_item_id, ingredient_id, extra_quantity, extra_quantity, unit_price)
                        )

            if base_modifications:
                rules = _get_product_rules(cur, product_id)
                for bm in base_modifications:
                    try:
                        ing_id = int(bm.get("ingredient_id"))
                        delta = int(bm.get("delta", 0))
                    except (ValueError, TypeError, AttributeError):
                        # Ignora modificações com formato inválido
                        continue
                    rule = rules.get(ing_id)
                    if not rule or float(rule["portions"]) == 0.0 or delta == 0:
                        continue
                    cur.execute("SELECT COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;", (ing_id,))
                    rowp = cur.fetchone()
                    unit_price = float(rowp[0] or 0.0) if rowp else 0.0
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
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do mesmo produto
        sql = "SELECT ID, CAST(NOTES AS VARCHAR(1000)) FROM CART_ITEMS WHERE CART_ID = ? AND PRODUCT_ID = ?;"
        cur.execute(sql, (cart_id, product_id))
        items = cur.fetchall()

        for item_id, existing_notes in items:
            # Busca todas as linhas (extras e base) e normaliza
            cur.execute(
                "SELECT INGREDIENT_ID, COALESCE(DELTA, QUANTITY) AS DELTA, TYPE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? ORDER BY TYPE, INGREDIENT_ID;",
                (item_id,)
            )
            rows = cur.fetchall()
            existing_extras = [(r[0], int(r[1])) for r in rows if (r[2] or 'extra').lower() == 'extra']
            existing_base = [(r[0], int(r[1])) for r in rows if (r[2] or 'extra').lower() == 'base' and int(r[1]) != 0]

            wanted_extras = []
            for ex in (extras or []):
                try:
                    wanted_extras.append((int(ex.get("ingredient_id")), int(ex.get("quantity", 1))))
                except (ValueError, TypeError, AttributeError):
                    # Ignora extras com formato inválido
                    continue
            wanted_extras.sort()

            wanted_base = []
            for bm in (base_modifications or []):
                try:
                    d = int(bm.get("delta", 0))
                    if d != 0:
                        wanted_base.append((int(bm.get("ingredient_id")), d))
                except (ValueError, TypeError, AttributeError):
                    # Ignora modificações com formato inválido
                    continue
            wanted_base.sort()

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
        
        # Remove o item (cascade remove os extras automaticamente)
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

    # Validação básica de disponibilidade (produto e extras disponíveis)
    availability_alerts = []
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for item in items:
            # Disponibilidade de ingredientes base do produto
            cur.execute(
                """
                SELECT i.ID, i.IS_AVAILABLE
                FROM PRODUCT_INGREDIENTS pi
                JOIN INGREDIENTS i ON i.ID = pi.INGREDIENT_ID
                WHERE pi.PRODUCT_ID = ?
                """,
                (item["product_id"],)
            )
            for ing_id, is_av in cur.fetchall():
                if not is_av:
                    availability_alerts.append({
                        "product_id": item["product_id"],
                        "ingredient_id": ing_id,
                        "issue": "ingredient_unavailable"
                    })
            # Disponibilidade de extras
            for extra in item.get("extras", []):
                cur.execute("SELECT IS_AVAILABLE FROM INGREDIENTS WHERE ID = ?", (extra["ingredient_id"],))
                row = cur.fetchone()
                if row and row[0] is False:
                    availability_alerts.append({
                        "product_id": item["product_id"],
                        "ingredient_id": extra["ingredient_id"],
                        "issue": "extra_unavailable"
                    })
    except Exception:
        pass
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass

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

        # Desativa o carrinho convidado após mesclar
        cur.execute("UPDATE CARTS SET IS_ACTIVE = FALSE WHERE ID = ?;", (guest_cart_id,))
        conn.commit()
        return (True, None, "Carrinho mesclado com sucesso")
    except fdb.Error as e:
        logger.error(f"Erro ao reivindicar carrinho convidado: {e}", exc_info=True)
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()
