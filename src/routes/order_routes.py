from flask import Blueprint, request, jsonify, Response
from ..services import order_service, address_service, store_service  
from ..services.auth_service import require_role  
from flask_jwt_extended import jwt_required, get_jwt  
from ..services.printing_service import generate_kitchen_ticket_pdf, print_kitchen_ticket, format_order_for_kitchen_json
from .. import socketio

order_bp = Blueprint('orders', __name__)  

@order_bp.route('/', methods=['POST'])  
@require_role('customer')  
def create_order_route():  
    is_open, message = store_service.is_store_open()  
    if not is_open:  
        return jsonify({"error": message}), 409  
    claims = get_jwt()
    
    # Valida e extrai user_id de forma segura
    user_id_raw = claims.get('sub')
    if not user_id_raw:
        return jsonify({"error": "Token inválido: user_id não encontrado"}), 401
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Token inválido: user_id inválido"}), 401
    
    data = request.get_json()
    
    # Valida order_type (delivery ou pickup)
    order_type = data.get('order_type', 'delivery')
    if order_type not in ['delivery', 'pickup']:
        return jsonify({"error": "order_type deve ser 'delivery' ou 'pickup'"}), 400
    
    address_id = data.get('address_id')
    items = data.get('items')
    payment_method = data.get('payment_method')
    notes = data.get('notes', '')
    amount_paid = data.get('amount_paid')  # Valor pago (usado para calcular troco automaticamente)
    cpf_on_invoice = data.get('cpf_on_invoice')
    points_to_redeem = data.get('points_to_redeem', 0)
    use_cart = data.get('use_cart', False)  # Nova opção para usar carrinho
    
    # Validações básicas
    if not payment_method:
        return jsonify({"error": "payment_method é obrigatório"}), 400
    
    # address_id só obrigatório para delivery
    if order_type == 'delivery' and not address_id:
        return jsonify({"error": "address_id é obrigatório para pedidos de entrega"}), 400
    
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
        # Cria pedido a partir do carrinho
        new_order, error_code, error_message = order_service.create_order_from_cart(
            user_id,
            address_id if order_type == 'delivery' else None,
            payment_method,
            amount_paid,  # Passa amount_paid ao invés de change_for_amount
            notes,
            cpf_on_invoice,
            points_to_redeem,
            order_type
        )
    else:
        # Cria pedido tradicional
        new_order, error_code, error_message = order_service.create_order(  
            user_id,
            address_id if order_type == 'delivery' else None,
            items,
            payment_method,
            amount_paid,  # Passa amount_paid ao invés de change_for_amount
            notes,
            cpf_on_invoice,
            points_to_redeem,
            order_type
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
    except Exception:
        # Log erro sem expor detalhes sensíveis
        # TODO: Implementar logging adequado (ex: logger.error) em produção
        return jsonify({"error": "Erro ao processar solicitação"}), 500

@order_bp.route('/', methods=['GET'])  
@require_role('customer')  
def get_my_orders_route():  
    claims = get_jwt()  
    user_id = int(claims.get('sub'))
    
    # OTIMIZAÇÃO: Suportar parâmetros de paginação
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    
    result = order_service.get_orders_by_user_id(user_id, page=page, page_size=page_size)
    
    # Compatibilidade: Se retornar lista (formato antigo), manter compatibilidade
    if isinstance(result, list):
        return jsonify(result), 200
    
    # Novo formato com paginação
    return jsonify(result), 200  

@order_bp.route('/all', methods=['GET'])  
@require_role('admin', 'manager')  
def get_all_orders_route():  
    # OTIMIZAÇÃO: Suportar parâmetros de paginação (seção 1.9)
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    orders = order_service.get_all_orders(page=page, page_size=page_size)  
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
    user_id = int(claims.get('sub'))  
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
    user_id = int(claims.get('sub'))  
    user_roles = claims.get('roles', [])
    
    # Verifica se é gerente (manager ou admin)
    is_manager = 'manager' in user_roles or 'admin' in user_roles
    
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


# --- Rotas de impressão de cozinha ---
@order_bp.route('/<int:order_id>/print-kitchen-ticket', methods=['POST'])
@require_role('admin', 'manager')
def print_kitchen_ticket_route(order_id):
    claims = get_jwt()
    user_id = int(claims.get('sub'))
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
        return jsonify({"status": "error", "message": str(e)}), 500


@order_bp.route('/<int:order_id>/reprint', methods=['POST'])
@require_role('admin', 'manager')
def reprint_kitchen_ticket_event_route(order_id):
    """
    Emite o evento de reimpressão no WebSocket para o agente de impressão.
    """
    claims = get_jwt()
    user_id = int(claims.get('sub'))
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
        return jsonify({"error": str(e)}), 500


@order_bp.route('/<int:order_id>/kitchen-ticket.pdf', methods=['GET'])
@require_role('admin', 'manager')
def get_kitchen_ticket_pdf_route(order_id):
    claims = get_jwt()
    user_id = int(claims.get('sub'))
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
