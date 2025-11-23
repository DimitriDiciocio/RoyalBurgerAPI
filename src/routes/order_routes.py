from flask import Blueprint, request, jsonify, Response
from ..services import order_service, address_service, store_service  
from ..services.auth_service import require_role  
from flask_jwt_extended import jwt_required, get_jwt  
from ..services.printing_service import generate_kitchen_ticket_pdf, print_kitchen_ticket, format_order_for_kitchen_json
from .. import socketio
import logging  # ALTERAÇÃO: Import centralizado para logging estruturado

order_bp = Blueprint('orders', __name__)
logger = logging.getLogger(__name__)  # ALTERAÇÃO: Logger centralizado  

@order_bp.route('/', methods=['POST'])  
@jwt_required()
def create_order_route():  
    is_open, message = store_service.is_store_open()  
    if not is_open:  
        return jsonify({"error": message}), 409  
    claims = get_jwt()
    user_roles = claims.get('roles', [])
    
    # ALTERAÇÃO: Verificar permissão - customer pode criar qualquer pedido, attendant apenas on-site
    is_customer = 'customer' in user_roles
    is_attendant = 'attendant' in user_roles
    
    if not is_customer and not is_attendant:
        return jsonify({"msg": "Acesso não autorizado para esta função."}), 403
    
    data = request.get_json()
    
    # ALTERAÇÃO: Valida order_type (delivery, pickup ou on_site)
    order_type = data.get('order_type', 'delivery')
    if order_type not in ['delivery', 'pickup', 'on_site']:
        return jsonify({"error": "order_type deve ser 'delivery', 'pickup' ou 'on_site'"}), 400
    
    # ALTERAÇÃO: Attendants só podem criar pedidos on-site
    if is_attendant and order_type != 'on_site':
        return jsonify({"error": "Atendentes só podem criar pedidos on-site"}), 403
    
    # ALTERAÇÃO: Customers não podem criar pedidos on-site (apenas via aplicativo para delivery/pickup)
    if is_customer and order_type == 'on_site':
        return jsonify({"error": "Clientes não podem criar pedidos on-site. Use delivery ou pickup."}), 403
    
    # ALTERAÇÃO: Para pedidos on-site, user_id pode vir do request (atendente cria para o cliente)
    # Para outros tipos, sempre usa o user_id do token
    if order_type == 'on_site' and is_attendant:
        # Atendente pode criar pedido para outro cliente (user_id no request)
        customer_user_id = data.get('customer_user_id') or data.get('user_id')
        if not customer_user_id:
            return jsonify({"error": "customer_user_id é obrigatório para pedidos on-site criados por atendentes"}), 400
        try:
            user_id = int(customer_user_id)
        except (ValueError, TypeError):
            return jsonify({"error": "customer_user_id deve ser um número inteiro válido"}), 400
    else:
        # Valida e extrai user_id de forma segura do token
        user_id_raw = claims.get('sub')
        if not user_id_raw:
            return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
        try:
            user_id = int(user_id_raw)
        except (ValueError, TypeError):
            return jsonify({"error": "Token inválido: user_id inválido"}), 401
    
    address_id = data.get('address_id')
    items = data.get('items')
    payment_method = data.get('payment_method')
    notes = data.get('notes', '')
    amount_paid = data.get('amount_paid')  # Valor pago (usado para calcular troco automaticamente)
    cpf_on_invoice = data.get('cpf_on_invoice')
    points_to_redeem = data.get('points_to_redeem', 0)
    use_cart = data.get('use_cart', False)  # Nova opção para usar carrinho
    promotions = data.get('promotions')  # ALTERAÇÃO: Informações de promoções para aplicar descontos
    table_id = data.get('table_id')  # ALTERAÇÃO: ID da mesa para pedidos on-site
    
    # Validações básicas
    if not payment_method:
        return jsonify({"error": "payment_method é obrigatório"}), 400
    
    # ALTERAÇÃO: address_id só obrigatório para delivery, table_id opcional para on-site
    if order_type == 'delivery' and not address_id:
        return jsonify({"error": "address_id é obrigatório para pedidos de entrega"}), 400
    
    # ALTERAÇÃO: Validar mesa apenas se table_id for fornecido para pedidos on-site
    if order_type == 'on_site' and table_id is not None:
        try:
            table_id = int(table_id)
            if table_id <= 0:
                return jsonify({"error": "table_id deve ser um número inteiro válido"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "table_id deve ser um número inteiro válido"}), 400
    
    # Se não usar carrinho, items é obrigatório
    if not use_cart and not items:
        return jsonify({"error": "items é obrigatório quando use_cart é false"}), 400
    
    # Verifica endereço apenas se for delivery
    if order_type == 'delivery':
        address = address_service.get_address_by_id(address_id)  
        if not address or address.get('user_id') != user_id:  
            return jsonify({"error": "Endereço inválido ou não pertence a este usuário"}), 403
    
    # Escolhe o método de criação baseado na opção
    if use_cart:
        # ALTERAÇÃO: Cria pedido a partir do carrinho com promoções
        new_order, error_code, error_message = order_service.create_order_from_cart(
            user_id,
            address_id if order_type == 'delivery' else None,
            payment_method,
            amount_paid,  # Passa amount_paid ao invés de change_for_amount
            notes,
            cpf_on_invoice,
            points_to_redeem,
            order_type,
            promotions,  # ALTERAÇÃO: Passar promoções para aplicar descontos
            table_id  # ALTERAÇÃO: Passar table_id para pedidos on-site
        )
    else:
        # ALTERAÇÃO: Cria pedido tradicional com promoções
        new_order, error_code, error_message = order_service.create_order(  
            user_id,
            address_id if order_type == 'delivery' else None,
            items,
            payment_method,
            amount_paid,  # Passa amount_paid ao invés de change_for_amount
            notes,
            cpf_on_invoice,
            points_to_redeem,
            order_type,
            promotions,  # ALTERAÇÃO: Passar promoções para aplicar descontos
            table_id  # ALTERAÇÃO: Passar table_id para pedidos on-site
        )
    if new_order:  
        return jsonify(new_order), 201  
    
    # Tratamento de erros específicos
    if error_code == "STORE_CLOSED":  
        return jsonify({"error": error_message}), 409  
    elif error_code in ["INSUFFICIENT_STOCK", "STOCK_VALIDATION_ERROR"]:  
        return jsonify({"error": error_message}), 422  
    elif error_code in ["INVALID_CPF", "EMPTY_ORDER", "MISSING_PAYMENT_METHOD", "INVALID_DISCOUNT", "EMPTY_CART", "VALIDATION_ERROR", "INVALID_ADDRESS"]:  
        return jsonify({"error": error_message}), 400  
    elif error_code == "INGREDIENT_UNAVAILABLE":  
        return jsonify({"error": error_message}), 422  
    elif error_code in ["TABLE_NOT_FOUND", "TABLE_NOT_AVAILABLE"]:
        return jsonify({"error": error_message}), 404 if error_code == "TABLE_NOT_FOUND" else 409
    elif error_code == "DATABASE_ERROR":  
        return jsonify({"error": error_message}), 500  
    
    # Erro desconhecido - não expõe detalhes sensíveis
    return jsonify({"error": "Não foi possível criar o pedido. Tente novamente."}), 500  

@order_bp.route('/calculate-total', methods=['POST'])
@require_role('customer')
def calculate_order_total_route():
    """Calcula o total do pedido sem criar o pedido"""
    data = request.get_json()
    
    if not data or 'items' not in data:
        return jsonify({"error": "items é obrigatório"}), 400
    
    items = data.get('items', [])
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "A lista de items não pode estar vazia"}), 400
    
    order_type = data.get('order_type', 'delivery')
    if order_type not in ['delivery', 'pickup']:
        return jsonify({"error": "order_type deve ser 'delivery' ou 'pickup'"}), 400
    
    points_to_redeem = data.get('points_to_redeem', 0)
    
    # Valida pontos como inteiro não negativo
    if not isinstance(points_to_redeem, (int, float)):
        return jsonify({"error": "points_to_redeem deve ser um número"}), 400
    if points_to_redeem < 0:
        return jsonify({"error": "points_to_redeem não pode ser negativo"}), 400
    points_to_redeem = int(points_to_redeem)
    
    try:
        result = order_service.calculate_order_total_with_fees(
            items=items,
            points_to_redeem=points_to_redeem,
            order_type=order_type
        )
        
        if result:
            return jsonify(result), 200
        return jsonify({"error": "Erro ao calcular total do pedido"}), 500
    except ValueError as e:
        # Erro de validação - mensagem segura para o cliente
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao calcular total do pedido: {e}", exc_info=True)
        # Não expõe detalhes sensíveis ao cliente
        return jsonify({"error": "Erro ao processar solicitação"}), 500

@order_bp.route('/', methods=['GET'])  
@require_role('customer')  
def get_my_orders_route():  
    claims = get_jwt()  
    # ALTERAÇÃO: Validação segura de user_id para evitar ValueError/TypeError
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    
    # ALTERAÇÃO: Validação de parâmetros de paginação para evitar valores inválidos
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50
    if page_size > 100:  # Limite máximo para evitar sobrecarga
        page_size = 100
    
    result = order_service.get_orders_by_user_id(user_id, page=page, page_size=page_size)
    
    # Compatibilidade: Se retornar lista (formato antigo), manter compatibilidade
    if isinstance(result, list):
        return jsonify(result), 200
    
    # Novo formato com paginação
    return jsonify(result), 200  

@order_bp.route('/today', methods=['GET'])
@require_role('admin', 'manager')
def get_today_orders_route():
    """
    Retorna pedidos do dia atual
    Fase Futura: Endpoint específico para melhorar performance
    """
    # ALTERAÇÃO: Validação de parâmetros de paginação
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50
    if page_size > 100:
        page_size = 100
    
    # ALTERAÇÃO: Buscar pedidos de hoje usando o service com período 'today'
    orders = order_service.get_all_orders(
        page=page,
        page_size=page_size,
        search=None,
        status=None,
        channel=None,
        period='today'
    )
    
    return jsonify(orders), 200

@order_bp.route('/all', methods=['GET'])  
@require_role('admin', 'manager')  
def get_all_orders_route():  
    # ALTERAÇÃO: Validação de parâmetros de paginação para evitar valores inválidos
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50
    if page_size > 100:  # Limite máximo para evitar sobrecarga
        page_size = 100
    
    # ALTERAÇÃO: Ler filtros se presentes
    search = request.args.get('search', '').strip() or None
    status = request.args.get('status', '').strip() or None
    channel = request.args.get('channel', '').strip() or None
    period = request.args.get('period', '').strip() or None
    
    # ALTERAÇÃO: Passar filtros para o service
    orders = order_service.get_all_orders(
        page=page, 
        page_size=page_size,
        search=search,
        status=status,
        channel=channel,
        period=period
    )
    
    return jsonify(orders), 200  

@order_bp.route('/<int:order_id>/status', methods=['PATCH'])  
@require_role('admin', 'manager', 'attendant')  
def update_order_status_route(order_id):  
    data = request.get_json()  
    new_status = data.get('status')  
    if not new_status:  
        return jsonify({"error": "O campo 'status' é obrigatório"}), 400  
    if order_service.update_order_status(order_id, new_status):  
        return jsonify({"msg": f"Status do pedido {order_id} atualizado para '{new_status}'"}), 200  
    return jsonify({"error": "Falha ao atualizar status."}), 400  

@order_bp.route('/<int:order_id>', methods=['GET'])  
@jwt_required()  
def get_order_details_route(order_id):  
    claims = get_jwt()  
    # ALTERAÇÃO: Validação segura de user_id para evitar ValueError/TypeError
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    user_roles = claims.get('roles', [])  
    order = order_service.get_order_details(order_id, user_id, user_roles)  
    if order:  
        return jsonify(order), 200  
    else:  
        return jsonify({"error": "Pedido não encontrado"}), 404  

@order_bp.route('/<int:order_id>/cancel', methods=['POST'])  
@require_role('customer', 'manager')  
def cancel_order_route(order_id):  
    claims = get_jwt()  
    # ALTERAÇÃO: Validação segura de user_id para evitar ValueError/TypeError
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    user_roles = claims.get('roles', [])
    
    # Verifica se é gerente (manager ou admin)
    is_manager = 'manager' in user_roles or 'admin' in user_roles
    
    # NOVO: Aceita parâmetro opcional 'reason' no body para log/auditoria
    data = request.get_json() or {}
    reason = data.get('reason')
    if reason:
        logger.info(f"Cancelamento do pedido {order_id} solicitado por usuário {user_id}. Motivo: {reason}")
    
    success, message = order_service.cancel_order(order_id, user_id, is_manager)  
    if success:  
        return jsonify({"msg": message}), 200  
    else:  
        # Retorna 404 se pedido não encontrado, 403 para permissão, 400 para status inválido
        if "não encontrado" in message.lower():
            return jsonify({"error": message}), 404
        elif "permissão" in message.lower() or "não pode cancelar" in message.lower():
            return jsonify({"error": message}), 403
        else:
            return jsonify({"error": message}), 400


@order_bp.route('/<int:order_id>/uncancel', methods=['POST'])
@require_role('admin', 'manager')
def uncancel_order_route(order_id):
    """
    Reverte o cancelamento de um pedido.
    Apenas gerentes e administradores podem executar esta ação.
    """
    claims = get_jwt()
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    
    success, message = order_service.uncancel_order(order_id, user_id)
    
    if success:
        return jsonify({"msg": message}), 200
    else:
        # Retorna 404 se pedido não encontrado, 400 para outros erros
        if "não encontrado" in message.lower():
            return jsonify({"error": message}), 404
        else:
            return jsonify({"error": message}), 400  


# --- Rotas de impressão de cozinha ---
@order_bp.route('/<int:order_id>/print-kitchen-ticket', methods=['POST'])
@require_role('admin', 'manager')
def print_kitchen_ticket_route(order_id):
    claims = get_jwt()
    # ALTERAÇÃO: Validação segura de user_id (mesmo que não seja usado, mantém consistência)
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    # Admin/manager podem visualizar e imprimir qualquer pedido
    order = order_service.get_order_details(order_id, user_id, claims.get('roles', []))
    if not order:
        return jsonify({"error": "Pedido não encontrado"}), 404
    try:
        result = print_kitchen_ticket({
            "id": order.get('id') or order_id,
            "created_at": order.get('created_at'),
            "order_type": order.get('order_type', 'Delivery'),
            "notes": order.get('notes', ''),
            "items": order.get('items', [])
        })
        status_code = 200 if result.get('status') == 'printed' else 500
        return jsonify(result), status_code
    except Exception as e:
        # ALTERAÇÃO: Usar logger ao invés de expor detalhes do erro diretamente
        logger.error(f"Erro ao imprimir ticket do pedido {order_id}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Erro ao imprimir ticket"}), 500


@order_bp.route('/<int:order_id>/reprint', methods=['POST'])
@require_role('admin', 'manager')
def reprint_kitchen_ticket_event_route(order_id):
    """
    Emite o evento de reimpressão no WebSocket para o agente de impressão.
    """
    claims = get_jwt()
    # ALTERAÇÃO: Validação segura de user_id (mesmo que não seja usado, mantém consistência)
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    order = order_service.get_order_details(order_id, user_id, claims.get('roles', []))
    if not order:
        return jsonify({"error": "Pedido não encontrado"}), 404
    try:
        payload = format_order_for_kitchen_json(order_id)
        if not payload:
            return jsonify({"error": "Falha ao montar ticket"}), 500
        socketio.emit('new_kitchen_order', payload)
        return jsonify({"status": "emitted", "order_id": order_id}), 200
    except Exception as e:
        # ALTERAÇÃO: Usar logger ao invés de expor detalhes do erro diretamente
        logger.error(f"Erro ao emitir evento de reimpressão do pedido {order_id}: {e}", exc_info=True)
        return jsonify({"error": "Erro ao emitir evento de reimpressão"}), 500


@order_bp.route('/<int:order_id>/kitchen-ticket.pdf', methods=['GET'])
@require_role('admin', 'manager')
def get_kitchen_ticket_pdf_route(order_id):
    claims = get_jwt()
    # ALTERAÇÃO: Validação segura de user_id (mesmo que não seja usado, mantém consistência)
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    order = order_service.get_order_details(order_id, user_id, claims.get('roles', []))
    if not order:
        return jsonify({"error": "Pedido não encontrado"}), 404
    pdf_bytes = generate_kitchen_ticket_pdf({
        "id": order.get('id') or order_id,
        "created_at": order.get('created_at'),
        "order_type": order.get('order_type', 'Delivery'),
        "notes": order.get('notes', ''),
        "items": order.get('items', [])
    })
    return Response(pdf_bytes, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="kitchen-ticket-{order_id}.pdf"'
    })

