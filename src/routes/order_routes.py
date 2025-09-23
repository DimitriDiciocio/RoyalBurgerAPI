from flask import Blueprint, request, jsonify  # importa Blueprint, request e jsonify do Flask
from ..services import order_service, address_service, store_service  # importa serviços de pedido, endereço e loja
from ..services.auth_service import require_role  # importa decorator de autorização por papel
from flask_jwt_extended import jwt_required, get_jwt  # importa utilitários JWT

order_bp = Blueprint('orders', __name__)  # cria o blueprint de pedidos

@order_bp.route('/', methods=['POST'])  # cliente cria um novo pedido
@require_role('customer')  # restringe a clientes
def create_order_route():  # função handler de criação de pedido
    is_open, message = store_service.is_store_open()  # verifica se a loja está aberta
    if not is_open:  # loja fechada
        return jsonify({"error": message}), 409  # retorna 409 conflito
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    data = request.get_json()  # captura corpo JSON
    address_id = data.get('address_id')  # extrai endereço
    items = data.get('items')  # extrai itens
    payment_method = data.get('payment_method')  # extrai método de pagamento
    notes = data.get('notes', '')  # extrai observações (opcional)
    change_for_amount = data.get('change_for_amount')  # extrai troco para (opcional)
    cpf_on_invoice = data.get('cpf_on_invoice')  # extrai CPF na nota (opcional)
    points_to_redeem = data.get('points_to_redeem', 0)  # extrai pontos a resgatar (opcional)
    if not all([address_id, items, payment_method]):  # valida obrigatórios
        return jsonify({"error": "address_id, items e payment_method são obrigatórios"}), 400  # retorna 400
    address = address_service.get_address_by_id(address_id)  # busca endereço
    if not address or address.get('user_id') != user_id:  # valida posse do endereço
        return jsonify({"error": "Endereço inválido ou não pertence a este usuário"}), 403  # retorna 403
    new_order, error_code, error_message = order_service.create_order(  # cria pedido no serviço
        user_id,
        address_id,
        items,
        payment_method,
        change_for_amount,
        notes,
        cpf_on_invoice,
        points_to_redeem
    )
    if new_order:  # criado com sucesso
        return jsonify(new_order), 201  # retorna 201
    if error_code == "STORE_CLOSED":  # loja fechada
        return jsonify({"error": error_message}), 409  # conflito 409
    elif error_code in ["INVALID_CPF", "EMPTY_ORDER", "MISSING_PAYMENT_METHOD", "INVALID_DISCOUNT"]:  # validações
        return jsonify({"error": error_message}), 400  # erro 400
    elif error_code == "INGREDIENT_UNAVAILABLE":  # ingrediente indisponível
        return jsonify({"error": error_message}), 422  # erro 422
    elif error_code == "DATABASE_ERROR":  # erro de banco
        return jsonify({"error": error_message}), 500  # erro 500
    else:  # fallback
        return jsonify({"error": "Não foi possível criar o pedido."}), 500  # erro 500 genérico

@order_bp.route('/', methods=['GET'])  # cliente logado vê seu histórico de pedidos
@require_role('customer')  # restringe a clientes
def get_my_orders_route():  # função handler de listagem do próprio usuário
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    orders = order_service.get_orders_by_user_id(user_id)  # busca pedidos do usuário
    return jsonify(orders), 200  # retorna lista com status 200

@order_bp.route('/all', methods=['GET'])  # admin/manager vê todos os pedidos
@require_role('admin', 'manager')  # restringe a admin/manager
def get_all_orders_route():  # função handler de listagem geral
    orders = order_service.get_all_orders()  # busca todos os pedidos
    return jsonify(orders), 200  # retorna lista com status 200

@order_bp.route('/<int:order_id>/status', methods=['PATCH'])  # atualiza status do pedido
@require_role('admin', 'manager', 'attendant')  # perfis autorizados
def update_order_status_route(order_id):  # função handler de atualização de status
    data = request.get_json()  # captura corpo JSON
    new_status = data.get('status')  # extrai novo status
    if not new_status:  # valida presença do status
        return jsonify({"error": "O campo 'status' é obrigatório"}), 400  # retorna 400
    if order_service.update_order_status(order_id, new_status):  # atualiza via serviço
        return jsonify({"msg": f"Status do pedido {order_id} atualizado para '{new_status}'"}), 200  # retorna 200
    return jsonify({"error": "Falha ao atualizar status."}), 400  # retorna 400 em falha

@order_bp.route('/<int:order_id>', methods=['GET'])  # busca detalhes de um pedido específico
@jwt_required()  # exige autenticação JWT
def get_order_details_route(order_id):  # função handler de detalhes do pedido
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    user_roles = claims.get('roles', [])  # extrai papéis do usuário
    order = order_service.get_order_details(order_id, user_id, user_roles)  # busca detalhes no serviço
    if order:  # encontrado
        return jsonify(order), 200  # retorna 200
    else:  # não encontrado
        return jsonify({"error": "Pedido não encontrado"}), 404  # retorna 404

@order_bp.route('/<int:order_id>/cancel', methods=['POST'])  # cliente cancela seu próprio pedido
@require_role('customer')  # restringe a clientes
def cancel_order_route(order_id):  # função handler de cancelamento
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    success, message = order_service.cancel_order_by_customer(order_id, user_id)  # tenta cancelar via serviço
    if success:  # cancelado com sucesso
        return jsonify({"msg": message}), 200  # retorna 200
    else:  # falha no cancelamento
        return jsonify({"error": message}), 403  # retorna 403