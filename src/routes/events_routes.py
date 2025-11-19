"""
Rotas para eventos em tempo real via SSE (Server-Sent Events)
ALTERAÇÃO: Implementado para atualizações em tempo real no frontend
"""
from flask import Blueprint, Response, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
import time
import logging
from ..utils.event_publisher import get_event_queue, subscribe_to_events
from ..services.auth_service import require_role

logger = logging.getLogger(__name__)

events_bp = Blueprint('events', __name__)


@events_bp.route('/stream', methods=['GET'])
def stream_events():
    """
    Endpoint SSE para receber eventos em tempo real.
    ALTERAÇÃO: Implementado Server-Sent Events para atualizações em tempo real
    
    O cliente mantém uma conexão HTTP aberta e recebe eventos conforme são publicados.
    
    ALTERAÇÃO: Autenticação via query param (token) porque EventSource não suporta headers customizados
    """
    # ALTERAÇÃO: Verificar autenticação via query param ou header
    token = request.args.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not token:
        # ALTERAÇÃO: Retornar erro SSE formatado
        def error_generator():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Token de autenticação necessário'})}\n\n"
        return Response(error_generator(), mimetype='text/event-stream'), 401
    
    # ALTERAÇÃO: Validar token JWT
    try:
        from flask_jwt_extended import decode_token
        from flask import current_app
        decoded = decode_token(token)
        user_id = decoded.get('sub')
        if not user_id:
            def error_generator():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Token inválido'})}\n\n"
            return Response(error_generator(), mimetype='text/event-stream'), 401
    except Exception as e:
        logger.warning(f"Token inválido no SSE: {e}")
        def error_generator():
            yield f"data: {json.dumps({'type': 'error', 'message': 'Token inválido'})}\n\n"
        return Response(error_generator(), mimetype='text/event-stream'), 401
    
    def event_generator():
        """Generator que produz eventos SSE"""
        event_queue = get_event_queue()
        
        # ALTERAÇÃO: Enviar evento de conexão inicial
        yield f"data: {json.dumps({'type': 'connected', 'message': 'Conectado ao stream de eventos'})}\n\n"
        
        # ALTERAÇÃO: Enviar heartbeat a cada 30 segundos para manter conexão viva
        last_heartbeat = time.time()
        heartbeat_interval = 30
        
        try:
            while True:
                # ALTERAÇÃO: Verificar se há eventos na fila (com timeout para permitir heartbeat)
                try:
                    event = event_queue.get(timeout=1)
                    yield f"data: {json.dumps(event)}\n\n"
                except:
                    # Timeout - verificar se precisa enviar heartbeat
                    current_time = time.time()
                    if current_time - last_heartbeat >= heartbeat_interval:
                        yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': current_time})}\n\n"
                        last_heartbeat = current_time
                    continue
        except GeneratorExit:
            logger.debug("Cliente desconectou do stream de eventos")
        except Exception as e:
            logger.error(f"Erro no stream de eventos: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    # ALTERAÇÃO: Retornar Response SSE com headers apropriados
    return Response(
        event_generator(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Desabilita buffering no nginx
            'Connection': 'keep-alive',
        }
    )


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

