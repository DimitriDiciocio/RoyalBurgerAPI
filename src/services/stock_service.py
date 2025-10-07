import fdb
from ..database import get_db_connection


def deduct_stock_for_order(order_id):
    """
    Deduz o estoque dos ingredientes baseado nos produtos do pedido.
    Retorna (sucesso, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca todos os itens do pedido
        cur.execute("""
            SELECT PRODUCT_ID, QUANTITY 
            FROM ORDER_ITEMS 
            WHERE ORDER_ID = ?
        """, (order_id,))
        order_items = cur.fetchall()
        
        if not order_items:
            return (True, None, "Pedido sem itens")
        
        # Dicionário para acumular quantidades de ingredientes
        ingredient_deductions = {}
        
        # Processa cada item do pedido
        for product_id, quantity in order_items:
            # Busca ingredientes do produto
            cur.execute("""
                SELECT INGREDIENT_ID, QUANTITY 
                FROM PRODUCT_INGREDIENTS 
                WHERE PRODUCT_ID = ?
            """, (product_id,))
            product_ingredients = cur.fetchall()
            
            # Adiciona ingredientes base do produto
            for ingredient_id, ingredient_quantity in product_ingredients:
                total_needed = ingredient_quantity * quantity
                if ingredient_id in ingredient_deductions:
                    ingredient_deductions[ingredient_id] += total_needed
                else:
                    ingredient_deductions[ingredient_id] = total_needed
            
            # Busca ingredientes extras do item
            cur.execute("""
                SELECT INGREDIENT_ID, QUANTITY 
                FROM ORDER_ITEM_EXTRAS 
                WHERE ORDER_ITEM_ID = (
                    SELECT ID FROM ORDER_ITEMS 
                    WHERE ORDER_ID = ? AND PRODUCT_ID = ?
                )
            """, (order_id, product_id))
            extras = cur.fetchall()
            
            # Adiciona ingredientes extras
            for ingredient_id, extra_quantity in extras:
                total_extra = extra_quantity * quantity
                if ingredient_id in ingredient_deductions:
                    ingredient_deductions[ingredient_id] += total_extra
                else:
                    ingredient_deductions[ingredient_id] = total_extra
        
        # Executa as deduções de estoque
        updated_ingredients = []
        for ingredient_id, deduction_amount in ingredient_deductions.items():
            # Busca estoque atual e limite mínimo
            cur.execute("""
                SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS, NAME
                FROM INGREDIENTS 
                WHERE ID = ?
            """, (ingredient_id,))
            result = cur.fetchone()
            
            if not result:
                continue
                
            current_stock, min_threshold, current_status, ingredient_name = result
            
            # Verifica se há estoque suficiente
            if current_stock < deduction_amount:
                return (False, "INSUFFICIENT_STOCK", 
                       f"Estoque insuficiente para {ingredient_name}. Disponível: {current_stock}, Necessário: {deduction_amount}")
            
            # Calcula novo estoque
            new_stock = current_stock - deduction_amount
            
            # Determina novo status baseado no estoque
            new_status = current_status
            if new_stock <= min_threshold and current_status == 'ok':
                new_status = 'low'
            elif new_stock <= 0:
                new_status = 'out_of_stock'
            
            # Atualiza o estoque
            cur.execute("""
                UPDATE INGREDIENTS 
                SET CURRENT_STOCK = ?, STOCK_STATUS = ?
                WHERE ID = ?
            """, (new_stock, new_status, ingredient_id))
            
            updated_ingredients.append({
                'ingredient_id': ingredient_id,
                'ingredient_name': ingredient_name,
                'old_stock': current_stock,
                'new_stock': new_stock,
                'deducted': deduction_amount,
                'new_status': new_status
            })
        
        conn.commit()
        
        # Log das alterações
        print(f"Estoque deduzido para pedido {order_id}:")
        for item in updated_ingredients:
            print(f"  {item['ingredient_name']}: {item['old_stock']} -> {item['new_stock']} (deduzido: {item['deducted']}, status: {item['new_status']})")
        
        return (True, None, f"Estoque deduzido para {len(updated_ingredients)} ingredientes")
        
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao deduzir estoque: {e}")
        return (False, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def get_stock_alerts():
    """
    Retorna lista de ingredientes com estoque baixo.
    Retorna (ingredientes, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT ID, NAME, CURRENT_STOCK, MIN_STOCK_THRESHOLD, UNIT, STOCK_STATUS
            FROM INGREDIENTS 
            WHERE STOCK_STATUS = 'low' AND IS_ACTIVE = TRUE
            ORDER BY CURRENT_STOCK ASC
        """)
        
        alerts = []
        for row in cur.fetchall():
            alerts.append({
                'id': row[0],
                'name': row[1],
                'current_stock': row[2],
                'min_threshold': row[3],
                'unit': row[4],
                'status': row[5]
            })
        
        return (alerts, None, None)
        
    except fdb.Error as e:
        print(f"Erro ao buscar alertas de estoque: {e}")
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def confirm_out_of_stock(ingredient_id):
    """
    Confirma que um ingrediente está fora de estoque e desativa produtos dependentes.
    Retorna (sucesso, produtos_desativados, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se o ingrediente existe
        cur.execute("SELECT NAME FROM INGREDIENTS WHERE ID = ? AND IS_ACTIVE = TRUE", (ingredient_id,))
        result = cur.fetchone()
        if not result:
            return (False, [], "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")
        
        ingredient_name = result[0]
        
        # Atualiza o ingrediente para fora de estoque
        cur.execute("""
            UPDATE INGREDIENTS 
            SET CURRENT_STOCK = 0, STOCK_STATUS = 'out_of_stock'
            WHERE ID = ?
        """, (ingredient_id,))
        
        # Busca produtos que usam este ingrediente
        cur.execute("""
            SELECT DISTINCT P.ID, P.NAME
            FROM PRODUCTS P
            JOIN PRODUCT_INGREDIENTS PI ON P.ID = PI.PRODUCT_ID
            WHERE PI.INGREDIENT_ID = ? AND P.IS_ACTIVE = TRUE
        """, (ingredient_id,))
        
        affected_products = cur.fetchall()
        deactivated_products = []
        
        # Desativa produtos dependentes
        for product_id, product_name in affected_products:
            cur.execute("UPDATE PRODUCTS SET IS_ACTIVE = FALSE WHERE ID = ?", (product_id,))
            deactivated_products.append({
                'id': product_id,
                'name': product_name
            })
        
        conn.commit()
        
        message = f"Ingrediente '{ingredient_name}' confirmado como fora de estoque"
        if deactivated_products:
            message += f". {len(deactivated_products)} produtos foram desativados do cardápio."
        
        return (True, deactivated_products, None, message)
        
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao confirmar estoque zerado: {e}")
        return (False, [], "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def adjust_stock(ingredient_id, adjustment_amount):
    """
    Ajusta manualmente o estoque de um ingrediente.
    Retorna (sucesso, produtos_reativados, error_code, mensagem)
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca dados atuais do ingrediente
        cur.execute("""
            SELECT CURRENT_STOCK, MIN_STOCK_THRESHOLD, STOCK_STATUS, NAME
            FROM INGREDIENTS 
            WHERE ID = ? AND IS_ACTIVE = TRUE
        """, (ingredient_id,))
        result = cur.fetchone()
        
        if not result:
            return (False, [], "INGREDIENT_NOT_FOUND", "Ingrediente não encontrado")
        
        current_stock, min_threshold, current_status, ingredient_name = result
        
        # Calcula novo estoque
        new_stock = max(0, current_stock + adjustment_amount)
        
        # Determina novo status
        new_status = current_status
        if new_stock > min_threshold and current_status in ['low', 'out_of_stock']:
            new_status = 'ok'
        elif new_stock <= min_threshold and new_stock > 0 and current_status == 'out_of_stock':
            new_status = 'low'
        elif new_stock <= 0:
            new_status = 'out_of_stock'
        
        # Atualiza o estoque
        cur.execute("""
            UPDATE INGREDIENTS 
            SET CURRENT_STOCK = ?, STOCK_STATUS = ?
            WHERE ID = ?
        """, (new_stock, new_status, ingredient_id,))
        
        # Se o ingrediente voltou a ter estoque, tenta reativar produtos
        reactivated_products = []
        if current_status == 'out_of_stock' and new_stock > 0:
            reactivated_products = reactivate_products_for_ingredient(ingredient_id, cur)
        
        conn.commit()
        
        message = f"Estoque de '{ingredient_name}' ajustado: {current_stock} -> {new_stock} (status: {new_status})"
        if reactivated_products:
            message += f". {len(reactivated_products)} produtos foram reativados."
        
        return (True, reactivated_products, None, message)
        
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao ajustar estoque: {e}")
        return (False, [], "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()


def reactivate_products_for_ingredient(ingredient_id, cursor=None):
    """
    Reativa produtos que usam um ingrediente, se todos os ingredientes necessários estiverem disponíveis.
    Retorna lista de produtos reativados.
    """
    conn = None
    try:
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
        
        # Busca produtos inativos que usam este ingrediente
        cursor.execute("""
            SELECT DISTINCT P.ID, P.NAME
            FROM PRODUCTS P
            JOIN PRODUCT_INGREDIENTS PI ON P.ID = PI.PRODUCT_ID
            WHERE PI.INGREDIENT_ID = ? AND P.IS_ACTIVE = FALSE
        """, (ingredient_id,))
        
        products_to_check = cursor.fetchall()
        reactivated_products = []
        
        for product_id, product_name in products_to_check:
            # Verifica se todos os ingredientes do produto estão disponíveis
            cursor.execute("""
                SELECT PI.INGREDIENT_ID, PI.QUANTITY, I.CURRENT_STOCK, I.STOCK_STATUS
                FROM PRODUCT_INGREDIENTS PI
                JOIN INGREDIENTS I ON PI.INGREDIENT_ID = I.ID
                WHERE PI.PRODUCT_ID = ? AND I.IS_ACTIVE = TRUE
            """, (product_id,))
            
            ingredients = cursor.fetchall()
            can_reactivate = True
            
            for ing_id, required_qty, current_stock, status in ingredients:
                if status == 'out_of_stock' or current_stock < required_qty:
                    can_reactivate = False
                    break
            
            if can_reactivate:
                cursor.execute("UPDATE PRODUCTS SET IS_ACTIVE = TRUE WHERE ID = ?", (product_id,))
                reactivated_products.append({
                    'id': product_id,
                    'name': product_name
                })
        
        if conn:
            conn.commit()
        
        return reactivated_products
        
    except fdb.Error as e:
        if conn: conn.rollback()
        print(f"Erro ao reativar produtos: {e}")
        return []
    finally:
        if conn: conn.close()
