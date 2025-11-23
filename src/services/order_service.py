import fdb
import random
import string
import logging
from datetime import datetime, date, timedelta

from . import loyalty_service, notification_service, user_service, email_service, store_service, cart_service, stock_service, settings_service, table_service, promotion_service, financial_movement_service
from .printing_service import print_kitchen_ticket, format_order_for_kitchen_json
from .. import socketio
from ..config import Config
from ..database import get_db_connection
from ..utils import validators

logger = logging.getLogger(__name__)

# Constantes para tipos de pedido
ORDER_TYPE_DELIVERY = 'delivery'
ORDER_TYPE_PICKUP = 'pickup'
ORDER_TYPE_ON_SITE = 'on_site'  # Pedido presencial no restaurante
VALID_ORDER_TYPES = [ORDER_TYPE_DELIVERY, ORDER_TYPE_PICKUP, ORDER_TYPE_ON_SITE]

# Constantes para status de pedido
ORDER_STATUS_ACTIVE_TABLE = 'active_table'  # Mesa ativa para pedido on-site

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

def _apply_promotion_to_price(product_price, promotion):
    """
    Aplica desconto de promoção ao preço do produto
    
    Args:
        product_price: Preço original do produto
        promotion: Dicionário com dados da promoção (pode ser None)
    
    Returns:
        Tuple (preco_final, valor_desconto, tem_promocao)
    """
    if not promotion:
        return (float(product_price), 0.0, False)
    
    try:
        price = float(product_price)
        discount_percentage = promotion.get('discount_percentage')
        discount_value = promotion.get('discount_value')
        
        # Aplica desconto percentual ou em valor fixo
        if discount_percentage and discount_percentage > 0:
            discount = (price * discount_percentage) / 100.0
            final_price = price - discount
        elif discount_value and discount_value > 0:
            discount = float(discount_value)
            final_price = price - discount
        else:
            return (price, 0.0, False)
        
        # Garante que o preço final não seja negativo
        final_price = max(0.0, final_price)
        return (final_price, discount, True)
    except (ValueError, TypeError, AttributeError):
        return (float(product_price), 0.0, False)

def _calculate_order_total(items, cur, promotions_map=None):
    """
    Calcula total do pedido incluindo extras e base_modifications
    ALTERAÇÃO: Agora aplica promoções se fornecido promotions_map
    """
    product_prices = {}
    order_total = 0.0  # Inicia como float
    product_ids = {item['product_id'] for item in items}
    
    if product_ids:
        placeholders = ', '.join(['?' for _ in product_ids])
        cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(product_ids))
        # Converte Decimal para float ao extrair do banco
        product_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        for item in items:
            product_id = item['product_id']
            original_price = product_prices.get(product_id, 0.0)
            
            # ALTERAÇÃO: Aplicar promoção se fornecida
            if promotions_map and product_id in promotions_map:
                promotion = promotions_map[product_id]
                price, _, _ = _apply_promotion_to_price(original_price, promotion)
            else:
                # ALTERAÇÃO: Buscar promoção ativa se não fornecida
                promotion = promotion_service.get_promotion_by_product_id(product_id, include_expired=False)
                price, _, _ = _apply_promotion_to_price(original_price, promotion)
            
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

def _add_order_items(order_id, items, cur, promotions_map=None):
    """
    Adiciona itens ao pedido
    ALTERAÇÃO: Agora aplica promoções e salva preços com desconto
    """
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
        original_price = product_prices.get(product_id)
        if original_price is None:
            raise ValueError(f"Produto {product_id} não encontrado ou preço indisponível")
        
        # ALTERAÇÃO: Aplicar promoção ao preço antes de salvar
        if promotions_map and product_id in promotions_map:
            promotion = promotions_map[product_id]
            unit_price, _, _ = _apply_promotion_to_price(original_price, promotion)
        else:
            # ALTERAÇÃO: Buscar promoção ativa se não fornecida
            promotion = promotion_service.get_promotion_by_product_id(product_id, include_expired=False)
            unit_price, _, _ = _apply_promotion_to_price(original_price, promotion)
        
        # Garante que o preço é float
        unit_price = float(unit_price)

        # ALTERAÇÃO: Salvar preço COM desconto aplicado no banco
        sql_item = "INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE) VALUES (?, ?, ?, ?) RETURNING ID;"
        cur.execute(sql_item, (order_id, product_id, quantity, unit_price))
        new_order_item_id = cur.fetchone()[0]

        # Insere extras (TYPE='extra')
        if 'extras' in item and item['extras']:
            for extra in item['extras']:
                extra_id = extra.get('ingredient_id')
                extra_qty = int(extra.get('quantity', 1))
                
                # IMPORTANTE: Não insere extras com quantidade 0 ou negativa
                if extra_qty <= 0:
                    logger.warning(f"[_add_order_items] Pulando extra com quantidade inválida: ingredient_id={extra_id}, quantity={extra_qty}")
                    continue
                
                # Proteção: usa .get() para evitar KeyError se ingrediente foi removido
                extra_price = extra_prices.get(extra_id)
                if extra_price is None:
                    raise ValueError(f"Ingrediente {extra_id} não encontrado ou preço indisponível")
                
                # Garante que o preço é float
                extra_price = float(extra_price)
                
                logger.info(f"[_add_order_items] Inserindo extra: order_item_id={new_order_item_id}, ingredient_id={extra_id}, quantity={extra_qty}, price={extra_price}")
                
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

def create_order(user_id, address_id, items, payment_method, amount_paid=None, notes="", cpf_on_invoice=None, points_to_redeem=0, order_type=ORDER_TYPE_DELIVERY, promotions=None, table_id=None):
    """
    Cria um novo pedido validando TUDO
    ALTERAÇÃO: Agora aceita promotions para aplicar descontos
    ALTERAÇÃO: Agora aceita table_id para pedidos on-site
    """
    
    try:
        # Valida order_type
        _validate_order_type(order_type)
        
        # ALTERAÇÃO: Validação de mesa para pedidos on-site (opcional)
        if order_type == ORDER_TYPE_ON_SITE:
            # Se table_id foi fornecido, valida que está correto e disponível
            if table_id is not None:
                if not isinstance(table_id, int) or table_id <= 0:
                    return (None, "VALIDATION_ERROR", "table_id deve ser um número inteiro válido")
                # Verifica se a mesa existe e está disponível
                if not table_service.is_table_available(table_id):
                    table_info = table_service.get_table_by_id(table_id)
                    if not table_info:
                        return (None, "TABLE_NOT_FOUND", "Mesa não encontrada")
                    return (None, "TABLE_NOT_AVAILABLE", f"Mesa {table_info.get('name', table_id)} não está disponível")
        elif table_id is not None:
            # Se table_id foi fornecido mas order_type não é on_site, rejeitar
            return (None, "VALIDATION_ERROR", "table_id só pode ser fornecido para pedidos on-site")
        
        # Validações básicas (address_id pode ser None para pickup e on-site)
        if order_type != ORDER_TYPE_ON_SITE:
            _validate_order_data(user_id, address_id, items, payment_method)
        else:
            # Para pedidos on-site, address_id deve ser None
            if address_id is not None:
                return (None, "VALIDATION_ERROR", "address_id deve ser None para pedidos on-site")
            # Valida apenas items e payment_method
            if not items or not isinstance(items, list) or len(items) == 0:
                return (None, "VALIDATION_ERROR", "O pedido deve conter pelo menos um item")
            if not payment_method or not isinstance(payment_method, str):
                return (None, "VALIDATION_ERROR", "Método de pagamento é obrigatório")
        
        _validate_cpf(cpf_on_invoice)
        
        # Verifica se a loja está aberta
        is_open, message = store_service.is_store_open()
        if not is_open:
            return (None, "STORE_CLOSED", message)

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # ALTERAÇÃO: Processar promoções fornecidas
            promotions_map = {}
            if promotions and isinstance(promotions, list):
                for promo in promotions:
                    product_id = promo.get('product_id')
                    if product_id:
                        promotions_map[product_id] = promo
            
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
            
            # ALTERAÇÃO: Calcula total dos itens aplicando promoções
            subtotal = _calculate_order_total(items, cur, promotions_map=promotions_map)
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

            # Cria o pedido (address_id None para pickup e on-site, table_id só para on-site quando fornecido)
            confirmation_code = _generate_confirmation_code()
            # ALTERAÇÃO: STATUS inicial 'active_table' apenas para pedidos on-site COM mesa vinculada
            initial_status = ORDER_STATUS_ACTIVE_TABLE if (order_type == ORDER_TYPE_ON_SITE and table_id is not None) else 'pending'
            sql_order = """
                INSERT INTO ORDERS (USER_ID, ADDRESS_ID, TABLE_ID, STATUS, TOTAL_AMOUNT, PAYMENT_METHOD, NOTES, CONFIRMATION_CODE, ORDER_TYPE, CHANGE_FOR_AMOUNT)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING ID;
            """
            final_address_id = address_id if order_type == ORDER_TYPE_DELIVERY else None
            final_table_id = table_id if order_type == ORDER_TYPE_ON_SITE else None
            # Calcula o troco: amount_paid - order_total (ou None se não for dinheiro)
            # Garante que todos os valores são float para evitar erro Decimal + float
            order_total_float = float(order_total)
            change_amount = None
            if paid_amount is not None:
                paid_amount_float = float(paid_amount)
                change_amount = paid_amount_float - order_total_float
            cur.execute(sql_order, (user_id, final_address_id, final_table_id, initial_status, order_total_float, payment_method, notes, confirmation_code, order_type, change_amount))
            new_order_id = cur.fetchone()[0]
            
            # ALTERAÇÃO: Vincular pedido à mesa e marcar como ocupada se for on-site e table_id fornecido
            if order_type == ORDER_TYPE_ON_SITE and table_id is not None:
                if not table_service.set_table_occupied(table_id, new_order_id):
                    # Se falhou ao vincular mesa, reverte tudo
                    conn.rollback()
                    logger.error(f"Erro ao vincular pedido {new_order_id} à mesa {table_id}")
                    return (None, "DATABASE_ERROR", "Erro ao vincular pedido à mesa")

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

            # ALTERAÇÃO: Adiciona itens ao pedido aplicando promoções
            _add_order_items(new_order_id, items, cur, promotions_map=promotions_map)
            
            # Deduz estoque quando o pedido é criado (usa cursor existente para manter transação)
            success, error_code, message = stock_service.deduct_stock_for_order(new_order_id, cur)
            if not success:
                # Se falhou a dedução, reverte tudo
                conn.rollback()
                logger.error(f"Erro ao deduzir estoque para pedido {new_order_id}: {message}")
                return (None, error_code, message)
            logger.info(f"Estoque deduzido para pedido {new_order_id}: {message}")
            
            conn.commit()
            
            # Notificação para cozinha
            _notify_kitchen(new_order_id)
            
            # ALTERAÇÃO: Enviar email de confirmação de pedido
            try:
                customer = user_service.get_user_by_id(user_id)
                if customer and customer.get('email'):
                    # Buscar dados completos do pedido para o email
                    order_details = get_order_details(new_order_id, user_id, 'customer')
                    if order_details:
                        email_service.send_email(
                            to=customer['email'],
                            subject=f"Pedido #{new_order_id} confirmado - Royal Burger",
                            template='order_confirmation',
                            user=customer,
                            order=order_details,
                            app_url=Config.APP_URL
                        )
            except Exception as e:
                # Não falha a criação do pedido se houver erro ao enviar email
                logger.warning(f"Erro ao enviar email de confirmação do pedido {new_order_id}: {e}", exc_info=True)
            
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

def get_orders_by_user_id(user_id, page=1, page_size=50):
    """Busca o histórico de pedidos de um usuário específico com otimizações.
    Inclui total_amount e items básicos na mesma query para evitar N+1 queries.
    Suporta paginação opcional."""
    # OTIMIZAÇÃO: Usar validador centralizado de paginação
    from ..utils.validators import validate_pagination_params
    try:
        page, page_size, offset = validate_pagination_params(page, page_size, max_page_size=100)
    except ValueError:
        page, page_size, offset = 1, 50, 0
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Contar total de pedidos do usuário
        cur.execute("SELECT COUNT(*) FROM ORDERS WHERE USER_ID = ?", (user_id,))
        total = cur.fetchone()[0] or 0
        
        # Query otimizada que inclui total_amount e agrega items básicos
        sql = f"""
            SELECT FIRST {page_size} SKIP {offset}
                o.ID, 
                o.STATUS, 
                o.CONFIRMATION_CODE, 
                o.CREATED_AT, 
                o.ORDER_TYPE, 
                o.TOTAL_AMOUNT,
                a.STREET, 
                a."NUMBER"
            FROM ORDERS o
            LEFT JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            WHERE o.USER_ID = ?
            ORDER BY o.CREATED_AT DESC
        """
        cur.execute(sql, (user_id,))
        order_rows = cur.fetchall()
        
        if not order_rows:
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            return {
                "items": [],
                "pagination": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages
                }
            }
        
        # Busca todos os items de todos os pedidos de uma vez (evita N+1)
        order_ids = [row[0] for row in order_rows]
        placeholders = ', '.join(['?' for _ in order_ids])
        sql_items = f"""
            SELECT 
                oi.ORDER_ID,
                oi.QUANTITY,
                p.NAME as PRODUCT_NAME
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE oi.ORDER_ID IN ({placeholders})
            ORDER BY oi.ORDER_ID, oi.ID;
        """
        cur.execute(sql_items, tuple(order_ids))
        items_rows = cur.fetchall()
        
        # Agrupa items por order_id
        items_by_order = {}
        for item_row in items_rows:
            order_id = item_row[0]
            if order_id not in items_by_order:
                items_by_order[order_id] = []
            items_by_order[order_id].append({
                "quantity": item_row[1],
                "product_name": item_row[2],
                "name": item_row[2]  # Alias para compatibilidade
            })
        
        # Monta resposta com items e total
        orders = []
        for row in order_rows:
            order_id = row[0]
            order_type = row[4] if row[4] else ORDER_TYPE_DELIVERY
            
            # Formata endereço como objeto para compatibilidade
            address_obj = None
            if order_type == ORDER_TYPE_PICKUP:
                address_obj = {"street": "Retirada no balcão"}
            elif row[6] and row[7]:  # STREET e NUMBER não nulos
                address_obj = {"street": row[6], "number": row[7]}
            else:
                address_obj = {"street": "Endereço não informado"}
            
            order_data = {
                "order_id": order_id,
                "id": order_id,  # Alias para compatibilidade
                "status": row[1],
                "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S'),
                "order_type": order_type,
                "total_amount": float(row[5]) if row[5] is not None else None,
                "total": float(row[5]) if row[5] is not None else None,  # Alias para compatibilidade
                "address": address_obj,
                "items": items_by_order.get(order_id, [])
            }
            
            orders.append(order_data)
        
        # Retornar com metadados de paginação
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return {
            "items": orders,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }
    except fdb.Error as e:
        logger.error(f"Erro ao buscar pedidos do usuário {user_id}: {e}", exc_info=True)
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

def get_all_orders(page=1, page_size=50, search=None, status=None, channel=None, period=None):
    """Busca todos os pedidos para a visão do administrador com paginação e filtros."""
    # OTIMIZAÇÃO: Validação de parâmetros de paginação usando função utilitária (seção 1.9 e 1.10)
    from ..utils.validators import validate_pagination_params
    try:
        page, page_size, offset = validate_pagination_params(page, page_size, max_page_size=100)
    except ValueError:
        page = 1
        page_size = 50
        offset = 0
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # ALTERAÇÃO: Construir WHERE clause baseado nos filtros
        where_clauses = []
        params = []
        
        # Filtro de busca (código de confirmação ou nome do cliente)
        if search:
            where_clauses.append("(UPPER(o.CONFIRMATION_CODE) LIKE UPPER(?) OR UPPER(u.FULL_NAME) LIKE UPPER(?))")
            search_pattern = f"%{search}%"
            params.append(search_pattern)
            params.append(search_pattern)
        
        # ALTERAÇÃO: Fase Futura - Filtro de status (suporta múltiplos status separados por vírgula)
        if status:
            # ALTERAÇÃO: Verificar se status contém vírgula (múltiplos status)
            if ',' in status:
                # ALTERAÇÃO: Separar status e criar filtro IN
                status_list = [s.strip() for s in status.split(',') if s.strip()]
                if status_list:
                    placeholders = ', '.join(['?' for _ in status_list])
                    where_clauses.append(f"o.STATUS IN ({placeholders})")
                    params.extend(status_list)
            else:
                # ALTERAÇÃO: Status único (comportamento original)
                where_clauses.append("o.STATUS = ?")
                params.append(status)
        
        # Filtro de canal (tipo de pedido)
        if channel:
            # Mapear channel para ORDER_TYPE
            channel_map = {
                'delivery': ORDER_TYPE_DELIVERY,
                'pickup': ORDER_TYPE_PICKUP,
                'on_site': ORDER_TYPE_ON_SITE
            }
            order_type_value = channel_map.get(channel.lower())
            if order_type_value is not None:
                where_clauses.append("o.ORDER_TYPE = ?")
                params.append(order_type_value)
        
        # Filtro de período
        if period:
            now = datetime.now()
            
            if period.lower() == 'today':
                # Desde início do dia de hoje
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                where_clauses.append("o.CREATED_AT >= ?")
                params.append(start_date)
            elif period.lower() == 'week':
                # Últimos 7 dias
                start_date = now - timedelta(days=7)
                where_clauses.append("o.CREATED_AT >= ?")
                params.append(start_date)
            elif period.lower() == 'month':
                # Últimos 30 dias
                start_date = now - timedelta(days=30)
                where_clauses.append("o.CREATED_AT >= ?")
                params.append(start_date)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # OTIMIZAÇÃO: Query com paginação usando FIRST/SKIP do Firebird
        # ALTERAÇÃO: Incluir TOTAL_AMOUNT para permitir cálculos de receita no frontend
        sql = f"""
            SELECT FIRST {page_size} SKIP {offset}
                o.ID, o.STATUS, o.CONFIRMATION_CODE, o.CREATED_AT, o.ORDER_TYPE, o.TOTAL_AMOUNT, u.FULL_NAME, a.STREET, a."NUMBER"
            FROM ORDERS o
            JOIN USERS u ON o.USER_ID = u.ID
            LEFT JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            WHERE {where_sql}
            ORDER BY o.CREATED_AT DESC
        """
        
        cur.execute(sql, tuple(params))
        
        orders = []
        for row in cur.fetchall():
            # CORREÇÃO: Consistência com get_orders_by_user_id - extrair order_type primeiro
            order_type = row[4] if row[4] else ORDER_TYPE_DELIVERY
            address_str = None
            if order_type == ORDER_TYPE_PICKUP:
                address_str = "Retirada no balcão"
            elif row[7] and row[8]:  # STREET e NUMBER não nulos (índices ajustados após adicionar TOTAL_AMOUNT)
                address_str = f"{row[7]}, {row[8]}"
            else:
                address_str = "Endereço não informado"
            
            # ALTERAÇÃO: Incluir total_amount no retorno
            orders.append({
                "id": row[0],  # Adicionado para compatibilidade com frontend
                "order_id": row[0], "status": row[1], "confirmation_code": row[2],
                "created_at": row[3].strftime('%Y-%m-%d %H:%M:%S'),
                "order_type": order_type,
                "total_amount": float(row[5]) if row[5] else 0.0,  # ALTERAÇÃO: Incluir total_amount
                "customer_name": row[6],  # Índice ajustado após adicionar TOTAL_AMOUNT
                "address": address_str
            })
        
        # ALTERAÇÃO: Buscar total para paginação usando os mesmos filtros
        count_where_sql = where_sql
        count_query = f"SELECT COUNT(*) FROM ORDERS o JOIN USERS u ON o.USER_ID = u.ID WHERE {count_where_sql}"
        cur.execute(count_query, tuple(params))
        total = cur.fetchone()[0] or 0
        
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
        
        result = {
            "items": orders,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }
        
        return result
    except fdb.Error as e:
        logger.error(f"Erro ao buscar todos os pedidos: {e}", exc_info=True)
        return {"items": [], "pagination": {"total": 0, "page": page, "page_size": page_size, "total_pages": 0}}
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

        # OTIMIZAÇÃO DE PERFORMANCE: Busca STATUS, ORDER_TYPE e USER_ID em uma única query
        # USER_ID é necessário para notificações e pontos de fidelidade
        cur.execute("SELECT STATUS, ORDER_TYPE, USER_ID FROM ORDERS WHERE ID = ?;", (order_id,))
        order_info = cur.fetchone()
        
        if not order_info:
            logger.error(f"Pedido {order_id} não encontrado")
            return False
        
        current_status, order_type, user_id = order_info
        
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

        # NOTA: Dedução de estoque foi movida para o momento da criação do pedido
        # (create_order e create_order_from_cart) para garantir que o estoque seja
        # reservado imediatamente quando o pedido é criado, não quando é confirmado

        # OTIMIZAÇÃO DE PERFORMANCE: user_id e order_type já foram obtidos na query inicial
        # Para pontos de fidelidade, precisa recalcular subtotal e buscar TOTAL_AMOUNT
        stored_total = None
        
        # OTIMIZAÇÃO: Só busca TOTAL_AMOUNT se realmente precisar (para pontos quando delivered)
        if db_status == 'delivered':
            cur.execute("SELECT TOTAL_AMOUNT FROM ORDERS WHERE ID = ?;", (order_id,))
            total_result = cur.fetchone()
            
            if total_result:
                stored_total = total_result[0]
            
            total_after_discount = float(stored_total) if stored_total else 0.0
            
            # Processa crédito de pontos apenas quando entregue (delivered)
            # Busca configurações para taxa de entrega (já tem cache)
            settings = settings_service.get_all_settings()
            delivery_fee = 0.0
            if order_type == ORDER_TYPE_DELIVERY and settings and settings.get('taxa_entrega'):
                delivery_fee = float(settings.get('taxa_entrega'))
            
            # OTIMIZAÇÃO: Calcula subtotal e extras em uma única query otimizada
            # Para extras e base_modifications, usa DELTA para multiplicar
            try:
                # OTIMIZAÇÃO: Query única que calcula subtotal e extras juntos
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
            except Exception as e:
                logger.error(f"Erro ao calcular subtotal do pedido {order_id}: {e}", exc_info=True)
                # Continua mesmo se houver erro no cálculo

        # ALTERAÇÃO: Registrar receita e CMV quando pedido é finalizado
        # FASE 1: Integrar registro financeiro na mesma transação do status
        # Isso garante consistência: se o registro financeiro falhar, o status não é atualizado
        if db_status == 'delivered':
            # Buscar dados do pedido para registro financeiro
            # ALTERAÇÃO: Buscar antes do commit para usar na mesma transação
            cur.execute("""
                SELECT TOTAL_AMOUNT, PAYMENT_METHOD, CREATED_AT
                FROM ORDERS
                WHERE ID = ?
            """, (order_id,))
            
            order_data = cur.fetchone()
            if order_data:
                order_total, payment_method, order_created_at = order_data
                
                # Registrar receita e CMV na mesma transação
                # ALTERAÇÃO FASE 3: Retorno agora inclui payment_fee_id
                success, revenue_id, cmv_id, payment_fee_id, error = financial_movement_service.register_order_revenue_and_cmv(
                    order_id=order_id,
                    order_total=float(order_total) if order_total else 0.0,
                    payment_method=payment_method or 'unknown',
                    payment_date=order_created_at,  # Usar data de criação do pedido
                    created_by_user_id=None,  # Sistema registra automaticamente (pode ser melhorado para rastrear usuário)
                    cur=cur  # ALTERAÇÃO: Passar cursor para mesma transação
                )
                
                if not success:
                    # ALTERAÇÃO: Se falhar, fazer rollback completo
                    conn.rollback()
                    logger.error(f"Erro ao registrar receita/CMV para pedido {order_id}: {error}")
                    return False
                
                logger.info(f"Receita, CMV e taxa registrados para pedido {order_id}: revenue_id={revenue_id}, cmv_id={cmv_id}, payment_fee_id={payment_fee_id}")
        
        # Commit único de tudo (status + movimentações financeiras)
        conn.commit()
        
        # OTIMIZAÇÃO DE PERFORMANCE: Envia notificações de forma assíncrona (não bloqueia resposta)
        # user_id já foi obtido na query inicial, então pode ser usado diretamente
        
        # ALTERAÇÃO: Envia notificação após commit bem-sucedido (não bloqueia se falhar)
        # Respeita preferências de notificação do usuário
        if user_id:
            try:
                # Para pickup com status ready ou in_progress (fallback), mensagem personalizada
                if (db_status == 'ready' or db_status == 'in_progress') and order_type == ORDER_TYPE_PICKUP:
                    notification_message = f"Seu pedido #{order_id} está pronto para retirada no balcão!"
                    notification_link = f"/my-orders/{order_id}"
                    notification_service.create_notification(user_id, notification_message, notification_link, notification_type='order')
                elif db_status != 'delivered':  # Para delivered, notificação já foi enviada em outro lugar
                    # ALTERAÇÃO: Usar db_status para mensagem consistente
                    status_messages = {
                        'pending': 'Aguardando Confirmação',
                        'in_progress': 'Em Andamento',
                        'awaiting_payment': 'Aguardando Pagamento',
                        'preparing': 'Em Preparação',
                        'ready': 'Pronto',
                        'on_the_way': 'A Caminho',
                        'cancelled': 'Cancelado'
                    }
                    status_text = status_messages.get(db_status, db_status)
                    notification_message = f"O status do seu pedido #{order_id} foi atualizado para {status_text}"
                    notification_link = f"/my-orders/{order_id}"
                    notification_service.create_notification(user_id, notification_message, notification_link, notification_type='order')
            except Exception as e:
                logger.error(f"Erro ao enviar notificação para pedido {order_id}: {e}", exc_info=True)
                # Não falha a operação por erro na notificação
        
        # OTIMIZAÇÃO DE PERFORMANCE: Envia email de forma assíncrona (não bloqueia resposta)
        # Email é enviado em background para não impactar tempo de resposta
        if user_id:
            try:
                customer = user_service.get_user_by_id(user_id)
                if customer:
                    # ALTERAÇÃO: Usar db_status em vez de new_status para garantir tradução correta
                    # db_status é o status que foi salvo no banco (já mapeado corretamente)
                    email_service.send_email(
                        to=customer['email'],
                        subject=f"Atualização sobre seu pedido #{order_id}",
                        template='order_status_update',
                        user=customer,
                        order={"order_id": order_id},
                        new_status=db_status,  # Usar db_status que é o status salvo no banco
                        app_url=Config.APP_URL
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
            SELECT o.ID, o.USER_ID, o.ADDRESS_ID, o.STATUS, o.CONFIRMATION_CODE, o.NOTES,
                   o.PAYMENT_METHOD, o.TOTAL_AMOUNT, o.CREATED_AT, o.ORDER_TYPE, o.CHANGE_FOR_AMOUNT,
                   u.FULL_NAME
            FROM ORDERS o
            LEFT JOIN USERS u ON o.USER_ID = u.ID
            WHERE o.ID = ?;
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
            "amount_paid": amount_paid,
            "customer_name": order_row[11] if order_row[11] else None
        }

        # Verificação de segurança: cliente só pode ver seus próprios pedidos
        if user_role == 'customer' and order_details['user_id'] != user_id:
            return None 

        # CORREÇÃO: Evitar query N+1 - buscar todos os extras de uma vez
        # Primeiro busca todos os itens
        # ALTERAÇÃO: Incluir COST_PRICE do produto para cálculo de CMV
        # Inclui PRODUCT_ID, imagem e tempo de preparo do produto para evitar roundtrips no frontend
        sql_items = """
            SELECT
                oi.ID,
                oi.QUANTITY,
                oi.UNIT_PRICE,
                p.NAME,
                p.DESCRIPTION,
                oi.PRODUCT_ID,
                p.IMAGE_URL,
                NULL AS IMAGE_HASH, -- REVISAR: adicionar coluna real se existir
                p.PREPARATION_TIME_MINUTES,
                COALESCE(p.COST_PRICE, 0) as COST_PRICE
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.PRODUCT_ID = p.ID
            WHERE oi.ORDER_ID = ?;
        """
        cur.execute(sql_items, (order_id,))
        item_rows = cur.fetchall()
        
        if not item_rows:
            order_details['items'] = []
            return order_details
        
        # ALTERAÇÃO: Validação de lista vazia para prevenir SQL inválido
        # Busca todos os extras de uma vez (evita N+1)
        order_item_ids = [row[0] for row in item_rows]
        
        # ALTERAÇÃO: Validação de tipos para prevenir SQL injection (já estava seguro, mas melhorado)
        # Validar que todos os IDs são números inteiros antes de executar query
        validated_ids = []
        for item_id in order_item_ids:
            try:
                validated_id = int(item_id)
                if validated_id > 0:
                    validated_ids.append(validated_id)
            except (ValueError, TypeError):
                # Ignorar IDs inválidos (não devem acontecer, mas prevenir é melhor)
                continue
        
        # ALTERAÇÃO: Importar função de cálculo de CMV antes de usar
        try:
            from .financial_movement_service import _calculate_cost_per_base_portion
        except ImportError:
            # Fallback se não conseguir importar
            def _calculate_cost_per_base_portion(price, stock_unit, base_portion_quantity, base_portion_unit):
                if not price or price <= 0:
                    return 0.0
                stock_unit = str(stock_unit or 'un').strip().lower()
                base_portion_unit = str(base_portion_unit or 'un').strip().lower()
                if stock_unit == base_portion_unit or stock_unit == 'un' or base_portion_unit == 'un':
                    return float(price) * float(base_portion_quantity or 1.0)
                # Conversão simplificada (kg->g, L->ml)
                conversion_factors = {'kg': {'g': 1000}, 'l': {'ml': 1000}, 'litro': {'ml': 1000}}
                factor = 1
                if conversion_factors.get(stock_unit) and conversion_factors[stock_unit].get(base_portion_unit):
                    factor = conversion_factors[stock_unit][base_portion_unit]
                elif conversion_factors.get(base_portion_unit) and conversion_factors[base_portion_unit].get(stock_unit):
                    factor = 1 / conversion_factors[base_portion_unit][stock_unit]
                return (float(price) / factor) * float(base_portion_quantity or 1.0)
        
        # ALTERAÇÃO: Inicializar extras_dict vazio e só popular se houver IDs válidos
        # Se não há IDs válidos, os itens ainda serão processados abaixo, mas sem extras
        extras_dict = {}
        
        # ALTERAÇÃO: Só executar query se houver IDs válidos
        # ALTERAÇÃO: Incluir dados do ingrediente para cálculo de custo unitário
        if validated_ids:
            placeholders = ', '.join(['?' for _ in validated_ids])
            sql_extras = f"""
                SELECT e.ORDER_ITEM_ID, e.INGREDIENT_ID, i.NAME, e.QUANTITY, e.TYPE, COALESCE(e.DELTA, e.QUANTITY) as DELTA,
                       COALESCE(i.PRICE, 0) as PRICE, i.STOCK_UNIT, i.BASE_PORTION_QUANTITY, i.BASE_PORTION_UNIT
                FROM ORDER_ITEM_EXTRAS e
                JOIN INGREDIENTS i ON i.ID = e.INGREDIENT_ID
                WHERE e.ORDER_ITEM_ID IN ({placeholders})
                ORDER BY e.ORDER_ITEM_ID, e.TYPE, i.NAME
            """
            cur.execute(sql_extras, tuple(validated_ids))
            # Processar resultados dos extras
            for ex in cur.fetchall():
                order_item_id = ex[0]
                if order_item_id not in extras_dict:
                    extras_dict[order_item_id] = {'extras': [], 'base_modifications': []}
                row_type = (ex[4] or 'extra').lower()
                
                # ALTERAÇÃO: Calcular custo unitário do insumo
                ingredient_price = float(ex[6]) if ex[6] is not None else 0.0
                stock_unit = ex[7] or 'un'
                base_portion_quantity = float(ex[8] or 1) if ex[8] is not None else 1.0
                base_portion_unit = ex[9] or 'un'
                
                # Calcular custo por porção base
                try:
                    cost_per_base_portion = _calculate_cost_per_base_portion(
                        ingredient_price,
                        stock_unit,
                        base_portion_quantity,
                        base_portion_unit
                    )
                except:
                    cost_per_base_portion = 0.0
                
                if row_type == 'extra':
                    extras_dict[order_item_id]['extras'].append({
                        "ingredient_id": ex[1],
                        "name": ex[2],
                        "quantity": ex[3],
                        "unit_cost": cost_per_base_portion,  # ALTERAÇÃO: Custo unitário do insumo
                        "price": ingredient_price,
                        "stock_unit": stock_unit,
                        "base_portion_quantity": base_portion_quantity,
                        "base_portion_unit": base_portion_unit
                    })
                elif row_type == 'base':
                    # ALTERAÇÃO: Validação de delta para prevenir erros
                    try:
                        delta_value = int(ex[5]) if ex[5] is not None else 0
                        # Validar que delta é um número válido
                        if not isinstance(delta_value, int):
                            delta_value = 0
                    except (ValueError, TypeError):
                        delta_value = 0
                    
                    extras_dict[order_item_id]['base_modifications'].append({
                        "ingredient_id": ex[1],
                        "name": ex[2],
                        "delta": delta_value,
                        "unit_cost": cost_per_base_portion,  # ALTERAÇÃO: Custo unitário do insumo
                        "price": ingredient_price,
                        "stock_unit": stock_unit,
                        "base_portion_quantity": base_portion_quantity,
                        "base_portion_unit": base_portion_unit
                    })

        # Monta lista de itens com seus extras
        order_items = []
        for item_row in item_rows:
            order_item_id = item_row[0]
            cost_price = float(item_row[9]) if item_row[9] is not None else 0.0
            
            # ALTERAÇÃO: Calcular CMV do item incluindo extras e modificações
            item_cmv = cost_price * item_row[1]  # Custo base do produto
            
            # Calcular custo dos extras
            item_extras = extras_dict.get(order_item_id, {}).get('extras', [])
            for extra in item_extras:
                if extra.get('ingredient_id'):
                    try:
                        # Buscar dados do ingrediente
                        cur.execute("""
                            SELECT PRICE, STOCK_UNIT, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT
                            FROM INGREDIENTS
                            WHERE ID = ?
                        """, (extra['ingredient_id'],))
                        ing_row = cur.fetchone()
                        if ing_row and ing_row[0]:
                            extra_price = float(ing_row[0])
                            stock_unit = ing_row[1] or 'un'
                            base_portion_quantity = float(ing_row[2] or 1)
                            base_portion_unit = ing_row[3] or 'un'
                            extra_quantity = extra.get('quantity', 1)
                            
                            # Calcular custo por porção base
                            cost_per_base_portion = _calculate_cost_per_base_portion(
                                extra_price,
                                stock_unit,
                                base_portion_quantity,
                                base_portion_unit
                            )
                            
                            # Adicionar ao CMV
                            item_cmv += cost_per_base_portion * extra_quantity
                    except Exception as e:
                        logger.warning(f"Erro ao calcular custo de extra {extra.get('ingredient_id')}: {e}")
            
            # Calcular custo das modificações de base
            item_base_mods = extras_dict.get(order_item_id, {}).get('base_modifications', [])
            for mod in item_base_mods:
                if mod.get('ingredient_id') and mod.get('delta', 0) > 0:
                    try:
                        # Buscar dados do ingrediente
                        cur.execute("""
                            SELECT PRICE, STOCK_UNIT, BASE_PORTION_QUANTITY, BASE_PORTION_UNIT
                            FROM INGREDIENTS
                            WHERE ID = ?
                        """, (mod['ingredient_id'],))
                        ing_row = cur.fetchone()
                        if ing_row and ing_row[0]:
                            mod_price = float(ing_row[0])
                            stock_unit = ing_row[1] or 'un'
                            base_portion_quantity = float(ing_row[2] or 1)
                            base_portion_unit = ing_row[3] or 'un'
                            delta = mod.get('delta', 0)
                            
                            # Calcular custo por porção base
                            cost_per_base_portion = _calculate_cost_per_base_portion(
                                mod_price,
                                stock_unit,
                                base_portion_quantity,
                                base_portion_unit
                            )
                            
                            # Adicionar ao CMV
                            item_cmv += cost_per_base_portion * delta
                    except Exception as e:
                        logger.warning(f"Erro ao calcular custo de modificação {mod.get('ingredient_id')}: {e}")
            
            item_dict = {
                "quantity": item_row[1],
                "unit_price": item_row[2],
                "product_name": item_row[3],
                "product_description": item_row[4],
                "product_id": item_row[5],                 # adicionado
                "product_image_url": item_row[6],          # adicionado
                "product_image_hash": item_row[7],         # adicionado (pode ser None)
                "cost_price": cost_price,                 # ALTERAÇÃO: Incluir cost_price
                "unit_cost": cost_price,                   # ALTERAÇÃO: Custo unitário do produto
                "total_cost": item_cmv,                    # ALTERAÇÃO: CMV total do item (produto + extras + mods)
                "product": {
                    "id": item_row[5],
                    "name": item_row[3],
                    "description": item_row[4],
                    "image_url": item_row[6],
                    "image_hash": item_row[7],
                    "preparation_time_minutes": int(item_row[8]) if item_row[8] else 0,  # Tempo de preparo do produto
                    "cost_price": cost_price               # ALTERAÇÃO: Incluir cost_price no objeto product
                },
                "extras": item_extras,
                "base_modifications": item_base_mods
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

        # NOVA LÓGICA: Salvar status anterior e devolver estoque
        # Salva o status atual em PREVIOUS_STATUS antes de cancelar
        sql_update = """
            UPDATE ORDERS 
            SET STATUS = 'cancelled', 
                PREVIOUS_STATUS = ?,
                UPDATED_AT = CURRENT_TIMESTAMP 
            WHERE ID = ?;
        """
        cur.execute(sql_update, (status, order_id))
        
        # Devolve o estoque dos ingredientes do pedido cancelado
        try:
            success, error_code, message = stock_service.restock_for_order(order_id, cur)
            if not success:
                logger.warning(f"Erro ao devolver estoque para pedido {order_id}: {message}")
                # Não bloqueia o cancelamento se falhar a devolução de estoque
                # Mas loga o erro para investigação
        except Exception as e:
            logger.error(f"Erro ao devolver estoque para pedido {order_id}: {e}", exc_info=True)
            # Não bloqueia o cancelamento
        
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
            # ALTERAÇÃO: Passa notification_type='order' para respeitar preferências
            notification_service.create_notification(target_user_id, message, link, notification_type='order')

            customer = user_service.get_user_by_id(target_user_id)
            if customer:
                email_service.send_email(
                    to=customer['email'],
                    subject=f"Seu pedido #{order_id} foi cancelado",
                    template='order_status_update', 
                    user=customer,
                    order={"order_id": order_id},
                    new_status='cancelled',
                    app_url=Config.APP_URL
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


def uncancel_order(order_id, user_id):
    """
    Reverte o cancelamento de um pedido, restaurando-o ao status anterior.
    Apenas gerentes/admins podem executar esta ação.
    
    Regras:
    - Apenas Gerente/Admin pode executar
    - Só funciona se o status atual for 'cancelled'
    - Precisa ter um PREVIOUS_STATUS salvo (ou assume 'confirmed' como fallback)
    - Deduz estoque novamente (pois foi devolvido no cancelamento)
    - Se não houver estoque suficiente, a reversão falha
    
    Args:
        order_id: ID do pedido
        user_id: ID do usuário que está revertendo (deve ser gerente/admin)
    
    Returns:
        Tupla (sucesso, mensagem).
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Busca informações do pedido
        sql_find = "SELECT USER_ID, STATUS, PREVIOUS_STATUS, ORDER_TYPE FROM ORDERS WHERE ID = ?;"
        cur.execute(sql_find, (order_id,))
        order_record = cur.fetchone()

        if not order_record:
            return (False, "Pedido não encontrado.")

        owner_id, current_status, previous_status, order_type = order_record

        # Verifica se o pedido está cancelado
        if current_status != 'cancelled':
            return (False, f"Não é possível reverter cancelamento de um pedido com status '{current_status}'. Apenas pedidos cancelados podem ser revertidos.")

        # Determina o status a ser restaurado
        # Se PREVIOUS_STATUS for NULL, assume 'confirmed' como fallback
        status_to_restore = previous_status if previous_status else 'confirmed'
        
        # Valida se o status a restaurar é válido
        valid_statuses = ['pending', 'confirmed', 'preparing', 'ready', 'on_the_way', 'in_progress']
        if status_to_restore not in valid_statuses:
            logger.warning(f"Status anterior inválido '{status_to_restore}' para pedido {order_id}, usando 'confirmed'")
            status_to_restore = 'confirmed'

        # Deduz estoque novamente (pois foi devolvido no cancelamento)
        try:
            success, error_code, message = stock_service.deduct_stock_for_order(order_id, cur)
            if not success:
                # Se não houver estoque suficiente, a reversão falha
                if error_code == "VALIDATION_ERROR":
                    return (False, f"Não é possível reverter o cancelamento: {message}")
                else:
                    return (False, f"Erro ao deduzir estoque: {message}")
        except Exception as e:
            logger.error(f"Erro ao deduzir estoque para pedido {order_id} na reversão: {e}", exc_info=True)
            return (False, "Erro ao deduzir estoque. Não foi possível reverter o cancelamento.")

        # Restaura o status anterior e limpa PREVIOUS_STATUS
        sql_update = """
            UPDATE ORDERS 
            SET STATUS = ?,
                PREVIOUS_STATUS = NULL,
                UPDATED_AT = CURRENT_TIMESTAMP 
            WHERE ID = ?;
        """
        cur.execute(sql_update, (status_to_restore, order_id))
        
        # Se for pedido on-site, vincula novamente à mesa se necessário
        if order_type == ORDER_TYPE_ON_SITE:
            cur.execute("SELECT TABLE_ID FROM ORDERS WHERE ID = ?;", (order_id,))
            table_result = cur.fetchone()
            if table_result and table_result[0]:
                table_id = table_result[0]
                # Tenta ocupar a mesa novamente (pode falhar se mesa estiver ocupada)
                try:
                    table_service.set_table_occupied(table_id, order_id)
                except Exception as e:
                    logger.warning(f"Erro ao vincular mesa {table_id} ao pedido {order_id} na reversão: {e}")
                    # Não bloqueia a reversão se falhar ao vincular mesa
        
        conn.commit()

        # Envia notificações de reversão
        try:
            message = f"O cancelamento do pedido #{order_id} foi revertido. Status restaurado: {status_to_restore}."
            link = f"/my-orders/{order_id}"
            notification_service.create_notification(owner_id, message, link, notification_type='order')

            customer = user_service.get_user_by_id(owner_id)
            if customer:
                email_service.send_email(
                    to=customer['email'],
                    subject=f"Cancelamento do pedido #{order_id} foi revertido",
                    template='order_status_update', 
                    user=customer,
                    order={"order_id": order_id},
                    new_status=status_to_restore,
                    app_url=Config.APP_URL
                )
        except Exception as e:
            logger.warning(f"Falha ao enviar notificação de reversão para o pedido {order_id}: {e}", exc_info=True)

        return (True, f"Cancelamento do pedido #{order_id} revertido com sucesso. Status restaurado: {status_to_restore}.")

    except fdb.Error as e:
        logger.error(f"Erro ao reverter cancelamento do pedido {order_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return (False, "Ocorreu um erro interno ao tentar reverter o cancelamento do pedido.")
    finally:
        if conn:
            conn.close()


def create_order_from_cart(user_id, address_id, payment_method, amount_paid=None, notes="", cpf_on_invoice=None, points_to_redeem=0, order_type=ORDER_TYPE_DELIVERY, promotions=None, table_id=None):
    """
    Fluxo 4: Finalização (Converter Carrinho em Pedido)
    Cria um pedido a partir do carrinho do usuário
    ALTERAÇÃO: Agora aceita promotions para aplicar descontos
    ALTERAÇÃO: Agora aceita table_id para pedidos on-site
    """
    conn = None
    try:
        # Valida order_type
        _validate_order_type(order_type)
        
        # ALTERAÇÃO: Validação de mesa para pedidos on-site (opcional)
        if order_type == ORDER_TYPE_ON_SITE:
            # Se table_id foi fornecido, valida que está correto e disponível
            if table_id is not None:
                if not isinstance(table_id, int) or table_id <= 0:
                    return (None, "VALIDATION_ERROR", "table_id deve ser um número inteiro válido")
                # Verifica se a mesa existe e está disponível
                if not table_service.is_table_available(table_id):
                    table_info = table_service.get_table_by_id(table_id)
                    if not table_info:
                        return (None, "TABLE_NOT_FOUND", "Mesa não encontrada")
                    return (None, "TABLE_NOT_AVAILABLE", f"Mesa {table_info.get('name', table_id)} não está disponível")
        elif table_id is not None:
            # Se table_id foi fornecido mas order_type não é on_site, rejeitar
            return (None, "VALIDATION_ERROR", "table_id só pode ser fornecido para pedidos on-site")
        
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
        
        # ALTERAÇÃO: Processar promoções fornecidas
        promotions_map = {}
        if promotions and isinstance(promotions, list):
            for promo in promotions:
                product_id = promo.get('product_id')
                if product_id:
                    promotions_map[product_id] = promo
        
        # VALIDAÇÃO DE ESTOQUE - antes de criar o pedido
        # ALTERAÇÃO: Passa cart_id para excluir reservas temporárias do próprio carrinho na validação
        # Isso evita conflito quando há exatamente a quantidade necessária em estoque
        cart_id = cart_data.get("cart_id")
        stock_valid, stock_error_code, stock_error_message = stock_service.validate_stock_for_items(cart_data["items"], cur, cart_id=cart_id)
        if not stock_valid:
            return (None, stock_error_code, stock_error_message)
        
        # Validações básicas
        if cpf_on_invoice and not validators.is_valid_cpf(cpf_on_invoice):
            return (None, "INVALID_CPF", f"O CPF informado '{cpf_on_invoice}' é inválido.")
        
        # Verifica endereço apenas se for delivery (evita query desnecessária para pickup e on-site)
        if order_type == ORDER_TYPE_DELIVERY:
            if not address_id:
                return (None, "INVALID_ADDRESS", "address_id é obrigatório para pedidos de entrega")
            cur.execute("SELECT ID FROM ADDRESSES WHERE ID = ? AND USER_ID = ? AND IS_ACTIVE = TRUE;", (address_id, user_id))
            if not cur.fetchone():
                return (None, "INVALID_ADDRESS", "Endereço não encontrado ou não pertence ao usuário.")
        elif order_type == ORDER_TYPE_ON_SITE:
            # Para pedidos on-site, address_id deve ser None
            if address_id is not None:
                return (None, "VALIDATION_ERROR", "address_id deve ser None para pedidos on-site")
        
        # Gera código de confirmação
        confirmation_code = _generate_confirmation_code()
        
        # Busca configurações uma única vez
        settings = settings_service.get_all_settings()
        if not settings:
            settings = {}
        
        # ALTERAÇÃO: Buscar preços dos produtos ANTES de calcular totais
        cart_product_ids = {it["product_id"] for it in cart_data["items"]}
        product_prices = {}
        if cart_product_ids:
            placeholders = ', '.join(['?' for _ in cart_product_ids])
            cur.execute(f"SELECT ID, PRICE FROM PRODUCTS WHERE ID IN ({placeholders});", tuple(cart_product_ids))
            product_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        # ALTERAÇÃO: Buscar preços de extras e base_modifications ANTES de calcular totais
        extra_ids = set()
        base_mod_ids = set()
        for it in cart_data["items"]:
            for ex in it.get("extras", []):
                ex_id = ex.get("ingredient_id")
                if ex_id:
                    extra_ids.add(ex_id)
            for bm in it.get("base_modifications", []):
                bm_id = bm.get("ingredient_id")
                if bm_id:
                    base_mod_ids.add(bm_id)
        
        extra_prices = {}
        if extra_ids:
            placeholders = ', '.join(['?' for _ in extra_ids])
            cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE, 0) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(extra_ids))
            extra_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        base_mod_prices = {}
        if base_mod_ids:
            placeholders = ', '.join(['?' for _ in base_mod_ids])
            cur.execute(f"SELECT ID, COALESCE(ADDITIONAL_PRICE, PRICE) FROM INGREDIENTS WHERE ID IN ({placeholders});", tuple(base_mod_ids))
            base_mod_prices = {row[0]: float(row[1] or 0) for row in cur.fetchall()}
        
        # ALTERAÇÃO: Recalcular total do carrinho aplicando promoções fornecidas
        # Se promoções foram fornecidas, recalcular subtotal considerando descontos
        # Caso contrário, usar o total do carrinho (que já tem promoções aplicadas se houver)
        if promotions_map:
            # Recalcular subtotal aplicando promoções fornecidas
            subtotal = 0.0
            for item in cart_data["items"]:
                product_id = item["product_id"]
                original_price = float(product_prices.get(product_id, 0.0))
                
                # Aplicar promoção se fornecida
                if product_id in promotions_map:
                    promotion = promotions_map[product_id]
                    price_with_promo, _, _ = _apply_promotion_to_price(original_price, promotion)
                else:
                    price_with_promo = original_price
                
                quantity = item.get("quantity", 1)
                extras_total = sum(
                    float(extra_prices.get(ex.get("ingredient_id", 0), 0.0)) * int(ex.get("quantity", 0))
                    for ex in item.get("extras", [])
                )
                base_mods_total = sum(
                    float(base_mod_prices.get(bm.get("ingredient_id", 0), 0.0)) * abs(int(bm.get("delta", 0)))
                    for bm in item.get("base_modifications", [])
                )
                
                item_subtotal = (price_with_promo * quantity) + extras_total + (base_mods_total * quantity)
                subtotal += item_subtotal
            
            total_amount = float(subtotal)
        else:
            # Usar total do carrinho (já tem promoções aplicadas se houver)
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
        
        # Cria o pedido (address_id None para pickup e on-site, table_id só para on-site quando fornecido)
        # ALTERAÇÃO: STATUS inicial 'active_table' apenas para pedidos on-site COM mesa vinculada
        initial_status = ORDER_STATUS_ACTIVE_TABLE if (order_type == ORDER_TYPE_ON_SITE and table_id is not None) else 'pending'
        sql_order = """
            INSERT INTO ORDERS (USER_ID, ADDRESS_ID, TABLE_ID, STATUS, TOTAL_AMOUNT, PAYMENT_METHOD, 
                                NOTES, CONFIRMATION_CODE, ORDER_TYPE, CHANGE_FOR_AMOUNT)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING ID;
        """
        final_address_id = address_id if order_type == ORDER_TYPE_DELIVERY else None
        final_table_id = table_id if order_type == ORDER_TYPE_ON_SITE else None
        # Calcula o troco: amount_paid - total_with_delivery (ou None se não for dinheiro)
        # Garante que todos os valores são float
        total_with_delivery_float = float(total_with_delivery)
        change_amount = None
        if paid_amount is not None:
            paid_amount_float = float(paid_amount)
            change_amount = paid_amount_float - total_with_delivery_float
        cur.execute(sql_order, (user_id, final_address_id, final_table_id, initial_status, total_with_delivery_float, payment_method, notes, confirmation_code, order_type, change_amount))
        order_id = cur.fetchone()[0]
        
        # ALTERAÇÃO: Vincular pedido à mesa e marcar como ocupada se for on-site e table_id fornecido
        if order_type == ORDER_TYPE_ON_SITE and table_id is not None:
            if not table_service.set_table_occupied(table_id, order_id):
                # Se falhou ao vincular mesa, reverte tudo
                conn.rollback()
                logger.error(f"Erro ao vincular pedido {order_id} à mesa {table_id}")
                return (None, "DATABASE_ERROR", "Erro ao vincular pedido à mesa")

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
        
        # ALTERAÇÃO: Preços já foram buscados acima, apenas log para debug
        logger.info(f"[create_order_from_cart] Preços de extras carregados: {len(extra_prices)} preços de {len(extra_ids)} ingredientes")

        # DEBUG: Log detalhado dos itens do carrinho
        logger.info(f"[create_order_from_cart] Processando {len(cart_data['items'])} itens do carrinho")
        for idx, item_debug in enumerate(cart_data["items"]):
            logger.info(f"[create_order_from_cart] Item {idx}: product_id={item_debug.get('product_id')}, "
                        f"quantity={item_debug.get('quantity')}, "
                        f"extras_count={len(item_debug.get('extras', []))}, "
                        f"extras={item_debug.get('extras', [])}, "
                        f"base_modifications_count={len(item_debug.get('base_modifications', []))}")
        
        # ALTERAÇÃO: Copia itens do carrinho para o pedido (com preços e promoções aplicadas)
        for item in cart_data["items"]:
            product_id = item["product_id"]
            quantity = item["quantity"]
            # CORREÇÃO: Valida se produto existe antes de inserir
            original_price = product_prices.get(product_id)
            if original_price is None:
                raise ValueError(f"Produto {product_id} não encontrado ou preço indisponível")

            # ALTERAÇÃO: Aplicar promoção ao preço antes de salvar
            if promotions_map and product_id in promotions_map:
                promotion = promotions_map[product_id]
                unit_price_float, _, _ = _apply_promotion_to_price(original_price, promotion)
            else:
                # ALTERAÇÃO: Buscar promoção ativa se não fornecida
                promotion = promotion_service.get_promotion_by_product_id(product_id, include_expired=False)
                unit_price_float, _, _ = _apply_promotion_to_price(original_price, promotion)
            
            # Garante que unit_price é float
            unit_price_float = float(unit_price_float)
            
            sql_item = """
                INSERT INTO ORDER_ITEMS (ORDER_ID, PRODUCT_ID, QUANTITY, UNIT_PRICE)
                VALUES (?, ?, ?, ?) RETURNING ID;
            """
            cur.execute(sql_item, (order_id, product_id, quantity, unit_price_float))
            order_item_id = cur.fetchone()[0]

            # Insere extras do item (TYPE='extra')
            extras_to_insert = item.get("extras", [])
            logger.info(f"[create_order_from_cart] Item {order_item_id} (product_id={product_id}) tem {len(extras_to_insert)} extras: {extras_to_insert}")
            
            if not extras_to_insert:
                logger.warning(f"[create_order_from_cart] ATENÇÃO: Item {order_item_id} (product_id={product_id}) não tem extras!")
            
            for extra in extras_to_insert:
                ex_id = extra.get("ingredient_id")
                ex_qty = int(extra.get("quantity", 1))
                
                # Validações
                if not ex_id:
                    logger.warning(f"[create_order_from_cart] Extra sem ingredient_id: {extra}")
                    continue
                
                # IMPORTANTE: Não insere extras com quantidade 0 ou negativa
                if ex_qty <= 0:
                    logger.warning(f"[create_order_from_cart] Pulando extra com quantidade inválida: ingredient_id={ex_id}, quantity={ex_qty}")
                    continue
                
                # CORREÇÃO: Valida se ingrediente existe e tem preço
                ex_price = extra_prices.get(ex_id)
                if ex_price is None:
                    # Tenta buscar preço diretamente do banco se não estiver no cache
                    cur.execute(
                        "SELECT COALESCE(ADDITIONAL_PRICE, PRICE, 0) FROM INGREDIENTS WHERE ID = ?",
                        (ex_id,)
                    )
                    price_row = cur.fetchone()
                    if price_row:
                        ex_price = float(price_row[0] or 0.0)
                        extra_prices[ex_id] = ex_price  # Adiciona ao cache
                        logger.info(f"[create_order_from_cart] Preço do extra {ex_id} buscado diretamente: {ex_price}")
                    else:
                        logger.error(f"[create_order_from_cart] Ingrediente {ex_id} não encontrado no banco de dados")
                        raise ValueError(f"Ingrediente {ex_id} não encontrado ou preço indisponível")
                
                # Garante que o preço é float
                ex_price_float = float(ex_price)
                
                logger.info(f"[create_order_from_cart] Inserindo extra: order_item_id={order_item_id}, ingredient_id={ex_id}, quantity={ex_qty}, price={ex_price_float}")
                
                try:
                    sql_extra = """
                        INSERT INTO ORDER_ITEM_EXTRAS (ORDER_ITEM_ID, INGREDIENT_ID, QUANTITY, TYPE, DELTA, UNIT_PRICE)
                        VALUES (?, ?, ?, 'extra', ?, ?);
                    """
                    cur.execute(sql_extra, (order_item_id, ex_id, ex_qty, ex_qty, ex_price_float))
                    logger.info(f"[create_order_from_cart] Extra inserido com sucesso: ingredient_id={ex_id}")
                except Exception as e:
                    logger.error(f"[create_order_from_cart] Erro ao inserir extra {ex_id}: {e}", exc_info=True)
                    raise
            
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
        
        # Deduz estoque quando o pedido é criado (usa cursor existente para manter transação)
        success, error_code, message = stock_service.deduct_stock_for_order(order_id, cur)
        if not success:
            # Se falhou a dedução, reverte tudo (reservas temporárias permanecem no carrinho)
            conn.rollback()
            logger.error(f"Erro ao deduzir estoque para pedido {order_id}: {message}")
            return (None, error_code, message)
        logger.info(f"Estoque deduzido para pedido {order_id}: {message}")
        
        # INTEGRAÇÃO: Limpa reservas temporárias APÓS dedução bem-sucedida do estoque
        # As reservas temporárias são convertidas em dedução permanente do estoque
        # Portanto, devem ser removidas para evitar dupla dedução
        cart_id = cart_data.get("cart_id")
        if cart_id:
            # ALTERAÇÃO: Limpa reservas expiradas primeiro para liberar estoque
            # Depois limpa reservas temporárias do carrinho específico
            try:
                # Limpa reservas expiradas primeiro (otimização)
                cur.execute("""
                    DELETE FROM TEMPORARY_RESERVATIONS
                    WHERE EXPIRES_AT <= CURRENT_TIMESTAMP
                """)
                expired_count = cur.rowcount
                if expired_count > 0:
                    logger.info(f"Reservas temporárias expiradas limpas: {expired_count} reservas removidas")
                
                # Limpa reservas temporárias do carrinho (convertidas em dedução permanente)
                cur.execute("""
                    DELETE FROM TEMPORARY_RESERVATIONS
                    WHERE CART_ID = ?
                """, (cart_id,))
                reservations_cleared = cur.rowcount
                if reservations_cleared > 0:
                    logger.info(f"Reservas temporárias limpas para carrinho {cart_id}: {reservations_cleared} reservas removidas após checkout")
                elif expired_count == 0:
                    logger.debug(f"Nenhuma reserva temporária encontrada para carrinho {cart_id}")
            except fdb.Error as e:
                # ALTERAÇÃO: Se falhar ao limpar reservas, loga erro mas não falha o pedido
                # (o estoque já foi deduzido, então o pedido deve ser criado mesmo assim)
                # Não expõe detalhes do erro ao cliente, apenas loga internamente
                error_msg = str(e).lower()
                logger.error(
                    f"Erro ao limpar reservas temporárias para carrinho {cart_id}: "
                    f"Tabela: TEMPORARY_RESERVATIONS, Erro: {error_msg[:100]}",
                    exc_info=True
                )
                # Nota: Não faz rollback aqui porque o estoque já foi deduzido com sucesso
                # As reservas serão limpas automaticamente quando expirarem ou podem ser limpas manualmente
        else:
            logger.warning(f"cart_id não encontrado em cart_data ao limpar reservas temporárias para pedido {order_id}")
        
        # Limpa o carrinho do usuário
        if cart_id:
            cur.execute("DELETE FROM CART_ITEMS WHERE CART_ID = ?;", (cart_id,))
            logger.info(f"Carrinho {cart_id} limpo após criação do pedido {order_id}")
        else:
            logger.warning(f"cart_id não encontrado, não foi possível limpar carrinho para pedido {order_id}")
        
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
        
        # ALTERAÇÃO: Envia notificação e email de confirmação
        try:
            notification_service.send_order_confirmation(user_id, order_data)
        except Exception as e:
            logger.error(f"Falha ao enviar notificação de confirmação do pedido {order_id}: {e}", exc_info=True)
        
        # ALTERAÇÃO: Enviar email de confirmação de pedido
        try:
            customer = user_service.get_user_by_id(user_id)
            if customer and customer.get('email') and order_data:
                email_service.send_email(
                    to=customer['email'],
                    subject=f"Pedido #{order_id} confirmado - Royal Burger",
                    template='order_confirmation',
                    user=customer,
                    order=order_data,
                    app_url=Config.APP_URL
                )
        except Exception as e:
            # Não falha a criação do pedido se houver erro ao enviar email
            logger.warning(f"Erro ao enviar email de confirmação do pedido {order_id}: {e}", exc_info=True)
        
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
            # OTIMIZAÇÃO: Converter datas para range queries (substitui DATE() por range para usar índices)
            if filters.get('start_date'):
                # Se for date, converte para datetime (início do dia)
                start_date = filters['start_date']
                if isinstance(start_date, str):
                    try:
                        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                    except (ValueError, TypeError) as e:
                        # ALTERAÇÃO: Especificar exceções esperadas ao invés de catch-all genérico
                        logger.debug(f"Erro ao converter start_date '{start_date}': {e}")
                        pass
                if isinstance(start_date, date) and not isinstance(start_date, datetime):
                    start_date = datetime.combine(start_date, datetime.min.time())
                conditions.append("o.CREATED_AT >= ?")
                params.append(start_date)
            
            if filters.get('end_date'):
                # Se for date, converte para datetime (fim do dia)
                end_date = filters['end_date']
                if isinstance(end_date, str):
                    try:
                        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                    except (ValueError, TypeError) as e:
                        # ALTERAÇÃO: Especificar exceções esperadas ao invés de catch-all genérico
                        logger.debug(f"Erro ao converter end_date '{end_date}': {e}")
                        pass
                if isinstance(end_date, date) and not isinstance(end_date, datetime):
                    end_date = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
                conditions.append("o.CREATED_AT < ?")
                params.append(end_date)
            
            if filters.get('status'):
                conditions.append("o.STATUS = ?")
                params.append(filters['status'])
        
        if conditions:
            base_sql += " AND " + " AND ".join(conditions)
        
        # OTIMIZAÇÃO: Validação de parâmetros de paginação usando função utilitária (seção 1.9 e 1.10)
        from ..utils.validators import validate_pagination_params
        page = filters.get('page', 1) if filters else 1
        page_size = filters.get('page_size', 50) if filters else 50
        try:
            page, page_size, offset = validate_pagination_params(page, page_size, max_page_size=100)
        except ValueError:
            page = 1
            page_size = 50
            offset = 0
        
        # Query de contagem para paginação
        count_query = """
            SELECT COUNT(*)
            FROM ORDERS o
            JOIN USERS u ON o.USER_ID = u.ID
            LEFT JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            WHERE 1=1
        """
        if conditions:
            count_query += " AND " + " AND ".join(conditions)
        
        cur.execute(count_query, params)
        total = cur.fetchone()[0] or 0
        
        # Ordenação
        sort_by = filters.get('sort_by', 'date_desc') if filters else 'date_desc'
        if sort_by == 'date_desc':
            order_clause = " ORDER BY o.CREATED_AT DESC"
        elif sort_by == 'date_asc':
            order_clause = " ORDER BY o.CREATED_AT ASC"
        else:
            order_clause = " ORDER BY o.CREATED_AT DESC"
        
        # OTIMIZAÇÃO: Query principal com paginação usando FIRST/SKIP do Firebird
        paginated_query = f"""
            SELECT FIRST {page_size} SKIP {offset}
                o.ID, o.STATUS, o.CONFIRMATION_CODE, o.CREATED_AT, o.TOTAL_AMOUNT,
                o.ORDER_TYPE, u.FULL_NAME as customer_name, a.STREET, a."NUMBER"
            FROM ORDERS o
            JOIN USERS u ON o.USER_ID = u.ID
            LEFT JOIN ADDRESSES a ON o.ADDRESS_ID = a.ID
            WHERE 1=1
        """
        if conditions:
            paginated_query += " AND " + " AND ".join(conditions)
        paginated_query += order_clause
        
        cur.execute(paginated_query, params)
        orders = []
        
        for row in cur.fetchall():
            # Monta endereço ou exibe tipo de retirada
            # row[0] = o.ID
            # row[1] = o.STATUS
            # row[2] = o.CONFIRMATION_CODE
            # row[3] = o.CREATED_AT
            # row[4] = o.TOTAL_AMOUNT
            # row[5] = o.ORDER_TYPE
            # row[6] = u.FULL_NAME (customer_name)
            # row[7] = a.STREET
            # row[8] = a."NUMBER"
            order_type = row[5] if row[5] else ORDER_TYPE_DELIVERY
            address_str = None
            if order_type == ORDER_TYPE_PICKUP:
                address_str = "Retirada no balcão"
            elif order_type == ORDER_TYPE_ON_SITE:
                address_str = "Pedido no local"
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
        
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
        
        return {
            "items": orders,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
        }
        
    except fdb.Error as e:
        logger.error(f"Erro ao buscar pedidos com filtros: {e}", exc_info=True)
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
