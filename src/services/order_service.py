import fdb
import random
import string
import logging

from . import loyalty_service, notification_service, user_service, email_service, store_service, cart_service, stock_service, settings_service
from .printing_service import print_kitchen_ticket, format_order_for_kitchen_json
from .. import socketio
from ..config import Config
from ..database import get_db_connection
from ..utils import validators

logger = logging.getLogger(__name__)

# Constantes para tipos de pedido
ORDER_TYPE_DELIVERY = 'delivery'
ORDER_TYPE_PICKUP = 'pickup'
VALID_ORDER_TYPES = [ORDER_TYPE_DELIVERY, ORDER_TYPE_PICKUP]

def _validate_order_type(order_type):
    """Valida order_type"""
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(f"order_type deve ser '{ORDER_TYPE_DELIVERY}' ou '{ORDER_TYPE_PICKUP}'")

def _validate_order_data(user_id, address_id, items, payment_method):
    """Valida dados básicos do pedido"""
    if not user_id or not isinstance(user_id, int):
        raise ValueError("user_id deve ser um inteiro válido")
    
    # address_id pode ser None para pickup, mas se fornecido deve ser válido
    if address_id is not None and (not isinstance(address_id, int) or address_id <= 0):
        raise ValueError("address_id deve ser um inteiro válido ou None para pickup")
    
    if not items or not isinstance(items, list) or len(items) == 0:
        raise ValueError("O pedido deve conter pelo menos um item")
    
    if not payment_method or not isinstance(payment_method, str):
        raise ValueError("Método de pagamento é obrigatório")

def _validate_cpf(cpf_on_invoice):
    """Valida CPF se fornecido"""
    if cpf_on_invoice and not validators.is_valid_cpf(cpf_on_invoice):
        raise ValueError(f"O CPF informado '{cpf_on_invoice}' é inválido")

def _validate_points_redemption(points_to_redeem, total_amount):
    """Valida resgate de pontos usando configurações"""
    if points_to_redeem and points_to_redeem > 0:
        # Obter taxa de resgate das configurações
        settings = settings_service.get_all_settings()
        if not settings:
            settings = {}
        
        redemption_rate = float(settings.get('taxa_conversao_resgate_clube', 0.01) or 0.01)
        
        expected_discount = points_to_redeem * redemption_rate
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
    """Calcula total do pedido incluindo extras e base_modifications"""
    product_prices = {}
    order_total = 0.0  # Inicia como float
    product_ids = {item['product_id'] for item in items}
    
    if product_ids:
        placeholders = ', '.join(['?' for _ in product_ids])
        cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(product_ids))
        # Converte Decimal para float ao extrair do banco
        product_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        for item in items:
            price = product_prices.get(item['product_id'], 0.0)
            quantity = item.get('quantity', 1)
            order_total += float(price) * int(quantity)

    # Preços dos extras
    extra_prices = {}
    extra_ingredient_ids = set()
    for item in items:
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_ingredient_ids.add(extra['ingredient_id'])
    
    if extra_ingredient_ids:
        placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
        cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ingredient_ids))
        # Converte Decimal para float ao extrair do banco
        extra_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        for item in items:
            if 'extras' in item and item['extras']:
                for extra in item['extras']:
                    price = extra_prices.get(extra['ingredient_id'], 0.0)
                    quantity = extra.get('quantity', 1)
                    order_total += float(price) * int(quantity)
    
    # Preços das base_modifications (apenas deltas positivos contribuem para preço)
    base_mod_prices = {}
    base_mod_ingredient_ids = set()
    for item in items:
        if 'base_modifications' in item and item['base_modifications']:
            for bm in item['base_modifications']:
                delta = bm.get('delta', 0)
                if delta > 0:  # Apenas deltas positivos adicionam ao preço
                    base_mod_ingredient_ids.add(bm['ingredient_id'])
    
    if base_mod_ingredient_ids:
        placeholders = ', '.join(['?' for _ in base_mod_ingredient_ids])
        cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(base_mod_ingredient_ids))
        # Converte Decimal para float ao extrair do banco
        base_mod_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        for item in items:
            if 'base_modifications' in item and item['base_modifications']:
                for bm in item['base_modifications']:
                    delta = bm.get('delta', 0)
                    if delta > 0:  # Apenas deltas positivos contribuem para o preço
                        price = base_mod_prices.get(bm['ingredient_id'], 0.0)
                        order_total += float(price) * int(delta)

    return float(order_total)

def _add_order_items(order_id, items, cur):
    """Adiciona itens ao pedido"""
    product_prices = {}
    product_ids = {item['product_id'] for item in items}
    
    if product_ids:
        placeholders = ', '.join(['?' for _ in product_ids])
        cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(product_ids))
        # Converte Decimal para float ao extrair do banco
        product_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}

    extra_prices = {}
    extra_ingredient_ids = set()
    for item in items:
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_ingredient_ids.add(extra['ingredient_id'])
    
    if extra_ingredient_ids:
        placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
        cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ingredient_ids))
        # Converte Decimal para float ao extrair do banco
        extra_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}

    for item in items:
        product_id = item.get('product_id')
        quantity = item.get('quantity')
        # Proteção: usa .get() para evitar KeyError se produto foi removido entre validação e inserção
        unit_price = product_prices.get(product_id)
        if unit_price is None:
            raise ValueError(f"Produto {product_id} não encontrado ou preço indisponível")
        
        # Garante que o preço é float
        unit_price = float(unit_price)

        sql_item = "INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE) VALUES (?, ?, ?, ?) RETURNING ID;"
        cur.execute(sql_item, (order_id, product_id, quantity, unit_price))
        new_order_item_id = cur.fetchone()[0]

        # Insere extras (TYPE='extra')
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_id = extra['ingredient_id']
                extra_qty = extra.get('quantity', 1)
                # Proteção: usa .get() para evitar KeyError se ingrediente foi removido
                extra_price = extra_prices.get(extra_id)
                if extra_price is None:
                    raise ValueError(f"Ingrediente {extra_id} não encontrado ou preço indisponível")
                
                # Garante que o preço é float
                extra_price = float(extra_price)
                
                sql_extra = "INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, ?, 'extra', ?, ?);"
                cur.execute(sql_extra, (new_order_item_id, extra_id, extra_qty, extra_qty, extra_price))
        
        # Insere base_modifications (TYPE='base')
        # CORREÇÃO: Buscar preços de base_modifications em batch para evitar query N+1
        if 'base_modifications' in item and item['base_modifications']:
            base_mod_ids = [bm['ingredient_id'] for bm in item['base_modifications'] if bm.get('delta', 0) != 0]
            base_mod_prices_dict = {}
            if base_mod_ids:
                placeholders = ', '.join(['?' for _ in base_mod_ids])
                cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(base_mod_ids))
                base_mod_prices_dict = {row[0]: float(row[1] or 0.0) for row in cur.fetchall()}
            
            for bm in item['base_modifications']:
                bm_id = bm['ingredient_id']
                bm_delta = bm.get('delta', 0)
                if bm_delta != 0:
                    # CORREÇÃO: Verifica se ingrediente foi encontrado (não apenas se preço é 0)
                    if bm_id not in base_mod_prices_dict:
                        raise ValueError(f"Ingrediente {bm_id} não encontrado ou preço indisponível")
                    bm_price = base_mod_prices_dict[bm_id]
                    sql_base_mod = "INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE) VALUES (?, ?, 0, 'base', ?, ?);"
                    cur.execute(sql_base_mod, (new_order_item_id, bm_id, bm_delta, bm_price))

def _notify_kitchen(order_id):
    """Notifica a cozinha sobre novo pedido"""
    try:
        kitchen_ticket_json = format_order_for_kitchen_json(order_id)
        if kitchen_ticket_json:
            socketio.emit('new_kitchen_order', kitchen_ticket_json)
    except Exception as e:
        # Logging estruturado substitui print/TODO
        logger.warning(f"Falha ao notificar cozinha sobre pedido {order_id}: {e}", exc_info=True)


def _generate_confirmation_code(length=8):
    """Gera um código de confirmação alfanumérico aleatório."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def _calculate_estimated_delivery_time(order_status, order_type):
    """
    Calcula o tempo estimado de entrega baseado nos prazos configurados.
    
    Args:
        order_status: Status atual do pedido
        order_type: Tipo do pedido (delivery ou pickup)
    
    Returns:
        dict: Contendo 'estimated_time' (em minutos) e 'breakdown' (detalhamento por fase)
    """
    # Busca configurações com cache
    settings = settings_service.get_all_settings()
    if not settings:
        settings = {}
    
    # Define prazos padrão caso não estejam configurados
    prazo_iniciacao = settings.get('prazo_iniciacao') or 5
    prazo_preparo = settings.get('prazo_preparo') or 20
    prazo_envio = settings.get('prazo_envio') or 5
    # CORREÇÃO: Operador ternário mal formado (linha 271 original)
    prazo_entrega = (settings.get('prazo_entrega') or 15) if order_type == ORDER_TYPE_DELIVERY else 0
    
    # Calcula tempo total baseado no status atual
    # Mapeia status da aplicação para fases do ciclo
    # pending -> fase de iniciacao (aguardando confirmação)
    # confirmed -> fase de preparo
    # preparing -> fase de preparo (em andamento)
    # ready -> fase de envio
    # out_for_delivery, on_the_way -> fase de entrega
    
    if order_status in ['completed', 'delivered']:
        estimated_time = 0
        breakdown = {
            'iniciacao': 0,
            'preparo': 0,
            'envio': 0,
            'entrega': 0,
            'total': 0
        }
    elif order_status in ['out_for_delivery', 'on_the_way']:
        # Já foi iniciado, preparado e enviado - resta apenas entrega
        estimated_time = prazo_entrega
        breakdown = {
            'iniciacao': 0,
            'preparo': 0,
            'envio': 0,
            'entrega': prazo_entrega,
            'total': prazo_entrega
        }
    elif order_status == 'ready':
        # Pronto para enviar - resta envio e entrega
        estimated_time = prazo_envio + prazo_entrega
        breakdown = {
            'iniciacao': 0,
            'preparo': 0,
            'envio': prazo_envio,
            'entrega': prazo_entrega,
            'total': estimated_time
        }
    elif order_status in ['preparing', 'confirmed']:
        # Em preparo - resta preparo, envio e entrega
        estimated_time = prazo_preparo + prazo_envio + prazo_entrega
        breakdown = {
            'iniciacao': 0,
            'preparo': prazo_preparo,
            'envio': prazo_envio,
            'entrega': prazo_entrega,
            'total': estimated_time
        }
    else:
        # pending ou outros status iniciais - todo o ciclo
        estimated_time = prazo_iniciacao + prazo_preparo + prazo_envio + prazo_entrega
        breakdown = {
            'iniciacao': prazo_iniciacao,
            'preparo': prazo_preparo,
            'envio': prazo_envio,
            'entrega': prazo_entrega,
            'total': estimated_time
        }
    
    return {
        'estimated_time': estimated_time,
        'breakdown': breakdown,
        'order_type': order_type
    }

def create_order(user_id, address_id, items, payment_method, amount_paid=None, notes="", cpf_on_invoice=None, points_to_redeem=0, order_type=ORDER_TYPE_DELIVERY):
    """Cria um novo pedido validando TUDO"""
    
    try:
        # Valida order_type
        _validate_order_type(order_type)
        
        # Validações básicas (address_id pode ser None para pickup)
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
            
            # Busca configurações uma única vez
            settings = settings_service.get_all_settings()
            if not settings:
                settings = {}
            
            # VALIDAÇÃO DE ESTOQUE - antes de criar o pedido
            stock_valid, stock_error_code, stock_error_message = stock_service.validate_stock_for_items(items, cur)
            if not stock_valid:
                return (None, stock_error_code, stock_error_message)
            
            # Validações de ingredientes e extras
            _validate_ingredients_and_extras(items, cur)
            
            # Calcula total dos itens
            subtotal = _calculate_order_total(items, cur)
            subtotal = float(subtotal)  # Garante que é float
            
            # Adiciona taxa de entrega se for delivery
            delivery_fee = 0.0
            if order_type == ORDER_TYPE_DELIVERY and settings.get('taxa_entrega'):
                delivery_fee = float(settings.get('taxa_entrega') or 0)
            
            order_total = float(subtotal) + float(delivery_fee)
            
            # Valida resgate de pontos
            _validate_points_redemption(points_to_redeem, order_total)

            # Valida e processa valor pago para pagamento em dinheiro
            paid_amount = None
            if payment_method and payment_method.lower() in ['money', 'dinheiro', 'cash']:
                if amount_paid is None:
                    return (None, "VALIDATION_ERROR", "amount_paid é obrigatório quando o pagamento é em dinheiro")
                try:
                    paid_amount = float(amount_paid)
                    if paid_amount < order_total:
                        return (None, "VALIDATION_ERROR", f"O valor pago (R$ {paid_amount:.2f}) deve ser maior ou igual ao total do pedido (R$ {order_total:.2f})")
                except (ValueError, TypeError):
                    return (None, "VALIDATION_ERROR", "O valor pago deve ser um número válido")

            # Cria o pedido (address_id None para pickup)
            confirmation_code = _generate_confirmation_code()
            sql_order = """
                INSERT INTO ORDERS (USER_ID, ADDRESS_ID, STATUS, TOTAL_AMOUNT, PAYMENT_METHOD, NOTES, CONFIRMATION_CODE, ORDER_TYPE, CHANGE_FOR_AMOUNT)
                VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?) RETURNING ID;
            """
            final_address_id = address_id if order_type == ORDER_TYPE_DELIVERY else None
            # Calcula o troco: amount_paid - order_total (ou None se não for dinheiro)
            # Garante que todos os valores são float para evitar erro Decimal + float
            order_total_float = float(order_total)
            change_amount = None
            if paid_amount is not None:
                paid_amount_float = float(paid_amount)
                change_amount = paid_amount_float - order_total_float
            cur.execute(sql_order, (user_id, final_address_id, order_total_float, payment_method, notes, confirmation_code, order_type, change_amount))
            new_order_id = cur.fetchone()[0]

            # Debita pontos se houver
            if points_to_redeem and points_to_redeem > 0:
                discount_amount = loyalty_service.redeem_points_for_discount(user_id, points_to_redeem, new_order_id, cur)
                discount_amount = float(discount_amount or 0)  # Garante float
                new_total = max(0.0, order_total_float - discount_amount)
                cur.execute("UPDATE ORDERS SET TOTAL_AMOUNT = ? WHERE ID = ?;", (new_total, new_order_id))
                # Recalcula o troco com o novo total após desconto
                if paid_amount is not None:
                    paid_amount_float = float(paid_amount)
                    new_change_amount = paid_amount_float - new_total
                    cur.execute("UPDATE ORDERS SET CHANGE_FOR_AMOUNT = ? WHERE ID = ?;", (new_change_amount, new_order_id))

            # Adiciona itens ao pedido
            _add_order_items(new_order_id, items, cur)
            
            conn.commit()
            
            # Notificação para cozinha
            _notify_kitchen(new_order_id)
            
            return ({"order_id": new_order_id, "confirmation_code": confirmation_code, "status": "pending"}, None, None)

        except fdb.Error as e:
            # Logging estruturado com níveis apropriados
            logger.error(f"Erro no banco de dados ao criar pedido: {e}", exc_info=Config.DEBUG)
            if conn:
                conn.rollback()
            # Verifica se o erro é relacionado a coluna não encontrada
            error_msg = str(e).lower()
            if 'change_for_amount' in error_msg or 'column' in error_msg or 'unknown' in error_msg:
                return (None, "DATABASE_ERROR", "Campo CHANGE_FOR_AMOUNT não existe no banco. Execute a migração: ALTER TABLE ORDERS ADD CHANGE_FOR_AMOUNT DECIMAL(10,2);")
            return (None, "DATABASE_ERROR", "Erro interno do servidor")
        finally:
            if conn:
                conn.close()
            
    except ValueError as e:
        return (None, "VALIDATION_ERROR", str(e))
    except Exception as e:
        # Logging estruturado - traceback apenas em DEBUG
        logger.error(f"Erro inesperado ao processar pedido: {type(e).__name__}: {e}", exc_info=Config.DEBUG)
        return (None, "UNKNOWN_ERROR", "Erro inesperado ao processar pedido")

def get_orders_by_user_id(user_id):
    """Busca o histórico de pedidos de um usuário específico."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT o.ID, o.STATUS, o.CONFIRMATION_CODE, o.CREATED_AT, o.ORDER_TYPE, a.STREET, a."NUMBER"
            FROM ORDERS o
            LEFT JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            WHERE o.USER_ID = ?
            ORDER BY o.CREATED_AT DESC;
        """
        cur.execute(sql, (user_id,))
        orders = []
        for row in cur.fetchall():
            # CORREÇÃO: row[4] é ORDER_TYPE, não índice incorreto
            order_type = row[4] if row[4] else ORDER_TYPE_DELIVERY
            address_str = None
            if order_type == ORDER_TYPE_PICKUP:
                address_str = "Retirada no balcão"
            elif row[5] and row[6]:  # STREET e NUMBER não nulos
                address_str = f"{row[5]}, {row[6]}"
            else:
                address_str = "Endereço não informado"
            
            orders.append({
                "order_id": row[0], "status": row[1], "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S'),
                "order_type": order_type,
                "address": address_str
            })
        return orders
    except fdb.Error as e:
        logger.error(f"Erro ao buscar pedidos do usuário {user_id}: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def get_all_orders():
    """Busca todos os pedidos para a visão do administrador."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql = """
            SELECT o.ID, o.STATUS, o.CONFIRMATION_CODE, o.CREATED_AT, o.ORDER_TYPE, u.FULL_NAME, a.STREET, a."NUMBER"
            FROM ORDERS o
            JOIN USERS u ON o.USER_ID = u.ID
            LEFT JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            ORDER BY o.CREATED_AT DESC;
        """
        cur.execute(sql)
        orders = []
        for row in cur.fetchall():
            # CORREÇÃO: Consistência com get_orders_by_user_id - extrair order_type primeiro
            order_type = row[4] if row[4] else ORDER_TYPE_DELIVERY
            address_str = None
            if order_type == ORDER_TYPE_PICKUP:
                address_str = "Retirada no balcão"
            elif row[6] and row[7]:  # STREET e NUMBER não nulos
                address_str = f"{row[6]}, {row[7]}"
            else:
                address_str = "Endereço não informado"
            
            orders.append({
                "order_id": row[0], "status": row[1], "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S'),
                "order_type": order_type,
                "customer_name": row[5],
                "address": address_str
            })
        return orders
    except fdb.Error as e:
        logger.error(f"Erro ao buscar todos os pedidos: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def update_order_status(order_id, new_status):
    """Atualiza o status de um pedido e adiciona pontos de fidelidade se concluído."""
    # IMPORTANTE: O banco tem constraint CHECK (INTEG_57) que permite apenas:
    # 'pending', 'in_progress', 'awaiting_payment', 'preparing', 'on_the_way', 'delivered', 'cancelled'
    # NOTA: Para suportar pedidos pickup corretamente, execute o script add_ready_status.sql
    # para adicionar 'ready' à constraint. Se não executar, pedidos pickup usarão 'in_progress' temporariamente.
    # Mapeamos 'completed' do frontend para 'delivered' do banco
    # Para pedidos pickup: 'on_the_way' é mapeado para 'ready' (pronto para retirada)
    
    conn = None
    current_status = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Primeiro verifica se o pedido existe, qual o status atual e o tipo
        cur.execute("SELECT STATUS, ORDER_TYPE FROM ORDERS WHERE ID = ?;", (order_id,))
        order_info = cur.fetchone()
        
        if not order_info:
            logger.error(f"Pedido {order_id} não encontrado")
            return False
        
        current_status, order_type = order_info
        
        # Aceita tanto os valores do frontend quanto os do banco
        allowed_statuses = ['pending', 'preparing', 'on_the_way', 'ready', 'completed', 'delivered', 'cancelled']
        if new_status not in allowed_statuses:
            logger.warning(f"Status '{new_status}' não permitido para pedido {order_id}")
            return False
        
        # Mapeia status baseado no tipo de pedido
        # Para pickup: on_the_way -> ready (pronto para retirada)
        # Para delivery: on_the_way -> on_the_way (saindo para entrega)
        if new_status == 'on_the_way':
            if order_type == ORDER_TYPE_PICKUP:
                # Tenta usar 'ready', se não estiver na constraint, usa 'in_progress' como fallback
                db_status = 'ready'  # Para pickup, "pronto" em vez de "saindo para entrega"
            else:
                db_status = 'on_the_way'  # Para delivery, mantém "saindo para entrega"
        elif new_status == 'completed':
            db_status = 'delivered'  # Mapeia completed -> delivered
        elif new_status == 'ready':
            # Se já está enviando 'ready', mantém (pode ser usado para ambos os tipos)
            db_status = 'ready'
        else:
            db_status = new_status
        
        # Se o status é o mesmo (ou equivalente), não precisa atualizar
        if current_status == db_status:
            return True
        
        # Atualiza o status usando o valor mapeado para o banco
        # Se 'ready' não estiver na constraint, tenta usar 'in_progress' como fallback para pickup
        sql_update = "UPDATE ORDERS SET STATUS = ? WHERE ID = ?;"
        try:
            cur.execute(sql_update, (db_status, order_id))
            rows_updated = cur.rowcount  # Salva o rowcount logo após o UPDATE
        except fdb.Error as e:
            error_msg = str(e)
            # Se 'ready' não está permitido e é um pedido pickup, usa 'in_progress' como fallback
            if 'CHECK' in error_msg and db_status == 'ready' and order_type == ORDER_TYPE_PICKUP:
                logger.warning(f"Status 'ready' não está na constraint. Usando 'in_progress' como fallback para pedido pickup {order_id}. Execute add_ready_status.sql para adicionar 'ready' à constraint.")
                db_status = 'in_progress'
                cur.execute(sql_update, (db_status, order_id))
                rows_updated = cur.rowcount
            else:
                raise

        # Deduz estoque quando o pedido é confirmado (status 'preparing')
        if db_status == 'preparing':
            success, error_code, message = stock_service.deduct_stock_for_order(order_id)
            if not success:
                # Se falhou a dedução, reverte o status
                cur.execute("UPDATE ORDERS SET STATUS = 'pending' WHERE ID = ?;", (order_id,))
                conn.commit()
                logger.warning(f"Erro ao deduzir estoque para pedido {order_id}: {message}")
                return False
            logger.info(f"Estoque deduzido para pedido {order_id}: {message}")

        # Busca dados do pedido uma única vez para uso em múltiplas operações
        # order_type já foi obtido acima, então busca apenas USER_ID e TOTAL_AMOUNT
        cur.execute("""
            SELECT USER_ID, TOTAL_AMOUNT FROM ORDERS WHERE ID = ?;
        """, (order_id,))
        order_data = cur.fetchone()
        
        if not order_data:
            conn.rollback()
            return False
        
        user_id, stored_total = order_data
        total_after_discount = float(stored_total) if stored_total else 0.0
        
        # Processa crédito de pontos apenas quando entregue (delivered)
        if db_status == 'delivered':
            # Busca configurações para taxa de entrega
            settings = settings_service.get_all_settings()
            delivery_fee = 0.0
            if order_type == ORDER_TYPE_DELIVERY and settings and settings.get('taxa_entrega'):
                delivery_fee = float(settings.get('taxa_entrega'))
            
            # Calcula subtotal (soma dos itens) e desconto
            # Para extras e base_modifications, usa DELTA para multiplicar
            try:
                # Primeiro verifica se o pedido tem itens
                cur.execute("SELECT COUNT(*) FROM ORDER_ITEMS WHERE ORDER_ID = ?;", (order_id,))
                item_count = cur.fetchone()[0]
                
                if item_count > 0:
                    cur.execute("""
                        SELECT 
                            CAST(COALESCE(SUM(oi.QUANTITY * oi.UNIT_PRICE), 0) AS DECIMAL(10,2)) as SUBTOTAL_ITEMS,
                            CAST(COALESCE(SUM(
                                CASE 
                                    WHEN oie.DELTA IS NOT NULL THEN oie.DELTA * oie.UNIT_PRICE
                                    ELSE oie.QUANTITY * oie.UNIT_PRICE
                                END
                            ), 0) AS DECIMAL(10,2)) as TOTAL_EXTRAS
                        FROM ORDER_ITEMS oi
                        LEFT JOIN ORDER_ITEM_EXTRAS oie ON oi.ID = oie.ORDER_ITEM_ID
                        WHERE oi.ORDER_ID = ?;
                    """, (order_id,))
                    row = cur.fetchone()
                    if row:
                        subtotal_items = float(row[0]) if row[0] is not None else 0.0
                        total_extras = float(row[1]) if row[1] is not None else 0.0
                        subtotal = subtotal_items + total_extras
                        
                        # Calcula desconto aplicado
                        total_before_discount = subtotal + delivery_fee
                        discount_applied = total_before_discount - total_after_discount
                        
                        # Credita pontos usando função precisa
                        try:
                            loyalty_service.earn_points_for_order_with_details(
                                user_id, order_id, subtotal, discount_applied, delivery_fee, cur
                            )
                        except Exception as e:
                            logger.error(f"Erro ao creditar pontos para pedido {order_id}: {e}", exc_info=True)
                            # Não falha o pedido por erro nos pontos, apenas loga
                    else:
                        logger.warning(f"Pedido {order_id} não retornou dados do cálculo de subtotal")
                else:
                    logger.warning(f"Pedido {order_id} não tem itens para calcular pontos")
            except Exception as e:
                logger.error(f"Erro ao calcular subtotal do pedido {order_id}: {e}", exc_info=True)
                # Continua mesmo se houver erro no cálculo

        conn.commit()
        
        # Envia notificação após commit bem-sucedido
        # Para pickup com status ready ou in_progress (fallback), mensagem personalizada
        if (db_status == 'ready' or db_status == 'in_progress') and order_type == ORDER_TYPE_PICKUP:
            notification_message = f"Seu pedido #{order_id} está pronto para retirada no balcão!"
        else:
            notification_message = f"O status do seu pedido #{order_id} foi atualizado para {new_status}"
        notification_link = f"/my-orders/{order_id}"
        notification_service.create_notification(user_id, notification_message, notification_link)
        
        # Envia email de notificação
        customer = user_service.get_user_by_id(user_id)
        if customer:
            try:
                email_service.send_email(
                    to=customer['email'],
                    subject=f"Atualização sobre seu pedido #{order_id}",
                    template='order_status_update',
                    user=customer,
                    order={"order_id": order_id},
                    new_status=new_status
                )
            except Exception as e:
                logger.error(f"Erro ao enviar email para pedido {order_id}: {e}", exc_info=True)
                # Não falha a operação por erro no email

        # Retorna True se a atualização foi bem-sucedida (rowcount > 0)
        # ou se chegou até aqui sem erros (indica sucesso)
        return rows_updated > 0
    except fdb.Error as e:
        error_msg = str(e)
        logger.error(f"Erro ao atualizar status do pedido {order_id} para '{new_status}': {error_msg}", exc_info=True)
        
        # Verifica se é erro de constraint
        if 'CHECK' in error_msg or 'constraint' in error_msg or 'INTEG_57' in error_msg:
            status_info = f"Status atual: '{current_status}'" if current_status else "Status atual: desconhecido"
            logger.error(f"Constraint CHECK violada. {status_info}, Status tentado: '{new_status}'. Verifique se o valor é permitido pela constraint do banco.")
        
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

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
                   PAYMENT_METHOD, TOTAL_AMOUNT, CREATED_AT, ORDER_TYPE, CHANGE_FOR_AMOUNT
            FROM ORDERS WHERE ID = ?;
        """
        cur.execute(sql_order, (order_id,))
        order_row = cur.fetchone()

        if not order_row:
            return None

        # Calcula amount_paid quando há troco (amount_paid = total + change)
        total = float(order_row[7]) if order_row[7] is not None else 0.0
        change = float(order_row[10]) if order_row[10] is not None else None
        amount_paid = (total + change) if change is not None else (total if total > 0 else None)
        
        order_details = {
            "id": order_row[0], "user_id": order_row[1], "address_id": order_row[2],
            "status": order_row[3], "confirmation_code": order_row[4], "notes": order_row[5],
            "payment_method": order_row[6], "total_amount": total,
            "created_at": order_row[8].strftime('%Y-%m-%d %H:%M:%S') if order_row[8] else None,
            "order_type": order_row[9] if order_row[9] else 'delivery',
            "change_for_amount": change,
            "amount_paid": amount_paid
        }

        # Verificação de segurança: cliente só pode ver seus próprios pedidos
        if user_role == 'customer' and order_details['user_id'] != user_id:
            return None 
        
        # CORREÇÃO: Evitar query N+1 - buscar todos os extras de uma vez
        # Primeiro busca todos os itens
        sql_items = """
            SELECT oi.ID, oi.QUANTITY, oi.UNIT_PRICE, p.NAME, p.DESCRIPTION
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE oi.ORDER_ID = ?;
        """
        cur.execute(sql_items, (order_id,))
        item_rows = cur.fetchall()
        
        if not item_rows:
            order_details['items'] = []
            return order_details
        
        # Busca todos os extras de uma vez (evita N+1)
        order_item_ids = [row[0] for row in item_rows]
        placeholders = ', '.join(['?' for _ in order_item_ids])
        sql_extras = f"""
            SELECT e.ORDER_ITEM_ID, e.INGREDIENT_ID, i.NAME, e.QUANTITY, e.TYPE, COALESCE(e.DELTA, e.QUANTITY) as DELTA
            FROM ORDER_ITEM_EXTRAS e
            JOIN INGREDIENTS i ON i.ID = e.INGREDIENT_ID
            WHERE e.ORDER_ITEM_ID IN ({placeholders})
            ORDER BY e.ORDER_ITEM_ID, e.TYPE, i.NAME
        """
        cur.execute(sql_extras, tuple(order_item_ids))
        extras_dict = {}
        for ex in cur.fetchall():
            order_item_id = ex[0]
            if order_item_id not in extras_dict:
                extras_dict[order_item_id] = {'extras': [], 'base_modifications': []}
            row_type = (ex[4] or 'extra').lower()
            if row_type == 'extra':
                extras_dict[order_item_id]['extras'].append({
                    "ingredient_id": ex[1],
                    "name": ex[2],
                    "quantity": ex[3]
                })
            elif row_type == 'base':
                extras_dict[order_item_id]['base_modifications'].append({
                    "ingredient_id": ex[1],
                    "name": ex[2],
                    "delta": int(ex[5])
                })

        # Monta lista de itens com seus extras
        order_items = []
        for item_row in item_rows:
            order_item_id = item_row[0]
            item_dict = {
                "quantity": item_row[1],
                "unit_price": item_row[2],
                "product_name": item_row[3],
                "product_description": item_row[4],
                "extras": extras_dict.get(order_item_id, {}).get('extras', []),
                "base_modifications": extras_dict.get(order_item_id, {}).get('base_modifications', [])
            }
            order_items.append(item_dict)

        order_details['items'] = order_items
        
        # Adiciona tempo estimado de entrega baseado nos prazos configurados
        estimated_delivery = _calculate_estimated_delivery_time(
            order_details['status'], 
            order_details['order_type']
        )
        order_details['estimated_delivery'] = estimated_delivery
        
        return order_details

    except fdb.Error as e:
        logger.error(f"Erro ao buscar detalhes do pedido {order_id}: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def cancel_order(order_id, user_id, is_manager=False):
    """
    Permite que um cliente ou gerente cancele um pedido.
    
    - Cliente: só pode cancelar seus próprios pedidos com status 'pending'
    - Gerente: pode cancelar qualquer pedido (exceto os já concluídos ou cancelados)
    
    Args:
        order_id: ID do pedido
        user_id: ID do usuário que está cancelando
        is_manager: True se o usuário é gerente ou admin
    
    Returns:
        Tupla (sucesso, mensagem).
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        sql_find = "SELECT USER_ID, STATUS, ORDER_TYPE FROM ORDERS WHERE ID = ?;"
        cur.execute(sql_find, (order_id,))
        order_record = cur.fetchone()

        if not order_record:
            return (False, "Pedido não encontrado.")

        owner_id, status, order_type = order_record

        # Verifica se o pedido já está cancelado ou concluído
        if status == 'cancelled':
            return (False, "O pedido já está cancelado.")
        
        if status in ['completed', 'delivered']:
            return (False, f"Não é possível cancelar um pedido que já foi concluído (status: '{status}').")

        # Verificação de autorização
        if not is_manager:
            # Cliente: apenas o dono pode cancelar
            if owner_id != user_id:
                return (False, "Você não tem permissão para cancelar este pedido.")
            
            # Cliente: apenas pedidos pendentes podem ser cancelados
            if status != 'pending':
                return (False, f"Não é possível cancelar um pedido que já está com o status '{status}'. Apenas pedidos pendentes podem ser cancelados.")
        
        # Para gerentes, verifica se o pedido pode ser cancelado
        # Gerentes não podem cancelar pedidos que já foram entregues ou concluídos
        # Mas podem cancelar pedidos em outros status (preparing, confirmed, etc.)
        
        # Se for pedido on-site (active_table), libera a mesa antes de cancelar
        if order_type == ORDER_TYPE_ON_SITE and status == ORDER_STATUS_ACTIVE_TABLE:
            # Busca o TABLE_ID
            cur.execute("SELECT TABLE_ID FROM ORDERS WHERE ID = ?;", (order_id,))
            table_result = cur.fetchone()
            if table_result and table_result[0]:
                table_id = table_result[0]
                # Libera a mesa
                table_service.set_table_available(table_id)

        # Cancela o pedido
        sql_update = "UPDATE ORDERS SET STATUS = 'cancelled', UPDATED_AT = CURRENT_TIMESTAMP WHERE ID = ?;"
        cur.execute(sql_update, (order_id,))
        conn.commit()

        # Envia notificações de cancelamento
        try:
            # Se o cancelamento foi feito por gerente, notifica o cliente
            target_user_id = owner_id if is_manager else user_id
            
            if is_manager:
                message = f"Seu pedido #{order_id} foi cancelado pelo gerente."
            else:
                message = f"Seu pedido #{order_id} foi cancelado com sucesso!"
            
            link = f"/my-orders/{order_id}"
            notification_service.create_notification(target_user_id, message, link)

            customer = user_service.get_user_by_id(target_user_id)
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
            logger.warning(f"Falha ao enviar notificação de cancelamento para o pedido {order_id}: {e}", exc_info=True)

        if is_manager:
            return (True, f"Pedido #{order_id} cancelado pelo gerente com sucesso.")
        else:
            return (True, "Pedido cancelado com sucesso.")

    except fdb.Error as e:
        logger.error(f"Erro ao cancelar pedido {order_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "Ocorreu um erro interno ao tentar cancelar o pedido.")
    finally:
        if conn:
            conn.close()


def cancel_order_by_customer(order_id, user_id):
    """
    Função de compatibilidade para manter o código antigo funcionando.
    Permite que um cliente cancele seu próprio pedido.
    Retorna uma tupla: (sucesso, mensagem).
    """
    return cancel_order(order_id, user_id, is_manager=False)


def create_order_from_cart(user_id, address_id, payment_method, amount_paid=None, notes="", cpf_on_invoice=None, points_to_redeem=0, order_type=ORDER_TYPE_DELIVERY):
    """
    Fluxo 4: Finalização (Converter Carrinho em Pedido)
    Cria um pedido a partir do carrinho do usuário
    """
    conn = None
    try:
        # Valida order_type
        _validate_order_type(order_type)
        
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
        
        # VALIDAÇÃO DE ESTOQUE - antes de criar o pedido
        stock_valid, stock_error_code, stock_error_message = stock_service.validate_stock_for_items(cart_data["items"], cur)
        if not stock_valid:
            return (None, stock_error_code, stock_error_message)
        
        # Validações básicas
        if cpf_on_invoice and not validators.is_valid_cpf(cpf_on_invoice):
            return (None, "INVALID_CPF", f"O CPF informado '{cpf_on_invoice}' é inválido.")
        
        # Verifica endereço apenas se for delivery (evita query desnecessária para pickup)
        if order_type == ORDER_TYPE_DELIVERY:
            if not address_id:
                return (None, "INVALID_ADDRESS", "address_id é obrigatório para pedidos de entrega")
            cur.execute("SELECT ID FROM ADDRESSES WHERE ID = ? AND USER_ID = ? AND IS_ACTIVE = TRUE;", (address_id, user_id))
            if not cur.fetchone():
                return (None, "INVALID_ADDRESS", "Endereço não encontrado ou não pertence ao usuário.")
        
        # Gera código de confirmação
        confirmation_code = _generate_confirmation_code()
        
        # Busca configurações uma única vez
        settings = settings_service.get_all_settings()
        if not settings:
            settings = {}
        
        # Calcula total do carrinho
        total_amount = float(cart_data["total_amount"] or 0)  # Garante float
        
        # Adiciona taxa de entrega se for delivery
        delivery_fee = 0.0
        if order_type == ORDER_TYPE_DELIVERY and settings.get('taxa_entrega'):
            delivery_fee = float(settings.get('taxa_entrega') or 0)
        
        total_with_delivery = float(total_amount) + float(delivery_fee)
        
        # Valida desconto de pontos (sem debitar ainda)
        if points_to_redeem and points_to_redeem > 0:
            redemption_rate = float(settings.get('taxa_conversao_resgate_clube', 0.01) or 0.01)
            expected_discount = points_to_redeem * redemption_rate
            if expected_discount > total_with_delivery:
                return (None, "INVALID_DISCOUNT", "O valor do desconto não pode ser maior que o total do pedido.")
        
        # Valida e processa valor pago para pagamento em dinheiro
        paid_amount = None
        if payment_method and payment_method.lower() in ['money', 'dinheiro', 'cash']:
            if amount_paid is None:
                return (None, "VALIDATION_ERROR", "amount_paid é obrigatório quando o pagamento é em dinheiro")
            try:
                paid_amount = float(amount_paid)
                if paid_amount < total_with_delivery:
                    return (None, "VALIDATION_ERROR", f"O valor pago (R$ {paid_amount:.2f}) deve ser maior ou igual ao total do pedido (R$ {total_with_delivery:.2f})")
            except (ValueError, TypeError):
                return (None, "VALIDATION_ERROR", "O valor pago deve ser um número válido")
        
        # Cria o pedido (address_id None para pickup)
        sql_order = """
            INSERT INTO ORDERS (USER_ID, ADDRESS_ID, STATUS, TOTAL_AMOUNT, PAYMENT_METHOD, 
                                NOTES, CONFIRMATION_CODE, ORDER_TYPE, CHANGE_FOR_AMOUNT)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?) RETURNING ID;
        """
        final_address_id = address_id if order_type == ORDER_TYPE_DELIVERY else None
        # Calcula o troco: amount_paid - total_with_delivery (ou None se não for dinheiro)
        # Garante que todos os valores são float
        total_with_delivery_float = float(total_with_delivery)
        change_amount = None
        if paid_amount is not None:
            paid_amount_float = float(paid_amount)
            change_amount = paid_amount_float - total_with_delivery_float
        cur.execute(sql_order, (user_id, final_address_id, total_with_delivery_float, payment_method, notes, confirmation_code, order_type, change_amount))
        order_id = cur.fetchone()[0]

        # Debita pontos (se houver) e atualiza o total do pedido
        if points_to_redeem > 0:
            discount_amount = loyalty_service.redeem_points_for_discount(user_id, points_to_redeem, order_id, cur)
            discount_amount = float(discount_amount or 0)  # Garante float
            total_with_delivery_float = float(total_with_delivery)
            new_total = max(0.0, total_with_delivery_float - discount_amount)
            cur.execute("UPDATE ORDERS SET TOTAL_AMOUNT = ? WHERE ID = ?;", (new_total, order_id))
            # Recalcula o troco com o novo total após desconto
            if paid_amount is not None:
                paid_amount_float = float(paid_amount)
                new_change_amount = paid_amount_float - new_total
                cur.execute("UPDATE ORDERS SET CHANGE_FOR_AMOUNT = ? WHERE ID = ?;", (new_change_amount, order_id))
        
        # Preços dos produtos do carrinho
        cart_product_ids = {it["product_id"] for it in cart_data["items"]}
        product_prices = {}
        if cart_product_ids:
            placeholders = ', '.join(['?' for _ in cart_product_ids])
            cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(cart_product_ids))
            # Converte Decimal para float ao extrair do banco
            product_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}

        # Preços dos extras do carrinho
        extra_ids = set()
        base_mod_ids = set()
        for it in cart_data["items"]:
            for ex in it.get("extras", []):
                extra_ids.add(ex["ingredient_id"])
            for bm in it.get("base_modifications", []):
                base_mod_ids.add(bm["ingredient_id"])
        
        extra_prices = {}
        if extra_ids:
            placeholders = ', '.join(['?' for _ in extra_ids])
            cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ids))
            # Converte Decimal para float ao extrair do banco
            extra_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        base_mod_prices = {}
        if base_mod_ids:
            placeholders = ', '.join(['?' for _ in base_mod_ids])
            cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(base_mod_ids))
            # Converte Decimal para float ao extrair do banco
            base_mod_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}

        # Copia itens do carrinho para o pedido (com preços)
        for item in cart_data["items"]:
            product_id = item["product_id"]
            quantity = item["quantity"]
            # CORREÇÃO: Valida se produto existe antes de inserir
            unit_price = product_prices.get(product_id)
            if unit_price is None:
                raise ValueError(f"Produto {product_id} não encontrado ou preço indisponível")

            # Insere item principal com UNIT_PRICE
            # Garante que unit_price é float
            unit_price_float = float(unit_price)
            
            sql_item = """
                INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE)
                VALUES (?, ?, ?, ?) RETURNING ID;
            """
            cur.execute(sql_item, (order_id, product_id, quantity, unit_price_float))
            order_item_id = cur.fetchone()[0]

            # Insere extras do item (TYPE='extra')
            for extra in item.get("extras", []):
                ex_id = extra["ingredient_id"]
                ex_qty = extra.get("quantity", 1)
                # CORREÇÃO: Valida se ingrediente existe antes de inserir
                ex_price = extra_prices.get(ex_id)
                if ex_price is None:
                    raise ValueError(f"Ingrediente {ex_id} não encontrado ou preço indisponível")
                
                # Garante que o preço é float
                ex_price_float = float(ex_price)
                
                sql_extra = """
                    INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE)
                    VALUES (?, ?, ?, 'extra', ?, ?);
                """
                cur.execute(sql_extra, (order_item_id, ex_id, ex_qty, ex_qty, ex_price_float))
            
            # Insere base_modifications do item (TYPE='base')
            for bm in item.get("base_modifications", []):
                bm_id = bm["ingredient_id"]
                bm_delta = bm.get("delta", 0)
                if bm_delta != 0:
                    # CORREÇÃO: Valida se ingrediente existe antes de inserir
                    bm_price = base_mod_prices.get(bm_id)
                    if bm_price is None:
                        raise ValueError(f"Ingrediente {bm_id} não encontrado ou preço indisponível")
                    
                    # Garante que o preço é float
                    bm_price_float = float(bm_price)
                    
                    sql_base_mod = """
                        INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE)
                        VALUES (?, ?, 0, 'base', ?, ?);
                    """
                    cur.execute(sql_base_mod, (order_item_id, bm_id, bm_delta, bm_price_float))
        
        # Limpa o carrinho do usuário
        cart_id = cart_data["cart_id"]
        cur.execute("DELETE FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
        
        # Nota: Pontos de fidelidade serão creditados apenas quando o pedido for concluído (status='completed')
        # Ver função update_order_status para lógica de crédito de pontos
        
        # Confirma transação
        conn.commit()
        
        # Notificação para agente de impressão (WebSocket)
        try:
            kitchen_ticket_json = format_order_for_kitchen_json(order_id)
            if kitchen_ticket_json:
                socketio.emit('new_kitchen_order', kitchen_ticket_json)
        except Exception as e:
            logger.warning(f"Falha ao notificar cozinha sobre pedido {order_id}: {e}", exc_info=True)
        
        # Busca dados completos do pedido criado
        order_data = get_order_details(order_id, user_id, ['customer'])

        # Impressão local opcional (mantida para compatibilidade)
        try:
            if Config.ENABLE_AUTOPRINT and order_data:
                print_kitchen_ticket({
                    "id": order_id,
                    "created_at": order_data.get('created_at'),
                    "order_type": order_data.get('order_type', 'Delivery'),
                    "notes": order_data.get('notes', ''),
                    "items": order_data.get('items', [])
                })
        except Exception as e:
            logger.warning(f"Falha ao imprimir ticket do pedido {order_id}: {e}", exc_info=True)
        
        # Envia notificação
        try:
            notification_service.send_order_confirmation(user_id, order_data)
        except Exception as e:
            logger.error(f"Falha ao enviar notificação de confirmação do pedido {order_id}: {e}", exc_info=True)
        
        return (order_data, None, "Pedido criado com sucesso a partir do carrinho")
        
    except fdb.Error as e:
        logger.error(f"Erro no banco de dados ao criar pedido do carrinho: {e}", exc_info=Config.DEBUG)
        if conn:
            conn.rollback()
        # Verifica se o erro é relacionado a coluna não encontrada
        error_msg = str(e).lower()
        if 'change_for_amount' in error_msg or 'column' in error_msg or 'unknown' in error_msg:
            return (None, "DATABASE_ERROR", "Campo CHANGE_FOR_AMOUNT não existe no banco. Execute a migração: ALTER TABLE ORDERS ADD CHANGE_FOR_AMOUNT DECIMAL(10,2);")
        return (None, "DATABASE_ERROR", "Erro interno do servidor")
    except Exception as e:
        logger.error(f"Erro inesperado ao processar pedido do carrinho: {type(e).__name__}: {e}", exc_info=Config.DEBUG)
        if conn:
            conn.rollback()
        return (None, "UNKNOWN_ERROR", "Erro inesperado ao processar pedido")
    finally:
        if conn:
            conn.close()


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
                   o.ORDER_TYPE, u.FULL_NAME as customer_name, a.STREET, a."NUMBER"
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
            # Monta endereço ou exibe tipo de retirada
            order_type = row[5] if row[5] else ORDER_TYPE_DELIVERY
            address_str = None
            if order_type == ORDER_TYPE_PICKUP:
                address_str = "Retirada no balcão"
            elif row[7] and row[8]:  # STREET e NUMBER não nulos
                address_str = f"{row[7]}, {row[8]}"
            else:
                address_str = "Endereço não informado"
            
            orders.append({
                "id": row[0],
                "status": row[1],
                "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else None,
                "total_amount": float(row[4]) if row[4] else 0.0,
                "order_type": order_type,
                "customer_name": row[6],
                "address": address_str
            })
        
        return orders
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar pedidos com filtros: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def calculate_order_total_with_fees(items, points_to_redeem=0, order_type=ORDER_TYPE_DELIVERY):
    """
    Calcula o total de um pedido SEM criar o pedido
    Usa as configurações do sistema para taxa de entrega
    Retorna breakdown completo
    """
    conn = None
    try:
        # Valida order_type
        _validate_order_type(order_type)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Valida e calcula subtotal dos items
        _validate_ingredients_and_extras(items, cur)
        subtotal = _calculate_order_total(items, cur)
        
        # Busca taxa de entrega das configurações (apenas para delivery)
        # Cache já implementado em settings_service
        settings = settings_service.get_all_settings()
        if not settings:
            settings = {}
        
        delivery_fee = 0
        if order_type == ORDER_TYPE_DELIVERY and settings.get('taxa_entrega'):
            delivery_fee = float(settings.get('taxa_entrega'))
        
        # Calcular desconto por pontos
        discount_amount = 0
        if points_to_redeem and points_to_redeem > 0:
            # Obter taxa de resgate das configurações
            redemption_rate = float(settings.get('taxa_conversao_resgate_clube', 0.01) or 0.01)
            discount_amount = points_to_redeem * redemption_rate
            # Validar que o desconto não excede o total
            if discount_amount > subtotal + delivery_fee:
                discount_amount = subtotal + delivery_fee
        
        # Total final
        total = subtotal + delivery_fee - discount_amount
        
        # Montar breakdown detalhado
        breakdown = _build_order_breakdown(items, cur)
        
        return {
            "subtotal": float(subtotal),
            "delivery_fee": float(delivery_fee),
            "discount_from_points": float(discount_amount),
            "total": float(total),
            "breakdown": breakdown,
            "order_type": order_type
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao calcular total do pedido: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def _build_order_breakdown(items, cur):
    """Monta breakdown detalhado dos itens do pedido"""
    product_prices = {}
    extra_prices = {}
    product_ids = {item['product_id'] for item in items}
    
    # Busca preços dos produtos
    if product_ids:
        placeholders = ', '.join(['?' for _ in product_ids])
        cur.execute(f"SELECT ID, NAME, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(product_ids))
        for row in cur.fetchall():
            product_prices[row[0]] = {
                'name': row[1],
                'price': float(row[2])
            }
    
    # Busca preços dos extras
    extra_ingredient_ids = set()
    for item in items:
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_ingredient_ids.add(extra['ingredient_id'])
    
    if extra_ingredient_ids:
        placeholders = ', '.join(['?' for _ in extra_ingredient_ids])
        cur.execute(f"SELECT ID, NAME, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ingredient_ids))
        for row in cur.fetchall():
            extra_prices[row[0]] = {
                'name': row[1],
                'price': float(row[2])
            }
    
    # Monta breakdown
    breakdown = []
    for item in items:
        product_id = item['product_id']
        quantity = item.get('quantity', 1)
        product_info = product_prices.get(product_id, {})
        
        item_total = product_info.get('price', 0) * quantity
        extras_info = []
        
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_id = extra['ingredient_id']
                extra_qty = extra.get('quantity', 1)
                extra_info = extra_prices.get(extra_id, {})
                extra_total = extra_info.get('price', 0) * extra_qty
                item_total += extra_total
                
                extras_info.append({
                    'name': extra_info.get('name', 'Extra'),
                    'quantity': extra_qty,
                    'unit_price': extra_info.get('price', 0),
                    'total': extra_total
                })
        
        breakdown.append({
            'product_name': product_info.get('name', 'Produto'),
            'quantity': quantity,
            'unit_price': product_info.get('price', 0),
            'extras': extras_info,
            'item_total': item_total
        })
    
    return breakdown