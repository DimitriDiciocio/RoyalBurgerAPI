# src/routes/order_routes.py

from flask import Blueprint, request, jsonify
# 1. AJUSTE: Imports limpos e centralizados no topo
from ..services import order_service, address_service, store_service
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required, get_jwt

order_bp = Blueprint('orders', __name__)


# POST /src/orders/ -> Cliente cria um novo pedido
@order_bp.route('/', methods=['POST'])
@require_role('customer')
def create_order_route():
    # Verificação de loja aberta
    is_open, message = store_service.is_store_open()
    if not is_open:
        return jsonify({"error": message}), 409
    
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    data = request.get_json()

    # Coleta dos dados
    address_id = data.get('address_id')
    items = data.get('items')
    payment_method = data.get('payment_method')
    notes = data.get('notes', '')
    change_for_amount = data.get('change_for_amount')
    cpf_on_invoice = data.get('cpf_on_invoice')
    # 2. AJUSTE: Adicionada a coleta dos pontos a serem resgatados
    points_to_redeem = data.get('points_to_redeem', 0)

    if not all([address_id, items, payment_method]):
        return jsonify({"error": "address_id, items e payment_method são obrigatórios"}), 400

    address = address_service.get_address_by_id(address_id)
    if not address or address.get('user_id') != user_id:
        return jsonify({"error": "Endereço inválido ou não pertence a este usuário"}), 403

    # Chamada de serviço agora passa todos os parâmetros, incluindo os pontos
    new_order, error_code, error_message = order_service.create_order(
        user_id,
        address_id,
        items,
        payment_method,
        change_for_amount,
        notes,
        cpf_on_invoice,
        points_to_redeem # Passando os pontos para a função de serviço
    )

    if new_order:
        return jsonify(new_order), 201
    
    # Retorna códigos de status HTTP específicos baseados no erro
    if error_code == "STORE_CLOSED":
        return jsonify({"error": error_message}), 409
    elif error_code in ["INVALID_CPF", "EMPTY_ORDER", "MISSING_PAYMENT_METHOD", "INVALID_DISCOUNT"]:
        return jsonify({"error": error_message}), 400
    elif error_code == "INGREDIENT_UNAVAILABLE":
        return jsonify({"error": error_message}), 422
    elif error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    else:
        return jsonify({"error": "Não foi possível criar o pedido."}), 500


# GET /src/orders/ -> Cliente logado vê seu histórico de pedidos
@order_bp.route('/', methods=['GET'])
@require_role('customer')
def get_my_orders_route():
    claims = get_jwt()
    user_id = int(claims.get('sub'))
    orders = order_service.get_orders_by_user_id(user_id)
    return jsonify(orders), 200


# GET /src/orders/all -> Admin/Manager vê todos os pedidos do sistema
@order_bp.route('/all', methods=['GET'])
@require_role('admin', 'manager')
def get_all_orders_route():
    orders = order_service.get_all_orders()
    return jsonify(orders), 200


# PATCH /src/orders/<order_id>/status -> Admin/Manager/Attendant atualiza o status
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


# GET /src/orders/<order_id> -> Busca os detalhes de um pedido específico
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


# POST /src/orders/<order_id>/cancel -> Cliente cancela seu próprio pedido
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