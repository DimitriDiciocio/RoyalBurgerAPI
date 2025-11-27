"""
Rotas para eventos em tempo real via SSE (Server-Sent Events)
ALTERAÇÃO: DESCONTINUADO - Agora usamos WebSocket via SocketIO
Este arquivo está mantido apenas para referência histórica.
Para eventos em tempo real, use WebSocket através de SocketIO.
"""
from flask import Blueprint, Response, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
import time
import logging
from ..utils.event_publisher import publish_event
from ..services.auth_service import require_role

logger = logging.getLogger(__name__)

events_bp = Blueprint('events', __name__)


@events_bp.route('/stream', methods=['GET'])
def stream_events():
    """
    Endpoint SSE para receber eventos em tempo real.
    
    ALTERAÇÃO: DESCONTINUADO - Este endpoint não está mais funcional.
    Use WebSocket via SocketIO para eventos em tempo real.
    """
    # Retornar mensagem informando que SSE foi descontinuado
    def error_generator():
        yield f"data: {json.dumps({'type': 'error', 'message': 'SSE foi descontinuado. Use WebSocket via SocketIO para eventos em tempo real.'})}\n\n"
    return Response(error_generator(), mimetype='text/event-stream'), 410  # 410 Gone


@events_bp.route('/test', methods=['POST'])
@require_role('admin', 'manager')
def test_event():
    """
    Endpoint para testar publicação de eventos.
    ALTERAÇÃO: Útil para debug e testes
    """
    from ..utils.event_publisher import publish_event
    
    event_type = request.json.get('event_type', 'test.event')
    event_data = request.json.get('event_data', {'message': 'Teste de evento'})
    
    publish_event(event_type, event_data)
    
    return jsonify({
        'message': 'Evento publicado com sucesso',
        'event_type': event_type
    }), 200

