from flask import request  
from flask_jwt_extended import decode_token  
from flask_socketio import join_room, leave_room, emit  
from .. import socketio  
from ..services import chat_service  

@socketio.on('connect')  
def handle_connect():  
    print(f"Cliente conectado: {request.sid}")  

@socketio.on('disconnect')  
def handle_disconnect():  
    print(f"Cliente desconectado: {request.sid}")  

@socketio.on('join_chat')  
def handle_join_chat(data):  
    token = data.get('token')  
    chat_id = data.get('chat_id')  
    if not token or not chat_id:  
        return  
    try:  
        decoded_token = decode_token(token)  
        user_id = decoded_token.get('sub')  
        print(f"Usuário {user_id} tentando entrar no chat {chat_id}")  
        room = f"chat_{chat_id}"  
        join_room(room)  
        print(f"Cliente {request.sid} entrou na sala {room}")  
        history = chat_service.get_chat_history(chat_id)  
        emit('chat_history', {'chat_id': chat_id, 'history': history})  
    except Exception as e:  
        print(f"Erro na autenticação do socket ou ao entrar no chat: {e}")  

@socketio.on('send_message')  
def handle_send_message(data):  
    token = data.get('token')  
    chat_id = data.get('chat_id')  
    content = data.get('content')  
    if not token or not chat_id or not content:  
        return  
    try:  
        decoded_token = decode_token(token)  
        user_roles = decoded_token.get('roles', [])  
        sender_type = 'customer' if 'customer' in user_roles else 'attendant'  
        chat_service.save_message(chat_id, sender_type, content)  
        message_data = {  
            'sender': sender_type,  
            'content': content,  
            'timestamp': 'agora'  
        }
        room = f"chat_{chat_id}"  
        socketio.emit('new_message', message_data, room=room)  
        print(f"Mensagem enviada para a sala {room}")  
    except Exception as e:  
        print(f"Erro ao enviar mensagem: {e}")  
