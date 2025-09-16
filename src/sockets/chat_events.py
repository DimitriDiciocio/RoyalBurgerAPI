# src/sockets/chat_events.py

from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import join_room, leave_room, emit

from .. import socketio
from ..services import chat_service


@socketio.on('connect')
def handle_connect():
    """
    Evento que é acionado quando um cliente se conecta ao servidor WebSocket.
    """
    print(f"Cliente conectado: {request.sid}")


@socketio.on('disconnect')
def handle_disconnect():
    """
    Evento que é acionado quando um cliente se desconecta.
    """
    print(f"Cliente desconectado: {request.sid}")


@socketio.on('join_chat')
def handle_join_chat(data):
    """
    Cliente entra em uma sala de chat para receber mensagens.
    Espera receber: {'token': 'seu_jwt_aqui', 'chat_id': 123}
    """
    token = data.get('token')
    chat_id = data.get('chat_id')

    if not token or not chat_id:
        return  # Ignora se os dados estiverem incompletos

    try:
        # 1. Validação do Token e verificação de permissão (aqui podemos checar se o usuário pode entrar nesse chat)
        # Numa aplicação real, faríamos uma consulta no banco para garantir que o user_id do token é o dono do chat_id
        decoded_token = decode_token(token)
        user_id = decoded_token.get('sub')  # 'sub' é a identidade do usuário no JWT
        print(f"Usuário {user_id} tentando entrar no chat {chat_id}")

        # 2. Cria uma "sala" privada para este chat
        room = f"chat_{chat_id}"
        join_room(room)
        print(f"Cliente {request.sid} entrou na sala {room}")

        # 3. Busca o histórico de mensagens e envia de volta APENAS para o cliente que acabou de entrar
        history = chat_service.get_chat_history(chat_id)
        emit('chat_history', {'chat_id': chat_id, 'history': history})

    except Exception as e:
        print(f"Erro na autenticação do socket ou ao entrar no chat: {e}")


@socketio.on('send_message')
def handle_send_message(data):
    """
    Cliente envia uma nova mensagem.
    Espera receber: {'token': 'seu_jwt_aqui', 'chat_id': 123, 'content': 'Olá, mundo!'}
    """
    token = data.get('token')
    chat_id = data.get('chat_id')
    content = data.get('content')

    if not token or not chat_id or not content:
        return

    try:
        # 1. Validação do Token para saber quem está enviando
        decoded_token = decode_token(token)
        user_role = decoded_token.get('role')  # Pegamos a 'role' que salvamos no token

        # Determina o tipo de remetente com base no cargo
        sender_type = 'customer' if user_role == 'customer' else 'attendant'

        # 2. Salva a mensagem no banco de dados através do nosso serviço
        chat_service.save_message(chat_id, sender_type, content)

        # 3. Prepara a mensagem para ser enviada aos clientes em tempo real
        message_data = {
            'sender': sender_type,
            'content': content,
            'timestamp': 'agora'  # O front-end pode formatar a data/hora atual
        }

        # 4. Emite a nova mensagem para todos na mesma sala
        room = f"chat_{chat_id}"
        socketio.emit('new_message', message_data, room=room)
        print(f"Mensagem enviada para a sala {room}")

    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")