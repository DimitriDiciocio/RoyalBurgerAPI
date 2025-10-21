from ..database import get_db_connection
import fdb
from datetime import datetime

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
        
        # Busca o carrinho criado
        sql = "SELECT ID, USER_ID, CREATED_AT, UPDATED_AT FROM CARTS WHERE ID = ?;"
        cur.execute(sql, (cart_id,))
        row = cur.fetchone()
        
        return {
            "id": row[0],
            "user_id": row[1],
            "created_at": row[2],
            "updated_at": row[3]
        }
        
    except fdb.Error as e:
        print(f"Erro ao buscar/criar carrinho: {e}")
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
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do carrinho
        sql = """
            SELECT 
                ci.ID,
                ci.PRODUCT_ID,
                ci.QUANTITY,
                ci.NOTES,
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
                    cie.QUANTITY,
                    i.NAME as INGREDIENT_NAME,
                    COALESCE(i.ADDITIONAL_PRICE, i.PRICE) as INGREDIENT_PRICE
                FROM CART_ITEM_EXTRAS cie
                JOIN INGREDIENTS i ON cie.INGREDIENT_ID = i.ID
                WHERE cie.CART_ITEM_ID = ?
                ORDER BY i.NAME;
            """
            cur.execute(extras_sql, (item_id,))
            extras = []
            extras_total = 0.0
            
            for extra_row in cur.fetchall():
                extra = {
                    "id": extra_row[0],
                    "ingredient_id": extra_row[1],
                    "quantity": extra_row[2],
                    "ingredient_name": extra_row[3],
                    "ingredient_price": float(extra_row[4]) if extra_row[4] else 0.0
                }
                extras.append(extra)
                extras_total += extra["ingredient_price"] * extra["quantity"]
            
            # Calcula subtotal do item
            item_subtotal = (product_price + extras_total) * quantity
            
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
                "extras_total": extras_total,
                "item_subtotal": item_subtotal
            }
            items.append(item)
        
        return items
        
    except fdb.Error as e:
        print(f"Erro ao buscar itens do carrinho: {e}")
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
        print(f"Erro ao buscar carrinho ativo do usuário: {e}")
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
        print(f"Erro ao buscar carrinho convidado: {e}")
        return None
    finally:
        if conn: conn.close()


def create_guest_cart():
    """
    Cria um novo carrinho convidado (USER_ID = NULL)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO CARTS (USER_ID, IS_ACTIVE) VALUES (NULL, TRUE) RETURNING ID;")
        cart_id = cur.fetchone()[0]
        conn.commit()
        return {"id": cart_id}
    except fdb.Error as e:
        print(f"Erro ao criar carrinho convidado: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()


def get_cart_summary(user_id):
    """
    Retorna o resumo completo do carrinho do usuário
    """
    cart = get_or_create_cart(user_id)
    if not cart:
        return None
    
    items = get_cart_items(cart["id"])

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

    # Calcula taxas/fees e descontos (simples; pode ser parametrizado em APP_SETTINGS)
    fees_percent = _get_setting_percent("CART_FEES_PERCENT", default=0.0)
    taxes_percent = _get_setting_percent("CART_TAXES_PERCENT", default=0.0)
    discount_percent = _get_setting_percent("CART_DISCOUNT_PERCENT", default=0.0)

    fees = round(subtotal * (fees_percent / 100.0), 2)
    taxes = round(subtotal * (taxes_percent / 100.0), 2)
    discounts = round(subtotal * (discount_percent / 100.0), 2)
    total = round(subtotal + fees + taxes - discounts, 2)
    
    return {
        "cart": cart,
        "items": items,
        "summary": {
            "total_items": total_items,
            "subtotal": subtotal,
            "fees": fees,
            "taxes": taxes,
            "discounts": discounts,
            "total": total,
            "is_empty": len(items) == 0,
            "availability_alerts": availability_alerts
        }
    }


def add_item_to_cart(user_id, product_id, quantity, extras=None, notes=None):
    """
    Adiciona um item ao carrinho do usuário
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca ou cria carrinho
        cart = get_or_create_cart(user_id)
        if not cart:
            return (False, "CART_ERROR", "Erro ao acessar carrinho")
        
        cart_id = cart["id"]
        
        # Verifica se produto existe e está ativo
        sql = "SELECT ID, NAME, PRICE FROM PRODUCTS WHERE ID = ? AND IS_ACTIVE = TRUE;"
        cur.execute(sql, (product_id,))
        product = cur.fetchone()
        if not product:
            return (False, "PRODUCT_NOT_FOUND", "Produto não encontrado ou inativo")
        
        # Verifica e valida extras conforme regras do produto (PORTIONS=0, min/max)
        rules = _get_product_rules(cur, product_id)
        if extras:
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} não permitido para o produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} é da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Extra {ing_id} fora do intervalo [{min_q}, {max_q or '∞'}]")

        # Verifica se já existe um item idêntico (mesmo produto, mesmos extras e mesmas notas)
        existing_item_id = find_identical_cart_item(cart_id, product_id, extras or [], notes or "")
        
        if existing_item_id:
            # Incrementa quantidade do item existente
            sql = "UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;"
            cur.execute(sql, (quantity, existing_item_id))
        else:
            # Cria novo item
            sql = "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;"
            cur.execute(sql, (cart_id, product_id, quantity, notes))
            new_item_id = cur.fetchone()[0]
            
            # Adiciona extras se fornecidos
            if extras:
                for extra in extras:
                    ingredient_id = extra.get("ingredient_id")
                    extra_quantity = extra.get("quantity", 1)
                    
                    # Verifica se ingrediente existe
                    sql_check = "SELECT ID FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;"
                    cur.execute(sql_check, (ingredient_id,))
                    if cur.fetchone():
                        sql_extra = "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY) VALUES (?, ?, ?);"
                        cur.execute(sql_extra, (new_item_id, ingredient_id, extra_quantity))
        
        conn.commit()
        return (True, None, "Item adicionado ao carrinho com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao adicionar item ao carrinho: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def add_item_to_cart_by_cart_id(cart_id, product_id, quantity, extras=None, notes=None):
    """
    Adiciona item ao carrinho identificado por cart_id (convidado)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

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

        # Verifica e valida extras conforme regras do produto
        rules = _get_product_rules(cur, product_id)
        if extras:
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} não permitido para o produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} é da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Extra {ing_id} fora do intervalo [{min_q}, {max_q or '∞'}]")

        # Verifica item idêntico
        existing_item_id = find_identical_cart_item(cart_id, product_id, extras or [], notes or "")

        if existing_item_id:
            sql = "UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;"
            cur.execute(sql, (quantity, existing_item_id))
        else:
            sql = "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;"
            cur.execute(sql, (cart_id, product_id, quantity, notes))
            new_item_id = cur.fetchone()[0]

            if extras:
                for extra in extras:
                    ingredient_id = extra.get("ingredient_id")
                    extra_quantity = extra.get("quantity", 1)
                    sql_check = "SELECT ID FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;"
                    cur.execute(sql_check, (ingredient_id,))
                    if cur.fetchone():
                        sql_extra = "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY) VALUES (?, ?, ?);"
                        cur.execute(sql_extra, (new_item_id, ingredient_id, extra_quantity))

        conn.commit()
        return (True, None, "Item adicionado ao carrinho com sucesso")
    except fdb.Error as e:
        print(f"Erro ao adicionar item ao carrinho por cart_id: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def _get_setting_percent(key, default=0.0):
    """Busca percentuais em APP_SETTINGS (0..100). Retorna float."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT SETTING_VALUE FROM APP_SETTINGS WHERE SETTING_KEY = ?", (key,))
        row = cur.fetchone()
        if not row or row[0] is None:
            return default
        try:
            return float(row[0])
        except Exception:
            return default
    except Exception:
        return default
    finally:
        if conn: conn.close()


def find_identical_cart_item(cart_id, product_id, extras, notes):
    """
    Verifica se já existe um item idêntico no carrinho (mesmo produto e mesmos extras)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do mesmo produto
        sql = "SELECT ID, NOTES FROM CART_ITEMS WHERE CART_ID = ? AND PRODUCT_ID = ?;"
        cur.execute(sql, (cart_id, product_id))
        items = cur.fetchall()
        
        for item_id, existing_notes in items:
            # Busca extras deste item
            sql_extras = "SELECT INGREDIENT_ID, QUANTITY FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? ORDER BY INGREDIENT_ID;"
            cur.execute(sql_extras, (item_id,))
            existing_extras = cur.fetchall()
            
            # Compara extras
            if len(existing_extras) == len(extras):
                extras_match = True
                for i, (ingredient_id, quantity) in enumerate(existing_extras):
                    if (i >= len(extras) or 
                        extras[i].get("ingredient_id") != ingredient_id or 
                        extras[i].get("quantity", 1) != quantity):
                        extras_match = False
                        break
                
                if extras_match and (existing_notes or "") == (notes or ""):
                    return item_id
        
        return None
        
    except fdb.Error as e:
        print(f"Erro ao verificar item idêntico: {e}")
        return None
    finally:
        if conn: conn.close()


def update_cart_item(user_id, cart_item_id, quantity=None, extras=None, notes=None):
    """
    Atualiza um item do carrinho
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
        
        # Atualiza quantidade se fornecida
        if quantity is not None:
            if quantity <= 0:
                return (False, "INVALID_QUANTITY", "Quantidade deve ser maior que zero")
            sql = "UPDATE CART_ITEMS SET QUANTITY = ? WHERE ID = ?;"
            cur.execute(sql, (quantity, cart_item_id))
        
        # Atualiza extras se fornecidos
        if extras is not None:
            # Valida conforme regras do produto deste item
            cur.execute("SELECT PRODUCT_ID FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
            row = cur.fetchone()
            if not row:
                return (False, "ITEM_NOT_FOUND", "Item não encontrado")
            product_id = row[0]
            rules = _get_product_rules(cur, product_id)
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} não permitido para o produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} é da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Extra {ing_id} fora do intervalo [{min_q}, {max_q or '∞'}]")
        # Atualiza notes se fornecido
        if notes is not None:
            sql = "UPDATE CART_ITEMS SET NOTES = ? WHERE ID = ?;"
            cur.execute(sql, (notes, cart_item_id))
            # Remove extras antigos
            sql = "DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?;"
            cur.execute(sql, (cart_item_id,))
            
            # Adiciona novos extras
            for extra in extras:
                ingredient_id = extra.get("ingredient_id")
                extra_quantity = extra.get("quantity", 1)
                
                # Verifica se ingrediente existe
                sql_check = "SELECT ID FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;"
                cur.execute(sql_check, (ingredient_id,))
                if cur.fetchone():
                    sql_extra = "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY) VALUES (?, ?, ?);"
                    cur.execute(sql_extra, (cart_item_id, ingredient_id, extra_quantity))
        
        conn.commit()
        return (True, None, "Item atualizado com sucesso")
        
    except fdb.Error as e:
        print(f"Erro ao atualizar item do carrinho: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def update_cart_item_by_cart(cart_id, cart_item_id, quantity=None, extras=None, notes=None):
    """
    Atualiza um item do carrinho para carrinho convidado (por cart_id)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Verifica se o item pertence ao carrinho convidado
        sql = (
            "SELECT ci.ID FROM CART_ITEMS ci "
            "JOIN CARTS c ON ci.CART_ID = c.ID "
            "WHERE ci.ID = ? AND c.ID = ? AND c.USER_ID IS NULL AND c.IS_ACTIVE = TRUE;"
        )
        cur.execute(sql, (cart_item_id, cart_id))
        if not cur.fetchone():
            return (False, "ITEM_NOT_FOUND", "Item não encontrado no carrinho informado")

        if quantity is not None:
            if quantity <= 0:
                return (False, "INVALID_QUANTITY", "Quantidade deve ser maior que zero")
            cur.execute("UPDATE CART_ITEMS SET QUANTITY = ? WHERE ID = ?;", (quantity, cart_item_id))

        if extras is not None:
            # Valida conforme regras do produto deste item
            cur.execute("SELECT PRODUCT_ID FROM CART_ITEMS WHERE ID = ?", (cart_item_id,))
            row = cur.fetchone()
            if not row:
                return (False, "ITEM_NOT_FOUND", "Item não encontrado")
            product_id = row[0]
            rules = _get_product_rules(cur, product_id)
            for extra in extras:
                ing_id = extra.get("ingredient_id")
                qty = int(extra.get("quantity", 1))
                rule = rules.get(ing_id)
                if not rule:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} não permitido para o produto")
                if float(rule["portions"]) != 0.0:
                    return (False, "EXTRA_NOT_ALLOWED", f"Ingrediente {ing_id} é da receita base")
                min_q = int(rule["min_quantity"] or 0)
                max_q = int(rule["max_quantity"] or 0)
                if qty < min_q or (max_q > 0 and qty > max_q):
                    return (False, "EXTRA_OUT_OF_RANGE", f"Extra {ing_id} fora do intervalo [{min_q}, {max_q or '∞'}]")

            # Atualiza notes
            if notes is not None:
                cur.execute("UPDATE CART_ITEMS SET NOTES = ? WHERE ID = ?;", (notes, cart_item_id))

            # Remove extras antigos e adiciona novos
            cur.execute("DELETE FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ?;", (cart_item_id,))
            for extra in extras:
                ingredient_id = extra.get("ingredient_id")
                extra_quantity = extra.get("quantity", 1)
                sql_check = "SELECT ID FROM INGREDIENTS WHERE ID = ? AND IS_AVAILABLE = TRUE;"
                cur.execute(sql_check, (ingredient_id,))
                if cur.fetchone():
                    sql_extra = "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY) VALUES (?, ?, ?);"
                    cur.execute(sql_extra, (cart_item_id, ingredient_id, extra_quantity))

        conn.commit()
        return (True, None, "Item atualizado com sucesso")
    except fdb.Error as e:
        print(f"Erro ao atualizar item do carrinho por cart_id: {e}")
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
        print(f"Erro ao remover item do carrinho: {e}")
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
        print(f"Erro ao remover item do carrinho por cart_id: {e}")
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
        print(f"Erro ao limpar carrinho: {e}")
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
            "extras": []
        }
        
        for extra in item["extras"]:
            order_item["extras"].append({
                "ingredient_id": extra["ingredient_id"],
                "quantity": extra["quantity"]
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

    # Calcula totais
    total_items = sum(item["quantity"] for item in items)
    subtotal = sum(item["item_subtotal"] for item in items)

    fees_percent = _get_setting_percent("CART_FEES_PERCENT", default=0.0)
    taxes_percent = _get_setting_percent("CART_TAXES_PERCENT", default=0.0)
    discount_percent = _get_setting_percent("CART_DISCOUNT_PERCENT", default=0.0)

    fees = round(subtotal * (fees_percent / 100.0), 2)
    taxes = round(subtotal * (taxes_percent / 100.0), 2)
    discounts = round(subtotal * (discount_percent / 100.0), 2)
    total = round(subtotal + fees + taxes - discounts, 2)

    return {
        "cart": {"id": cart_id, "user_id": None},
        "items": items,
        "summary": {
            "total_items": total_items,
            "subtotal": subtotal,
            "fees": fees,
            "taxes": taxes,
            "discounts": discounts,
            "total": total,
            "is_empty": len(items) == 0,
            "availability_alerts": []
        }
    }


def claim_guest_cart(guest_cart_id, user_id):
    """
    Reivindica um carrinho convidado para um usuário.
    V1: Se o usuário não possui carrinho ativo, apenas atualiza USER_ID.
    V2-lite: Se já possui carrinho ativo, mescla itens do convidado e desativa o convidado.
    """
    conn = None
    try:
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
        cur.execute("SELECT ID, PRODUCT_ID, QUANTITY, NOTES FROM CART_ITEMS WHERE CART_ID = ?;", (guest_cart_id,))
        guest_items = cur.fetchall()
        for item_id, product_id, quantity, notes in guest_items:
            # Busca extras do item convidado
            cur.execute("SELECT INGREDIENT_ID, QUANTITY FROM CART_ITEM_EXTRAS WHERE CART_ITEM_ID = ? ORDER BY INGREDIENT_ID;", (item_id,))
            extras_rows = cur.fetchall()
            extras = [{"ingredient_id": r[0], "quantity": r[1]} for r in extras_rows]

            # Verifica item idêntico no carrinho do usuário
            identical_id = find_identical_cart_item(user_cart_id, product_id, extras, notes or "")
            if identical_id:
                cur.execute("UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;", (quantity, identical_id))
            else:
                cur.execute(
                    "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY, NOTES) VALUES (?, ?, ?, ?) RETURNING ID;",
                    (user_cart_id, product_id, quantity, notes)
                )
                new_user_item_id = cur.fetchone()[0]
                for ex in extras:
                    cur.execute(
                        "INSERT INTO CART_ITEM_EXTRAS (CART_ITEM_ID, INGREDIENT_ID, QUANTITY) VALUES (?, ?, ?);",
                        (new_user_item_id, ex["ingredient_id"], ex["quantity"])
                    )

        # Desativa o carrinho convidado após mesclar
        cur.execute("UPDATE CARTS SET IS_ACTIVE = FALSE WHERE ID = ?;", (guest_cart_id,))
        conn.commit()
        return (True, None, "Carrinho mesclado com sucesso")
    except fdb.Error as e:
        print(f"Erro ao reivindicar carrinho convidado: {e}")
        if conn: conn.rollback()
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()
