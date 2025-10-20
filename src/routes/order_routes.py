from flask import Blueprint, request, jsonify, Response, send_file  
from ..services import order_service, address_service, store_service  
from ..services.auth_service import require_role  
from flask_jwt_extended import jwt_required, get_jwt  
from ..services.printing_service import generate_kitchen_ticket_pdf, print_pdf_bytes, print_kitchen_ticket

order_bp = Blueprint('orders', __name__)  

@order_bp.route('/', methods=['POST'])  
@require_role('customer')  
def create_order_route():  
    is_open, message = store_service.is_store_open()  
    if not is_open:  
        return jsonify({"error": message}), 409  
    claims = get_jwt()  
    user_id = int(claims.get('sub'))  
    data = request.get_json()  
    address_id = data.get('address_id')  
    items = data.get('items')  
    payment_method = data.get('payment_method')  
    notes = data.get('notes', '')  
    change_for_amount = data.get('change_for_amount')  
    cpf_on_invoice = data.get('cpf_on_invoice')  
    points_to_redeem = data.get('points_to_redeem', 0)
    use_cart = data.get('use_cart', False)  # Nova opção para usar carrinho
    
    # Validações básicas
    if not all([address_id, payment_method]):  
        return jsonify({"error": "address_id e payment_method são obrigatórios"}), 400
    
    # Se não usar carrinho, items é obrigatório
    if not use_cart and not items:
        return jsonify({"error": "items é obrigatório quando use_cart é false"}), 400
    
    # Verifica endereço
    address = address_service.get_address_by_id(address_id)  
    if not address or address.get('user_id') != user_id:  
        return jsonify({"error": "Endereço inválido ou não pertence a este usuário"}), 403
    
    # Escolhe o método de criação baseado na opção
    if use_cart:
        # Cria pedido a partir do carrinho
        new_order, error_code, error_message = order_service.create_order_from_cart(
            user_id,
            address_id,
            payment_method,
            change_for_amount,
            notes,
            cpf_on_invoice,
            points_to_redeem
        )
    else:
        # Cria pedido tradicional
        new_order, error_code, error_message = order_service.create_order(  
            user_id,
            address_id,
            items,
            payment_method,
            change_for_amount,
            notes,
            cpf_on_invoice,
            points_to_redeem
        )
    if new_order:  
        return jsonify(new_order), 201  
    if error_code == "STORE_CLOSED":  
        return jsonify({"error": error_message}), 409  
    elif error_code in ["INVALID_CPF", "EMPTY_ORDER", "MISSING_PAYMENT_METHOD", "INVALID_DISCOUNT", "EMPTY_CART"]:  
        return jsonify({"error": error_message}), 400  
    elif error_code == "INGREDIENT_UNAVAILABLE":  
        return jsonify({"error": error_message}), 422  
    elif error_code == "DATABASE_ERROR":  
        return jsonify({"error": error_message}), 500  
    else:  
        return jsonify({"error": "Não foi possível criar o pedido."}), 500  

@order_bp.route('/', methods=['GET'])  
@require_role('customer')  
def get_my_orders_route():  
    claims = get_jwt()  
    user_id = int(claims.get('sub'))  
    orders = order_service.get_orders_by_user_id(user_id)  
    return jsonify(orders), 200  

@order_bp.route('/all', methods=['GET'])  
@require_role('admin', 'manager')  
def get_all_orders_route():  
    orders = order_service.get_all_orders()  
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
@require_role('customer')  
def cancel_order_route(order_id):  
    claims = get_jwt()  
    user_id = int(claims.get('sub'))  
    success, message = order_service.cancel_order_by_customer(order_id, user_id)  
    if success:  
        return jsonify({"msg": message}), 200  
    else:  
        return jsonify({"error": message}), 403  


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
