

import fdb
import random
import string

from . import loyalty_service, notification_service, user_service, email_service, store_service, cart_service, stock_service
from .printing_service import generate_kitchen_ticket_pdf, print_pdf_bytes, print_kitchen_ticket, format_order_for_kitchen_json
from .. import socketio
from ..config import Config
from ..database import get_db_connection
from ..utils import validators
from datetime import datetime

def _validate_order_data(user_id, address_id, items, payment_method):
    """Valida dados básicos do pedido"""
    if not user_id or not isinstance(user_id, int):
        raise ValueError("user_id deve ser um inteiro válido")
    
    if not address_id or not isinstance(address_id, int):
        raise ValueError("address_id deve ser um inteiro válido")
    
    if not items or not isinstance(items, list) or len(items) == 0:
        raise ValueError("O pedido deve conter pelo menos um item")
    
    if not payment_method or not isinstance(payment_method, str):
        raise ValueError("Método de pagamento é obrigatório")

def _validate_cpf(cpf_on_invoice):
    """Valida CPF se fornecido"""
    if cpf_on_invoice and not validators.is_valid_cpf(cpf_on_invoice):
        raise ValueError(f"O CPF informado '{cpf_on_invoice}' é inválido")

def _validate_points_redemption(points_to_redeem, total_amount):
    """Valida resgate de pontos"""
    if points_to_redeem and points_to_redeem > 0:
        expected_discount = points_to_redeem / 100.0
        if expected_discount > total_amount:
            raise ValueError("O valor do desconto não pode ser maior que o total do pedido")

def _validate_ingredients_and_extras(items, cur):
    """Valida ingredientes e extras do pedido"""
    required_ingredients = set()
    product_ids = {item['product_id'] for item in items}
    extra_ingredient_ids = set()

    for item in items:
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_ingredient_ids.add(extra['ingredient_id'])

    # Busca regras de ingredientes por produto
    product_rules = {}
    if product_ids:
        placeholders = ', '.join(['?' for _ in product_ids])
        sql_rules = f"""
            SELECT PRODUCT_ID, INGREDIENT_ID, PORTIONS, MIN_QUANTITY, MAX_QUANTITY
            FROM PRODUCT_INGREDIENTS
            WHERE PRODUCT_ID IN ({placeholders})
        """
        cur.execute(sql_rules, tuple(product_ids))
        for row in cur.fetchall():
            pid, ing_id, portions, min_q, max_q = row
            if pid not in product_rules:
                product_rules[pid] = {}
            product_rules[pid][ing_id] = {
                'portions': float(portions or 0),
                'min_quantity': int(min_q or 0),
                'max_quantity': int(max_q or 0)
            }
            required_ingredients.add(ing_id)

    required_ingredients.update(extra_ingredient_ids)

    # Valida extras conforme regras
    for item in items:
        pid = item['product_id']
        extras = item.get('extras') or []
        if not extras:
            continue
        rules_for_product = product_rules.get(pid, {})
        for extra in extras:
            ing_id = extra['ingredient_id']
            qty = int(extra.get('quantity', 1))
            rule = rules_for_product.get(ing_id)
            if not rule:
                raise ValueError(f"Ingrediente {ing_id} não é permitido para o produto {pid}")
            if float(rule['portions']) != 0.0:
                raise ValueError(f"Ingrediente {ing_id} faz parte da receita base e não pode ser extra")
            min_q = int(rule['min_quantity'] or 0)
            max_q = int(rule['max_quantity'] or 0)
            if qty < min_q or (max_q > 0 and qty > max_q):
                raise ValueError(f"Quantidade do extra {ing_id} fora do intervalo permitido [{min_q}, {max_q or '∞'}]")

    # Verifica disponibilidade de ingredientes
    if required_ingredients:
        placeholders = ', '.join(['?' for _ in required_ingredients])
        sql_check_availability = f"SELECT NAME FROM INGREDIENTS WHERE ID IN ({placeholders}) AND IS_AVAILABLE = FALSE;"
        cur.execute(sql_check_availability, tuple(required_ingredients))
        unavailable_ingredient = cur.fetchone()
        if unavailable_ingredient:
            raise ValueError(f"Desculpe, o ingrediente '{unavailable_ingredient[0]}' está esgotado.")

def _calculate_order_total(items, cur):
    """Calcula total do pedido"""
    product_prices = {}
    order_total = 0
    product_ids = {item['product_id'] for item in items}
    
    if product_ids:
        placeholders = ', '.join(['?' for _ in product_ids])
        cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(product_ids))
        product_prices = {row[0]: row[1] for row in cur.fetchall()}
        
        for item in items:
            order_total += product_prices.get(item['product_id'], 0) * item.get('quantity', 1)

    extra_prices = {}
    extra_ingredient_ids = set()
    for item in items:
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_ingredient_ids.add(extra['ingredient_id'])
    
    if extra_ingredient_ids:
        placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
        cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ingredient_ids))
        extra_prices = {row[0]: row[1] for row in cur.fetchall()}
        
        for item in items:
            if 'extras' in item and item['extras']:
                for extra in item['extras']:
                    order_total += extra_prices.get(extra['ingredient_id'], 0) * extra.get('quantity', 1)

    return order_total

def _add_order_items(order_id, items, cur):
    """Adiciona itens ao pedido"""
    product_prices = {}
    product_ids = {item['product_id'] for item in items}
    
    if product_ids:
        placeholders = ', '.join(['?' for _ in product_ids])
        cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(product_ids))
        product_prices = {row[0]: row[1] for row in cur.fetchall()}

    extra_prices = {}
    extra_ingredient_ids = set()
    for item in items:
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_ingredient_ids.add(extra['ingredient_id'])
    
    if extra_ingredient_ids:
        placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
        cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ingredient_ids))
        extra_prices = {row[0]: row[1] for row in cur.fetchall()}

    for item in items:
        product_id = item.get('product_id')
        quantity = item.get('quantity')
        unit_price = product_prices[product_id]

        sql_item = "INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE) VALUES (?, ?, ?, ?) RETURNING ID;"
        cur.execute(sql_item, (order_id, product_id, quantity, unit_price))
        new_order_item_id = cur.fetchone()[0]

        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_id = extra['ingredient_id']
                extra_qty = extra.get('quantity', 1)
                extra_price = extra_prices[extra_id]
                sql_extra = "INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, UNIT_PRICE) VALUES (?, ?, ?, ?);"
                cur.execute(sql_extra, (new_order_item_id, extra_id, extra_qty, extra_price))

def _notify_kitchen(order_id):
    """Notifica a cozinha sobre novo pedido"""
    try:
        kitchen_ticket_json = format_order_for_kitchen_json(order_id)
        if kitchen_ticket_json:
            socketio.emit('new_kitchen_order', kitchen_ticket_json)
    except Exception as e:
        print(f"[WARN] Falha ao emitir evento de cozinha do pedido {order_id}: {e}")


def _generate_confirmation_code(length=8):
    """Gera um código de confirmação alfanumérico aleatório."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def create_order(user_id, address_id, items, payment_method, change_for_amount=None, notes="", cpf_on_invoice=None, points_to_redeem=0):
    """Cria um novo pedido validando TUDO"""
    
    try:
        # Validações básicas
        _validate_order_data(user_id, address_id, items, payment_method)
        _validate_cpf(cpf_on_invoice)
        
        # Verifica se a loja está aberta
        is_open, message = store_service.is_store_open()
        if not is_open:
            return (None, "STORE_CLOSED", message)

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Validações de ingredientes e extras
            _validate_ingredients_and_extras(items, cur)
            
            # Calcula total dos itens
            order_total = _calculate_order_total(items, cur)
            
            # Valida resgate de pontos
            _validate_points_redemption(points_to_redeem, order_total)

            # Cria o pedido
            confirmation_code = _generate_confirmation_code()
            sql_order = """
                INSERT INTO ORDERS (USER_ID, ADDRESS_ID, STATUS, TOTAL_AMOUNT, PAYMENT_METHOD, NOTES, CONFIRMATION_CODE)
                VALUES (?, ?, 'pending', ?, ?, ?, ?) RETURNING ID;
            """
            cur.execute(sql_order, (user_id, address_id, order_total, payment_method, notes, confirmation_code))
            new_order_id = cur.fetchone()[0]

            # Debita pontos se houver
            if points_to_redeem and points_to_redeem > 0:
                discount_amount = loyalty_service.redeem_points_for_discount(user_id, points_to_redeem, new_order_id, cur)
                new_total = max(0, float(order_total) - float(discount_amount))
                cur.execute("UPDATE ORDERS SET TOTAL_AMOUNT = ? WHERE ID = ?;", (new_total, new_order_id))

            # Adiciona itens ao pedido
            _add_order_items(new_order_id, items, cur)
            
            conn.commit()
            
            # Notificação para cozinha
            _notify_kitchen(new_order_id)
            
            return ({"order_id": new_order_id, "confirmation_code": confirmation_code, "status": "pending"}, None, None)

        except fdb.Error as e:
            print(f"Erro ao criar pedido: {e}")
            if conn: conn.rollback()
            return (None, "DATABASE_ERROR", "Erro interno do servidor")
        finally:
            if conn: conn.close()
            
    except ValueError as e:
        return (None, "VALIDATION_ERROR", str(e))
    except Exception as e:
        print(f"Erro inesperado ao criar pedido: {e}")
        return (None, "UNKNOWN_ERROR", "Erro inesperado")

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
                # Busca o total do pedido para calcular pontos
                cur.execute("SELECT TOTAL_AMOUNT FROM ORDERS WHERE ID = ?;", (order_id,))
                order_total = cur.fetchone()
                if order_total:
                    loyalty_service.earn_points_for_order(user_id, order_id, order_total[0], cur)

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
                   PAYMENT_METHOD, TOTAL_AMOUNT, CREATED_AT
            FROM ORDERS WHERE ID = ?;
        """
        cur.execute(sql_order, (order_id,))
        order_row = cur.fetchone()

        if not order_row:
            return None 

        
        order_details = {
            "id": order_row[0], "user_id": order_row[1], "address_id": order_row[2],
            "status": order_row[3], "confirmation_code": order_row[4], "notes": order_row[5],
            "payment_method": order_row[6], "total_amount": float(order_row[7]) if order_row[7] is not None else 0.0,
            "created_at": order_row[8].strftime('%Y-%m-%d %H:%M:%S') if order_row[8] else None
        }

        
        
        if user_role == 'customer' and order_details['user_id'] != user_id:
            return None 

        
        sql_items = """
            SELECT oi.ID, oi.QUANTITY, oi.UNIT_PRICE, p.NAME, p.DESCRIPTION
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE oi.ORDER_ID = ?;
        """
        cur.execute(sql_items, (order_id,))

        order_items = []
        for item_row in cur.fetchall():
            order_item_id = item_row[0]
            item_dict = {
                "quantity": item_row[1],
                "unit_price": item_row[2],
                "product_name": item_row[3],
                "product_description": item_row[4],
                "extras": []
            }
            # Busca extras do item
            cur2 = conn.cursor()
            cur2.execute(
                """
                SELECT e.INGREDIENT_ID, i.NAME, e.QUANTITY
                FROM ORDER_ITEM_EXTRAS e
                JOIN INGREDIENTS i ON i.ID = e.INGREDIENT_ID
                WHERE e.ORDER_ITEM_ID = ?
                """,
                (order_item_id,)
            )
            for ex in cur2.fetchall():
                item_dict["extras"].append({
                    "ingredient_id": ex[0],
                    "name": ex[1],
                    "quantity": ex[2]
                })
            order_items.append(item_dict)

        
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
        
        # Valida desconto de pontos (sem debitar ainda)
        if points_to_redeem and points_to_redeem > 0:
            # 100 pontos = R$ 1,00 de desconto (conforme documentação)
            expected_discount = points_to_redeem / 100.0
            if expected_discount > total_amount:
                return (None, "INVALID_DISCOUNT", "O valor do desconto não pode ser maior que o total do pedido.")
        
        # Cria o pedido (colunas compatíveis com o schema)
        sql_order = """
            INSERT INTO ORDERS (USER_ID, ADDRESS_ID, STATUS, TOTAL_AMOUNT, PAYMENT_METHOD, 
                                NOTES, CONFIRMATION_CODE)
            VALUES (?, ?, 'pending', ?, ?, ?, ?) RETURNING ID;
        """
        cur.execute(sql_order, (user_id, address_id, total_amount, payment_method, notes, confirmation_code))
        order_id = cur.fetchone()[0]

        # Debita pontos (se houver) e atualiza o total do pedido
        if points_to_redeem and points_to_redeem > 0:
            discount_amount = loyalty_service.redeem_points_for_discount(user_id, points_to_redeem, order_id, cur)
            new_total = max(0, float(total_amount) - float(discount_amount))
            cur.execute("UPDATE ORDERS SET TOTAL_AMOUNT = ? WHERE ID = ?;", (new_total, order_id))
        
        # Preços dos produtos do carrinho
        cart_product_ids = {it["product_id"] for it in cart_data["items"]}
        product_prices = {}
        if cart_product_ids:
            placeholders = ', '.join(['?' for _ in cart_product_ids])
            cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(cart_product_ids))
            product_prices = {row[0]: row[1] for row in cur.fetchall()}

        # Preços dos extras do carrinho
        extra_ids = set()
        for it in cart_data["items"]:
            for ex in it["extras"]:
                extra_ids.add(ex["ingredient_id"])
        extra_prices = {}
        if extra_ids:
            placeholders = ', '.join(['?' for _ in extra_ids])
            cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ids))
            extra_prices = {row[0]: row[1] for row in cur.fetchall()}

        # Copia itens do carrinho para o pedido (com preços)
        for item in cart_data["items"]:
            product_id = item["product_id"]
            quantity = item["quantity"]
            unit_price = product_prices.get(product_id, 0)

            # Insere item principal com UNIT_PRICE
            sql_item = """
                INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE)
                VALUES (?, ?, ?, ?) RETURNING ID;
            """
            cur.execute(sql_item, (order_id, product_id, quantity, unit_price))
            order_item_id = cur.fetchone()[0]

            # Insere extras do item com UNIT_PRICE
            for extra in item["extras"]:
                ex_id = extra["ingredient_id"]
                ex_qty = extra["quantity"]
                ex_price = extra_prices.get(ex_id, 0)
                sql_extra = """
                    INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, UNIT_PRICE)
                    VALUES (?, ?, ?, ?);
                """
                cur.execute(sql_extra, (order_item_id, ex_id, ex_qty, ex_price))
        
        # Limpa o carrinho do usuário
        cart_id = cart_data["cart_id"]
        cur.execute("DELETE FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
        
        # Aplica pontos de fidelidade se houver (apenas se o pedido foi pago)
        if total_amount > 0:
            loyalty_service.earn_points_for_order(user_id, order_id, total_amount, cur)
        
        # Consome pontos se houver
        if points_to_redeem > 0:
            loyalty_service.redeem_points_for_discount(user_id, points_to_redeem, order_id, cur)
        
        # Confirma transação
        conn.commit()
        
        # Notificação para agente de impressão (WebSocket)
        try:
            kitchen_ticket_json = format_order_for_kitchen_json(order_id)
            if kitchen_ticket_json:
                socketio.emit('new_kitchen_order', kitchen_ticket_json)
        except Exception as e:
            print(f"[WARN] Falha ao emitir evento de cozinha do pedido {order_id}: {e}")
        
        # Busca dados completos do pedido criado
        order_data = get_order_details(order_id, user_id, ['customer'])

        # Impressão local opcional (mantida para compatibilidade)
        try:
            if Config.ENABLE_AUTOPRINT and order_data:
                _ = print_kitchen_ticket({
                    "id": order_id,
                    "created_at": order_data.get('created_at'),
                    "order_type": order_data.get('order_type', 'Delivery'),
                    "notes": order_data.get('notes', ''),
                    "items": order_data.get('items', [])
                })
        except Exception as e:
            print(f"[WARN] Falha na impressão automática local do pedido {order_id}: {e}")
        
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