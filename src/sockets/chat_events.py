from flask import request  # importa request do Flask
from flask_jwt_extended import decode_token  # importa função para decodificar JWT
from flask_socketio import join_room, leave_room, emit  # importa funções do SocketIO
from .. import socketio  # importa instância global do SocketIO
from ..services import chat_service  # importa serviço de chat

@socketio.on('connect')  # evento de conexão do cliente
def handle_connect():  # função handler de conexão
    print(f"Cliente conectado: {request.sid}")  # exibe ID da sessão do cliente

@socketio.on('disconnect')  # evento de desconexão do cliente
def handle_disconnect():  # função handler de desconexão
    print(f"Cliente desconectado: {request.sid}")  # exibe ID da sessão desconectada

@socketio.on('join_chat')  # evento de entrada em chat
def handle_join_chat(data):  # função handler de entrada em chat
    token = data.get('token')  # extrai token JWT dos dados
    chat_id = data.get('chat_id')  # extrai ID do chat
    if not token or not chat_id:  # valida presença dos dados obrigatórios
        return  # ignora se dados incompletos
    try:  # tenta processar entrada no chat
        decoded_token = decode_token(token)  # decodifica token JWT
        user_id = decoded_token.get('sub')  # extrai ID do usuário do token
        print(f"Usuário {user_id} tentando entrar no chat {chat_id}")  # exibe tentativa de entrada
        room = f"chat_{chat_id}"  # define nome da sala do chat
        join_room(room)  # adiciona cliente à sala
        print(f"Cliente {request.sid} entrou na sala {room}")  # exibe entrada na sala
        history = chat_service.get_chat_history(chat_id)  # busca histórico do chat
        emit('chat_history', {'chat_id': chat_id, 'history': history})  # envia histórico ao cliente
    except Exception as e:  # captura erros
        print(f"Erro na autenticação do socket ou ao entrar no chat: {e}")  # exibe erro

@socketio.on('send_message')  # evento de envio de mensagem
def handle_send_message(data):  # função handler de envio de mensagem
    token = data.get('token')  # extrai token JWT
    chat_id = data.get('chat_id')  # extrai ID do chat
    content = data.get('content')  # extrai conteúdo da mensagem
    if not token or not chat_id or not content:  # valida dados obrigatórios
        return  # ignora se dados incompletos
    try:  # tenta processar envio da mensagem
        decoded_token = decode_token(token)  # decodifica token JWT
        user_roles = decoded_token.get('roles', [])  # extrai papéis do usuário
        sender_type = 'customer' if 'customer' in user_roles else 'attendant'  # determina tipo do remetente
        chat_service.save_message(chat_id, sender_type, content)  # salva mensagem no banco
        message_data = {  # monta dados da mensagem
            'sender': sender_type,  # tipo do remetente
            'content': content,  # conteúdo da mensagem
            'timestamp': 'agora'  # timestamp atual
        }
        room = f"chat_{chat_id}"  # define sala do chat
        socketio.emit('new_message', message_data, room=room)  # envia mensagem para a sala
        print(f"Mensagem enviada para a sala {room}")  # exibe confirmação de envio
    except Exception as e:  # captura erros
        print(f"Erro ao enviar mensagem: {e}")  # exibe erro