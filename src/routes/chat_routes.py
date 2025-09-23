from flask import Blueprint, jsonify, request  # importa Blueprint, jsonify e request do Flask
from ..services import chat_service  # importa o serviço de chat
from ..services.auth_service import require_role  # importa decorator de autorização por papel
from flask_jwt_extended import get_jwt  # importa utilitário para ler claims do JWT

chat_bp = Blueprint('chats', __name__)  # cria o blueprint de chats

@chat_bp.route('/<int:order_id>', methods=['GET'])  # define rota GET para histórico do chat de um pedido
@require_role('customer', 'admin', 'manager', 'attendant')  # restringe a perfis autorizados
def get_chat_history_route(order_id):  # função handler para buscar histórico de chat
    claims = get_jwt()  # obtém claims do token
    user_id = int(claims.get('sub'))  # extrai ID do usuário
    user_roles = claims.get('roles', [])  # extrai papéis do usuário
    history = chat_service.get_chat_history(order_id, user_id, user_roles)  # busca histórico no serviço
    if history is None:  # pedido não encontrado
        return jsonify({"error": "Pedido não encontrado"}), 404  # retorna 404
    if history == 'forbidden':  # acesso negado pelo serviço
        return jsonify({"error": "Acesso negado a este chat"}), 403  # retorna 403
    return jsonify(history), 200  # retorna histórico com status 200

@chat_bp.route('/<int:order_id>/messages', methods=['POST'])  # define rota POST para enviar mensagem no chat
@require_role('customer', 'admin', 'manager', 'attendant')  # restringe a perfis autorizados
def post_message_route(order_id):  # função handler para envio de mensagem
    claims = get_jwt()  # obtém claims do token
    sender_id = int(claims.get('sub'))  # extrai ID do remetente
    data = request.get_json()  # captura corpo JSON
    message_text = data.get('message')  # extrai texto da mensagem
    if not message_text or not isinstance(message_text, str) or not message_text.strip():  # valida conteúdo
        return jsonify({"error": "A mensagem não pode ser vazia"}), 400  # retorna 400 se inválido
    new_message = chat_service.add_message(order_id, sender_id, message_text)  # delega envio ao serviço
    if new_message:  # enviado com sucesso
        return jsonify(new_message), 201  # retorna 201 com mensagem criada
    else:  # falha ao enviar
        return jsonify({"error": "Não foi possível enviar a mensagem. Verifique se o pedido existe."}), 500  # retorna 500