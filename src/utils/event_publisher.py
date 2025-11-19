"""
Sistema de Publicação de Eventos em Tempo Real
ALTERAÇÃO: Removido Redis - usando apenas sistema em memória para melhor performance
"""
import json
import logging
import threading
from typing import Dict, List, Callable, Any, Optional
from collections import defaultdict
from queue import Queue
from datetime import datetime

logger = logging.getLogger(__name__)

# ALTERAÇÃO: Sistema de eventos em memória
_event_listeners: Dict[str, List[Callable]] = defaultdict(list)
_event_queue: Queue = Queue()
_event_lock = threading.Lock()


def publish_event(event_type: str, event_data: Dict[str, Any], use_redis: bool = False):
    """
    Publica um evento no sistema.
    ALTERAÇÃO: Removido Redis - usando apenas sistema em memória
    
    Args:
        event_type: Tipo do evento (ex: 'purchase.created', 'financial_movement.updated')
        event_data: Dados do evento
        use_redis: Ignorado (mantido para compatibilidade, mas não usado)
    """
    event = {
        'type': event_type,
        'data': event_data,
        'timestamp': datetime.now().isoformat()
    }
    
    # ALTERAÇÃO: Usar apenas sistema em memória (removido Redis)
    with _event_lock:
        # Notificar listeners locais
        if event_type in _event_listeners:
            for listener in _event_listeners[event_type]:
                try:
                    listener(event)
                except Exception as e:
                    logger.error(f"Erro ao notificar listener: {e}", exc_info=True)
        
        # Também notificar listeners genéricos (para eventos que começam com prefixo)
        for registered_type, listeners in _event_listeners.items():
            if registered_type.endswith('*') and event_type.startswith(registered_type[:-1]):
                for listener in listeners:
                    try:
                        listener(event)
                    except Exception as e:
                        logger.error(f"Erro ao notificar listener genérico: {e}", exc_info=True)
        
        # Adicionar à fila para SSE
        _event_queue.put(event)


def subscribe_to_events(event_type: str, callback: Callable):
    """
    Inscreve um callback para receber eventos de um tipo específico.
    ALTERAÇÃO: Suporta padrões (ex: 'purchase.*' para todos os eventos de purchase)
    
    Args:
        event_type: Tipo do evento ou padrão (ex: 'purchase.*')
        callback: Função que recebe o evento como parâmetro
    """
    with _event_lock:
        _event_listeners[event_type].append(callback)
        logger.debug(f"Listener registrado para evento: {event_type}")


def get_event_queue() -> Queue:
    """
    Obtém a fila de eventos para SSE.
    ALTERAÇÃO: Retorna fila thread-safe de eventos
    """
    return _event_queue
