"""
Gerenciador de eventos de sistema via WebSocket.

Este módulo gerencia a conexão global e a entrada em salas (rooms) de sistema.
Diferente do chat, que entra na sala de uma conversa específica, aqui o usuário
entra na sala do seu "cargo" ou na sua sala "pessoal".
"""

from flask import request
from flask_jwt_extended import decode_token
from flask_socketio import join_room, leave_room, emit
from .. import socketio
import logging

logger = logging.getLogger(__name__)


@socketio.on('connect')
def handle_system_connect(auth=None):
    """
    Evento de conexão global do sistema.
    
    Autenticação: Lê o token JWT da query string ou do auth header do handshake.
    Decodifica o token e extrai user_id e roles.
    
    Lógica de Salas:
    - Todos entram na sala: user_{user_id} (para receber notificações pessoais)
    - Se role contém 'admin' ou 'manager': Entrar na sala admin_room
    - Se role contém 'kitchen' ou 'chef': Entrar na sala kitchen_room
    """
    try:
        # Tenta obter o token da query string primeiro
        token = request.args.get('token')
        
        # Se não encontrou na query string, tenta no header Authorization
        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        # Se ainda não encontrou, tenta no objeto auth (passado pelo cliente)
        if not token and auth:
            token = auth.get('token')
        
        if not token:
            logger.warning(f"Tentativa de conexão sem token: {request.sid}")
            return False  # Rejeita a conexão
        
        # Decodifica e valida o token
        try:
            decoded_token = decode_token(token)
            user_id = decoded_token.get('sub')
            roles = decoded_token.get('roles', [])
            
            if not user_id:
                logger.warning(f"Token sem user_id: {request.sid}")
                return False
            
            # Converte roles para lista se for string
            if isinstance(roles, str):
                roles = [roles]
            elif not isinstance(roles, list):
                roles = []
            
            # Converte roles para minúsculas para comparação case-insensitive
            roles_lower = [role.lower() if isinstance(role, str) else str(role).lower() for role in roles]
            
            # Lista de salas que o usuário entrará
            rooms_joined = []
            
            # Todos entram na sala pessoal
            personal_room = f"user_{user_id}"
            join_room(personal_room)
            rooms_joined.append(personal_room)
            
            # Verifica roles para salas específicas
            if any(role in roles_lower for role in ['admin', 'manager']):
                join_room('admin_room')
                rooms_joined.append('admin_room')
            
            if any(role in roles_lower for role in ['kitchen', 'chef', 'cozinha']):
                join_room('kitchen_room')
                rooms_joined.append('kitchen_room')
            
            logger.info(f"Usuário {user_id} conectado e adicionado às salas: {', '.join(rooms_joined)}")
            
            # Emite confirmação de conexão
            emit('system_connected', {
                'user_id': user_id,
                'rooms': rooms_joined,
                'message': 'Conectado ao sistema de notificações'
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao decodificar token: {e}", exc_info=True)
            return False
            
    except Exception as e:
        logger.error(f"Erro na conexão do sistema: {e}", exc_info=True)
        return False


@socketio.on('disconnect')
def handle_system_disconnect():
    """
    Evento de desconexão do sistema.
    """
    logger.info(f"Cliente desconectado do sistema: {request.sid}")

