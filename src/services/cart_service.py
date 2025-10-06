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
            product_name = row[3]
            product_price = float(row[4]) if row[4] else 0.0
            product_description = row[4]
            product_image_url = row[6]
            
            # Busca extras do item
            extras_sql = """
                SELECT 
                    cie.ID,
                    cie.INGREDIENT_ID,
                    cie.QUANTITY,
                    i.NAME as INGREDIENT_NAME,
                    i.PRICE as INGREDIENT_PRICE
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


def get_cart_summary(user_id):
    """
    Retorna o resumo completo do carrinho do usuário
    """
    cart = get_or_create_cart(user_id)
    if not cart:
        return None
    
    items = get_cart_items(cart["id"])
    
    # Calcula totais
    total_items = sum(item["quantity"] for item in items)
    subtotal = sum(item["item_subtotal"] for item in items)
    
    return {
        "cart": cart,
        "items": items,
        "summary": {
            "total_items": total_items,
            "subtotal": subtotal,
            "is_empty": len(items) == 0
        }
    }


def add_item_to_cart(user_id, product_id, quantity, extras=None):
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
        
        # Verifica se já existe um item idêntico (mesmo produto e mesmos extras)
        existing_item_id = find_identical_cart_item(cart_id, product_id, extras or [])
        
        if existing_item_id:
            # Incrementa quantidade do item existente
            sql = "UPDATE CART_ITEMS SET QUANTITY = QUANTITY + ? WHERE ID = ?;"
            cur.execute(sql, (quantity, existing_item_id))
        else:
            # Cria novo item
            sql = "INSERT INTO CART_ITEMS (CART_ID, PRODUCT_ID, QUANTITY) VALUES (?, ?, ?) RETURNING ID;"
            cur.execute(sql, (cart_id, product_id, quantity))
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


def find_identical_cart_item(cart_id, product_id, extras):
    """
    Verifica se já existe um item idêntico no carrinho (mesmo produto e mesmos extras)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca itens do mesmo produto
        sql = "SELECT ID FROM CART_ITEMS WHERE CART_ID = ? AND PRODUCT_ID = ?;"
        cur.execute(sql, (cart_id, product_id))
        items = cur.fetchall()
        
        for (item_id,) in items:
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
                
                if extras_match:
                    return item_id
        
        return None
        
    except fdb.Error as e:
        print(f"Erro ao verificar item idêntico: {e}")
        return None
    finally:
        if conn: conn.close()


def update_cart_item(user_id, cart_item_id, quantity=None, extras=None):
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
