# src/routes/chat_routes.py

from flask import Blueprint, jsonify, request
from ..services import chat_service
from ..services.auth_service import require_role
from flask_jwt_extended import get_jwt

chat_bp = Blueprint('chats', __name__)


@chat_bp.route('/<int:order_id>', methods=['GET'])
@require_role('customer', 'admin', 'manager', 'attendant')
def get_chat_history_route(order_id):
    """
    Busca o histórico de mensagens de um chat de um pedido.
    A lógica de permissão (cliente só pode ver seu próprio chat) é
    tratada dentro do serviço.
    """
    claims = get_jwt()
    user_id = claims.get('id')
    user_role = claims.get('role')

    history = chat_service.get_chat_history(order_id, user_id, user_role)

    if history is None:
        return jsonify({"error": "Pedido não encontrado"}), 404

    if history == 'forbidden':
        return jsonify({"error": "Acesso negado a este chat"}), 403

    return jsonify(history), 200


@chat_bp.route('/<int:order_id>/messages', methods=['POST'])
@require_role('customer', 'admin', 'manager', 'attendant')
def post_message_route(order_id):
    """
    Envia uma nova mensagem para o chat de um pedido.
    O remetente é identificado pelo token JWT.
    """
    claims = get_jwt()
    sender_id = claims.get('id')

    data = request.get_json()
    message_text = data.get('message')

    if not message_text or not isinstance(message_text, str) or not message_text.strip():
        return jsonify({"error": "A mensagem não pode ser vazia"}), 400

    new_message = chat_service.add_message(order_id, sender_id, message_text)

    if new_message:
        return jsonify(new_message), 201
    else:
        return jsonify({"error": "Não foi possível enviar a mensagem. Verifique se o pedido existe."}), 500