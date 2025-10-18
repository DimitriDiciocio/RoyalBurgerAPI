

import fdb
import random
import string

from . import loyalty_service, notification_service, user_service, email_service, store_service, cart_service, stock_service
from ..database import get_db_connection
from ..utils import validators


def _generate_confirmation_code(length=8):
    """Gera um código de confirmação alfanumérico aleatório."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def create_order(user_id, address_id, items, payment_method, change_for_amount=None, notes="", cpf_on_invoice=None,
                 points_to_redeem=0):
    """
    Cria um novo pedido validando TUDO: horário da loja, disponibilidade de ingredientes, CPF, etc.
    Retorna uma tupla: (order_data, error_code, error_message)
    """
    
    is_open, message = store_service.is_store_open()
    if not is_open:
        return (None, "STORE_CLOSED", message)

    
    if cpf_on_invoice and not validators.is_valid_cpf(cpf_on_invoice):
        return (None, "INVALID_CPF", f"O CPF informado '{cpf_on_invoice}' é inválido.")

    
    if not items or len(items) == 0:
        return (None, "EMPTY_ORDER", "O pedido deve conter pelo menos um item.")

    if not payment_method:
        return (None, "MISSING_PAYMENT_METHOD", "Método de pagamento é obrigatório.")

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        

        

        
        required_ingredients = set()
        product_ids = {item['product_id'] for item in items}
        extra_ingredient_ids = set()

        for item in items:
            if 'extras' in item and item['extras']:
                for extra in item['extras']:
                    extra_ingredient_ids.add(extra['ingredient_id'])

        if product_ids:
            placeholders = ', '.join(['?' for _ in product_ids])
            sql_base_ingredients = f"SELECT INGREDIENT_ID FROM PRODUCT_INGREDIENTS WHERE PRODUCT_ID IN ({placeholders});"
            cur.execute(sql_base_ingredients, tuple(product_ids))
            for row in cur.fetchall():
                required_ingredients.add(row[0])

        required_ingredients.update(extra_ingredient_ids)

        if required_ingredients:
            placeholders = ', '.join(['?' for _ in required_ingredients])
            sql_check_availability = f"SELECT NAME FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = FALSE;"
            cur.execute(sql_check_availability, tuple(required_ingredients))
            unavailable_ingredient = cur.fetchone()
            if unavailable_ingredient:
                return (None, "INGREDIENT_UNAVAILABLE", f"Desculpe, o ingrediente '{unavailable_ingredient[0]}' está esgotado.")

        
        
        sql_get_id = "SELECT GEN_ID(GEN_ORDERS_ID, 1) FROM RDB$DATABASE;"
        cur.execute(sql_get_id)
        new_order_id = cur.fetchone()[0]

        discount_amount = loyalty_service.redeem_points_for_discount(user_id, points_to_redeem, new_order_id,
                                                                     cur) if points_to_redeem > 0 else 0.0

        product_prices = {}
        order_total = 0
        if product_ids:
            placeholders = ', '.join(['?' for _ in product_ids])
            sql_prices = f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});"
            cur.execute(sql_prices, tuple(product_ids))
            product_prices = {row[0]: row[1] for row in cur.fetchall()}
            for item in items:
                order_total += product_prices.get(item['product_id'], 0) * item.get('quantity', 1)

        extra_prices = {}
        if extra_ingredient_ids:
            placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
            sql_extra_prices = f"SELECT ID, PRICE FROM INGREDIENTS WHERE ID IN ({placeholders});"
            cur.execute(sql_extra_prices, tuple(extra_ingredient_ids))
            extra_prices = {row[0]: row[1] for row in cur.fetchall()}
            for item in items:
                if 'extras' in item and item['extras']:
                    for extra in item['extras']:
                        order_total += extra_prices.get(extra['ingredient_id'], 0) * extra.get('quantity', 1)

        if discount_amount > order_total:
            return (None, "INVALID_DISCOUNT", "O valor do desconto não pode ser maior que o total do pedido.")

        confirmation_code = _generate_confirmation_code()
        sql_order = """
            INSERT INTO ORDERS (ID, USER_ID, ADDRESS_ID, STATUS, CONFIRMATION_CODE, NOTES, PAYMENT_METHOD, CHANGE_FOR_AMOUNT, CPF_ON_INVOICE, DISCOUNT_AMOUNT)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?);
        """
        cur.execute(sql_order, (
        new_order_id, user_id, address_id, confirmation_code, notes, payment_method, change_for_amount, cpf_on_invoice,
        discount_amount))

        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity')
            unit_price = product_prices[product_id]

            sql_item = "INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE) VALUES (?, ?, ?, ?) RETURNING ID;"
            cur.execute(sql_item, (new_order_id, product_id, quantity, unit_price))
            new_order_item_id = cur.fetchone()[0]

            if 'extras' in item and item['extras']:
                for extra in item['extras']:
                    extra_id = extra['ingredient_id']
                    extra_qty = extra.get('quantity', 1)
                    extra_price = extra_prices[extra_id]
                    sql_extra = "INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, UNIT_PRICE) VALUES (?, ?, ?, ?);"
                    cur.execute(sql_extra, (new_order_item_id, extra_id, extra_qty, extra_price))

        conn.commit()
        

        new_order_data = {"order_id": new_order_id, "confirmation_code": confirmation_code, "status": "pending"}
        

        return (new_order_data, None, None)

    except fdb.Error as e:
        print(f"Erro ao criar pedido: {e}")
        if conn: conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    finally:
        if conn: conn.close()

def get_orders_by_user_id(user_id):
    """Busca o histórico de pedidos de um usuário específico."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT o.ID, o.STATUS, o.CONFIRMATION_CODE, o.CREATED_AT, a.STREET, a."NUMBER"
            FROM ORDERS o
            JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            WHERE o.USER_ID = ?
            ORDER BY o.CREATED_AT DESC;
        """
        cur.execute(sql, (user_id,))
        orders = []
        for row in cur.fetchall():
            orders.append({
                "order_id": row[0], "status": row[1], "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S'),
                "address": f"{row[4]}, {row[5]}"
            })
        return orders
    except fdb.Error as e:
        print(f"Erro ao buscar pedidos do usuário: {e}")
        return []
    finally:
        if conn: conn.close()

def get_all_orders():
    """Busca todos os pedidos para a visão do administrador."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT o.ID, o.STATUS, o.CONFIRMATION_CODE, o.CREATED_AT, u.FULL_NAME
            FROM ORDERS o
            JOIN USERS u ON o.USER_ID = u.ID
            ORDER BY o.CREATED_AT DESC;
        """
        cur.execute(sql)
        orders = []
        for row in cur.fetchall():
            orders.append({
                "order_id": row[0], "status": row[1], "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S'),
                "customer_name": row[4]
            })
        return orders
    except fdb.Error as e:
        print(f"Erro ao buscar todos os pedidos: {e}")
        return []
    finally:
        if conn: conn.close()


def update_order_status(order_id, new_status):
    """Atualiza o status de um pedido e adiciona pontos de fidelidade se concluído."""
    allowed_statuses = ['pending', 'preparing', 'on_the_way', 'completed', 'cancelled']
    if new_status not in allowed_statuses:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        
        sql_update = "UPDATE ORDERS SET STATUS = ? WHERE ID = ?;"
        cur.execute(sql_update, (new_status, order_id))

        # Deduz estoque quando o pedido é confirmado (status 'preparing')
        if new_status == 'preparing':
            success, error_code, message = stock_service.deduct_stock_for_order(order_id)
            if not success:
                # Se falhou a dedução, reverte o status
                cur.execute("UPDATE ORDERS SET STATUS = 'pending' WHERE ID = ?;", (order_id,))
                conn.commit()
                print(f"Erro ao deduzir estoque para pedido {order_id}: {message}")
                return False
            print(f"Estoque deduzido para pedido {order_id}: {message}")

        if new_status == 'completed':
            sql_get_user = "SELECT USER_ID FROM ORDERS WHERE ID = ?;"
            cur.execute(sql_get_user, (order_id,))
            result = cur.fetchone()
            if result:
                user_id = result[0]
                loyalty_service.add_points_for_order(user_id, order_id, cur)

        conn.commit()
        

        
        
        sql_get_user = "SELECT USER_ID FROM ORDERS WHERE ID = ?;"
        cur.execute(sql_get_user, (order_id,))
        result = cur.fetchone()
        if result:
            user_id = result[0]
            notification_message = f"O status do seu pedido #{order_id} foi atualizado para {new_status}"
            notification_link = f"/my-orders/{order_id}"
            notification_service.create_notification(user_id, notification_message, notification_link)
            customer = user_service.get_user_by_id(user_id)
            if customer:
                email_service.send_email(
                    to=customer['email'],
                    subject=f"Atualização sobre seu pedido #{order_id}",
                    template='order_status_update',
                    user=customer,
                    order={"order_id": order_id},
                    new_status=new_status
                )

        return cur.rowcount > 0
    except fdb.Error as e:
        print(f"Erro ao atualizar status do pedido: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_order_details(order_id, user_id, user_role):
    """
    Busca os detalhes completos de um pedido, incluindo seus itens.
    Realiza uma verificação de posse para garantir a segurança.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        
        sql_order = """
            SELECT ID, USER_ID, ADDRESS_ID, STATUS, CONFIRMATION_CODE, NOTES,
                   PAYMENT_METHOD, CHANGE_FOR_AMOUNT, CPF_ON_INVOICE,
                   DISCOUNT_AMOUNT, CREATED_AT
            FROM ORDERS WHERE ID = ?;
        """
        cur.execute(sql_order, (order_id,))
        order_row = cur.fetchone()

        if not order_row:
            return None 

        
        order_details = {
            "id": order_row[0], "user_id": order_row[1], "address_id": order_row[2],
            "status": order_row[3], "confirmation_code": order_row[4], "notes": order_row[5],
            "payment_method": order_row[6], "change_for_amount": order_row[7],
            "cpf_on_invoice": order_row[8], "discount_amount": order_row[9],
            "created_at": order_row[10].strftime('%Y-%m-%d %H:%M:%S')
        }

        
        
        if user_role == 'customer' and order_details['user_id'] != user_id:
            return None 

        
        sql_items = """
            SELECT oi.QUANTITY, oi.UNIT_PRICE, p.NAME, p.DESCRIPTION
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE oi.ORDER_ID = ?;
        """
        cur.execute(sql_items, (order_id,))

        order_items = []
        for item_row in cur.fetchall():
            order_items.append({
                "quantity": item_row[0],
                "unit_price": item_row[1],
                "product_name": item_row[2],
                "product_description": item_row[3]
            })

        
        order_details['items'] = order_items
        return order_details

    except fdb.Error as e:
        print(f"Erro ao buscar detalhes do pedido: {e}")
        return None
    finally:
        if conn:
            conn.close()

def cancel_order_by_customer(order_id, user_id):
    """
    Permite que um cliente cancele seu próprio pedido, sob condições específicas.
    Retorna uma tupla: (sucesso, mensagem).
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        
        sql_find = "SELECT USER_ID, STATUS FROM ORDERS WHERE ID = ?;"
        cur.execute(sql_find, (order_id,))
        order_record = cur.fetchone()

        if not order_record:
            return (False, "Pedido não encontrado.")

        owner_id, status = order_record

        
        if owner_id != user_id:
            return (False, "Você não tem permissão para cancelar este pedido.")

        
        if status != 'pending':
            return (False, f"Não é possível cancelar um pedido que já está com o status '{status}'.")

        
        sql_update = "UPDATE ORDERS SET STATUS = 'cancelled' WHERE ID = ?;"
        cur.execute(sql_update, (order_id,))
        conn.commit()

        
        try:
            message = f"Seu pedido #{order_id} foi cancelado com sucesso!"
            link = f"/my-orders/{order_id}"
            notification_service.create_notification(user_id, message, link)

            customer = user_service.get_user_by_id(user_id)
            if customer:
                 email_service.send_email(
                    to=customer['email'],
                    subject=f"Seu pedido #{order_id} foi cancelado",
                    template='order_status_update', 
                    user=customer,
                    order={"order_id": order_id},
                    new_status='cancelled'
                )
        except Exception as e:
            print(f"AVISO: Falha ao enviar notificação de cancelamento para o pedido {order_id}. Erro: {e}")

        return (True, "Pedido cancelado com sucesso.")

    except fdb.Error as e:
        print(f"Erro ao cancelar pedido: {e}")
        if conn: conn.rollback()
        return (False, "Ocorreu um erro interno ao tentar cancelar o pedido.")
    finally:
        if conn: conn.close()


def create_order_from_cart(user_id, address_id, payment_method, change_for_amount=None, notes="", cpf_on_invoice=None, points_to_redeem=0):
    """
    Fluxo 4: Finalização (Converter Carrinho em Pedido)
    Cria um pedido a partir do carrinho do usuário
    """
    conn = None
    try:
        # Inicia transação
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se a loja está aberta
        is_open, message = store_service.is_store_open()
        if not is_open:
            return (None, "STORE_CLOSED", message)
        
        # Busca o carrinho do usuário
        cart_data = cart_service.get_cart_for_order(user_id)
        if not cart_data:
            return (None, "EMPTY_CART", "Carrinho está vazio")
        
        # Validações básicas
        if cpf_on_invoice and not validators.is_valid_cpf(cpf_on_invoice):
            return (None, "INVALID_CPF", f"O CPF informado '{cpf_on_invoice}' é inválido.")
        
        # Verifica se o endereço pertence ao usuário
        cur.execute("SELECT ID FROM ADDRESSES WHERE ID = ? AND USER_ID = ? AND IS_ACTIVE = TRUE;", (address_id, user_id))
        if not cur.fetchone():
            return (None, "INVALID_ADDRESS", "Endereço não encontrado ou não pertence ao usuário.")
        
        # Gera código de confirmação
        confirmation_code = _generate_confirmation_code()
        
        # Calcula total do carrinho
        total_amount = cart_data["total_amount"]
        
        # Aplica desconto de pontos se fornecido
        if points_to_redeem > 0:
            points_value = loyalty_service.calculate_points_value(points_to_redeem)
            total_amount = max(0, total_amount - points_value)
        
        # Cria o pedido
        sql_order = """
            INSERT INTO ORDERS (USER_ID, ADDRESS_ID, STATUS, TOTAL_AMOUNT, PAYMENT_METHOD, 
                              NOTES, CONFIRMATION_CODE, CHANGE_FOR_AMOUNT, CPF_ON_INVOICE, POINTS_TO_REDEEM)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?) RETURNING ID;
        """
        cur.execute(sql_order, (user_id, address_id, total_amount, payment_method, notes, 
                               confirmation_code, change_for_amount, cpf_on_invoice, points_to_redeem))
        order_id = cur.fetchone()[0]
        
        # Copia itens do carrinho para o pedido
        for item in cart_data["items"]:
            # Insere item principal
            sql_item = """
                INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY)
                VALUES (?, ?, ?) RETURNING ID;
            """
            cur.execute(sql_item, (order_id, item["product_id"], item["quantity"]))
            order_item_id = cur.fetchone()[0]
            
            # Insere extras do item
            for extra in item["extras"]:
                sql_extra = """
                    INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY)
                    VALUES (?, ?, ?);
                """
                cur.execute(sql_extra, (order_item_id, extra["ingredient_id"], extra["quantity"]))
        
        # Limpa o carrinho do usuário
        cart_id = cart_data["cart_id"]
        cur.execute("DELETE FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
        
        # Aplica pontos de fidelidade se houver
        if total_amount > 0:
            loyalty_service.add_loyalty_points(user_id, total_amount)
        
        # Consome pontos se houver
        if points_to_redeem > 0:
            loyalty_service.consume_loyalty_points(user_id, points_to_redeem)
        
        # Confirma transação
        conn.commit()
        
        # Busca dados completos do pedido criado
        order_data = get_order_details(order_id, user_id, ['customer'])
        
        # Envia notificação
        try:
            notification_service.send_order_confirmation(user_id, order_data)
        except Exception as e:
            print(f"Erro ao enviar notificação: {e}")
        
        return (order_data, None, "Pedido criado com sucesso a partir do carrinho")
        
    except fdb.Error as e:
        print(f"Erro ao criar pedido do carrinho: {e}")
        if conn: conn.rollback()
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        print(f"Erro inesperado ao criar pedido do carrinho: {e}")
        if conn: conn.rollback()
        return (None, "UNKNOWN_ERROR", "Erro inesperado")
    finally:
        if conn: conn.close()


def get_orders_with_filters(filters=None):
    """
    Busca pedidos com filtros para relatórios
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Query base
        base_sql = """
            SELECT o.ID, o.STATUS, o.CONFIRMATION_CODE, o.CREATED_AT, o.TOTAL_AMOUNT,
                   u.FULL_NAME as customer_name, a.STREET, a."NUMBER"
            FROM ORDERS o
            JOIN USERS u ON o.USER_ID = u.ID
            LEFT JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            WHERE 1=1
        """
        
        # Filtros
        conditions = []
        params = []
        
        if filters:
            if filters.get('start_date'):
                conditions.append("DATE(o.CREATED_AT) >= ?")
                params.append(filters['start_date'])
            
            if filters.get('end_date'):
                conditions.append("DATE(o.CREATED_AT) <= ?")
                params.append(filters['end_date'])
            
            if filters.get('status'):
                conditions.append("o.STATUS = ?")
                params.append(filters['status'])
        
        if conditions:
            base_sql += " AND " + " AND ".join(conditions)
        
        # Ordenação
        sort_by = filters.get('sort_by', 'date_desc') if filters else 'date_desc'
        if sort_by == 'date_desc':
            base_sql += " ORDER BY o.CREATED_AT DESC"
        elif sort_by == 'date_asc':
            base_sql += " ORDER BY o.CREATED_AT ASC"
        else:
            base_sql += " ORDER BY o.CREATED_AT DESC"
        
        cur.execute(base_sql, params)
        orders = []
        
        for row in cur.fetchall():
            orders.append({
                "id": row[0],
                "status": row[1],
                "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None,
                "total_amount": float(row[4]) if row[4] else 0.0,
                "customer_name": row[5],
                "address": f"{row[6]}, {row[7]}" if row[6] and row[7] else "N/A",
                "order_type": "Delivery"  # Por enquanto sempre delivery
            })
        
        return orders
        
    except fdb.Error as e:
        print(f"Erro ao buscar pedidos com filtros: {e}")
        return []
    finally:
        if conn: conn.close()