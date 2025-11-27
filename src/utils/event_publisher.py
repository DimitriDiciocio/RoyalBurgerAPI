"""
Publicador de eventos do sistema.

Este módulo gerencia a publicação de eventos tanto para listeners locais
(em memória) quanto para clientes conectados via WebSocket (SocketIO).

Mantém a lógica em memória para listeners internos e adiciona a emissão
via SocketIO para notificações em tempo real.
"""

import logging
from typing import Dict, Any, Optional, Callable, List

logger = logging.getLogger(__name__)

# Dicionário para armazenar listeners locais (em memória)
_local_listeners: Dict[str, List[Callable]] = {}


def publish_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Publica um evento tanto para listeners locais quanto via SocketIO.
    
    Args:
        event_type: Tipo do evento (ex: 'order.created', 'order.status_changed')
        data: Dados do evento (dicionário)
    """
    # Publica para listeners locais (mantém compatibilidade com código existente)
    if event_type in _local_listeners:
        for listener in _local_listeners[event_type]:
            try:
                listener(event_type, data)
            except Exception as e:
                logger.error(f"Erro ao executar listener local para {event_type}: {e}", exc_info=True)
    
    # Publica via SocketIO
    try:
        # Importação tardia para evitar import circular
        from .. import socketio
        
        # Roteamento de eventos para salas apropriadas
        if event_type == 'order.created':
            # Emite para admin e cozinha
            socketio.emit('order.created', data, room='admin_room')
            socketio.emit('order.created', data, room='kitchen_room')
            logger.debug(f"Evento order.created emitido para admin_room e kitchen_room: {data}")
            
        elif event_type == 'order.status_changed':
            # Emite para admin
            socketio.emit('order.status_changed', data, room='admin_room')
            logger.info(f"Evento order.status_changed emitido para admin_room: {data}")
            
            # Emite para a sala pessoal do usuário dono do pedido
            user_id = data.get('user_id')
            if user_id:
                # Garantir que user_id seja inteiro
                user_id_int = int(user_id) if user_id else None
                if user_id_int:
                    user_room = f"user_{user_id_int}"
                    socketio.emit('order.status_changed', data, room=user_room)
                    logger.info(f"Evento order.status_changed emitido para {user_room}: {data}")
                else:
                    logger.warning(f"order.status_changed com user_id inválido: {user_id}")
            else:
                logger.warning(f"order.status_changed sem user_id: {data}")
                
        elif event_type == 'stock.alert':
            # Emite apenas para admin
            socketio.emit('stock.alert', data, room='admin_room')
            logger.debug(f"Evento stock.alert emitido para admin_room: {data}")
            
        elif event_type == 'table.status_changed':
            # Emite para admin
            socketio.emit('table.status_changed', data, room='admin_room')
            logger.debug(f"Evento table.status_changed emitido para admin_room: {data}")
            
        else:
            # Para outros tipos de evento, emite para admin_room por padrão
            socketio.emit(event_type, data, room='admin_room')
            logger.debug(f"Evento {event_type} emitido para admin_room: {data}")
            
    except ImportError:
        # Se socketio não estiver disponível, apenas loga aviso
        logger.warning("SocketIO não disponível. Eventos serão apenas locais.")
    except Exception as e:
        logger.error(f"Erro ao emitir evento via SocketIO: {e}", exc_info=True)


def publish_admin_event(event_type: str, data: Dict[str, Any]) -> None:
    """
    Método auxiliar para publicar eventos apenas para administradores.
    
    Args:
        event_type: Tipo do evento
        data: Dados do evento
    """
    try:
        from .. import socketio
        socketio.emit(event_type, data, room='admin_room')
        logger.debug(f"Evento admin {event_type} emitido: {data}")
    except ImportError:
        logger.warning("SocketIO não disponível. Evento admin não será emitido.")
    except Exception as e:
        logger.error(f"Erro ao emitir evento admin: {e}", exc_info=True)


def publish_user_event(user_id: int, event_type: str, data: Dict[str, Any]) -> None:
    """
    Método auxiliar para publicar eventos para um usuário específico.
    
    Args:
        user_id: ID do usuário destinatário
        event_type: Tipo do evento
        data: Dados do evento
    """
    try:
        from .. import socketio
        user_room = f"user_{user_id}"
        socketio.emit(event_type, data, room=user_room)
        logger.debug(f"Evento {event_type} emitido para {user_room}: {data}")
    except ImportError:
        logger.warning("SocketIO não disponível. Evento de usuário não será emitido.")
    except Exception as e:
        logger.error(f"Erro ao emitir evento de usuário: {e}", exc_info=True)


def subscribe(event_type: str, callback: Callable) -> None:
    """
    Registra um listener local para um tipo de evento.
    
    Args:
        event_type: Tipo do evento
        callback: Função callback que será chamada quando o evento for publicado
    """
    if event_type not in _local_listeners:
        _local_listeners[event_type] = []
    _local_listeners[event_type].append(callback)
    logger.debug(f"Listener registrado para evento: {event_type}")


def unsubscribe(event_type: str, callback: Callable) -> None:
    """
    Remove um listener local de um tipo de evento.
    
    Args:
        event_type: Tipo do evento
        callback: Função callback a ser removida
    """
    if event_type in _local_listeners:
        if callback in _local_listeners[event_type]:
            _local_listeners[event_type].remove(callback)
            logger.debug(f"Listener removido para evento: {event_type}")
