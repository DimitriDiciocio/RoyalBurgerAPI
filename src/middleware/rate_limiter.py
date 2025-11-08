"""
Middleware de Rate Limiting para proteção contra brute force e abuse.
Implementação básica usando cache em memória (para desenvolvimento).
Em produção, considere usar Redis para cache distribuído.
"""
import time
from functools import wraps
from flask import request, jsonify
from collections import defaultdict
import threading

# Cache em memória para rate limiting
_rate_limit_cache = defaultdict(list)
_rate_limit_lock = threading.Lock()


def get_client_identifier():
    """
    Obtém identificador único do cliente para rate limiting.
    Prioriza IP real (atrás de proxy) e fallback para IP direto.
    """
    # Tenta obter IP real se estiver atrás de proxy
    if request.headers.get('X-Forwarded-For'):
        # Pega o primeiro IP da cadeia (cliente original)
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr or 'unknown'


def rate_limit(max_requests: int = 5, window_seconds: int = 60, per: str = 'ip'):
    """
    Decorator para rate limiting.
    
    Args:
        max_requests: Número máximo de requisições permitidas
        window_seconds: Janela de tempo em segundos
        per: Base para rate limiting ('ip' ou 'user')
    
    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Obtém identificador do cliente
            if per == 'ip':
                identifier = get_client_identifier()
            elif per == 'user':
                # Se usar rate limit por usuário, precisa do user_id do JWT
                from flask_jwt_extended import get_jwt_identity
                try:
                    identifier = get_jwt_identity() or get_client_identifier()
                except Exception:
                    # Se não conseguir obter user_id do JWT, usa IP como fallback
                    identifier = get_client_identifier()
            else:
                identifier = get_client_identifier()
            
            # Cria chave única para este endpoint + identificador
            endpoint_key = f"{request.endpoint}:{identifier}"
            current_time = time.time()
            
            # Limpa requisições antigas da janela
            with _rate_limit_lock:
                # Remove requisições fora da janela de tempo
                _rate_limit_cache[endpoint_key] = [
                    req_time for req_time in _rate_limit_cache[endpoint_key]
                    if current_time - req_time < window_seconds
                ]
                
                # Verifica se excedeu o limite
                if len(_rate_limit_cache[endpoint_key]) >= max_requests:
                    # Calcula tempo até poder fazer nova requisição
                    oldest_request = min(_rate_limit_cache[endpoint_key])
                    retry_after = int(window_seconds - (current_time - oldest_request)) + 1
                    
                    return jsonify({
                        "error": "Muitas requisições. Tente novamente mais tarde.",
                        "code": "RATE_LIMIT_EXCEEDED",
                        "retry_after": retry_after
                    }), 429
                
                # Adiciona requisição atual
                _rate_limit_cache[endpoint_key].append(current_time)
            
            # Executa a função normalmente
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def clear_rate_limit_cache():
    """Limpa o cache de rate limiting (útil para testes)"""
    global _rate_limit_cache
    with _rate_limit_lock:
        _rate_limit_cache.clear()


def get_rate_limit_stats(identifier: str = None):
    """
    Obtém estatísticas de rate limiting (útil para debugging).
    
    Args:
        identifier: Identificador do cliente (opcional)
    
    Returns:
        dict com estatísticas
    """
    with _rate_limit_lock:
        if identifier:
            # Retorna stats para um identificador específico
            stats = {}
            for key, requests in _rate_limit_cache.items():
                if identifier in key:
                    stats[key] = {
                        "requests": len(requests),
                        "oldest": min(requests) if requests else None,
                        "newest": max(requests) if requests else None
                    }
            return stats
        else:
            # Retorna stats gerais
            return {
                "total_endpoints": len(_rate_limit_cache),
                "total_requests": sum(len(reqs) for reqs in _rate_limit_cache.values())
            }

