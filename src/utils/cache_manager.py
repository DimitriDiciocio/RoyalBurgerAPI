"""
Gerenciador de Cache em Memória
ALTERAÇÃO: Removido Redis - usando apenas cache em memória para melhor performance
ALTERAÇÃO: Adicionado métricas de performance do cache
"""
import logging
import time
import threading
from typing import Any, Optional, Dict
from functools import wraps
from collections import defaultdict

logger = logging.getLogger(__name__)

# Cache em memória
_memory_cache = {}
_memory_cache_timestamps = {}
_memory_cache_lock = threading.Lock()

# ALTERAÇÃO: Métricas de performance do cache (thread-safe)
_cache_metrics = {
    'hits': 0,
    'misses': 0,
    'sets': 0,
    'deletes': 0,
    'errors': 0,
    'total_get_time': 0.0,
    'total_set_time': 0.0,
    'total_delete_time': 0.0,
    'operation_counts_by_key_prefix': defaultdict(int)
}
_metrics_lock = threading.Lock()


class CacheManager:
    """
    Gerenciador de cache em memória.
    ALTERAÇÃO: Removido Redis - usando apenas memória para melhor performance
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        Inicializa o gerenciador de cache.
        
        Args:
            default_ttl: TTL padrão em segundos (300 = 5 minutos)
        """
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtém valor do cache.
        ALTERAÇÃO: Adicionado rastreamento de métricas de performance
        
        Args:
            key: Chave do cache
        
        Returns:
            Valor do cache ou None se não existir/expirado
        """
        start_time = time.time()
        result = None
        is_hit = False
        
        try:
            with _memory_cache_lock:
                if key in _memory_cache:
                    # Verificar se expirou
                    if key in _memory_cache_timestamps:
                        if time.time() < _memory_cache_timestamps[key]:
                            result = _memory_cache[key]
                            is_hit = True
                        else:
                            # Expirou, remover
                            del _memory_cache[key]
                            del _memory_cache_timestamps[key]
                            result = None
                    else:
                        result = _memory_cache[key]
                        is_hit = True
        finally:
            # ALTERAÇÃO: Atualizar métricas de performance
            elapsed_time = time.time() - start_time
            with _metrics_lock:
                if is_hit:
                    _cache_metrics['hits'] += 1
                else:
                    _cache_metrics['misses'] += 1
                _cache_metrics['total_get_time'] += elapsed_time
                # Rastrear operações por prefixo de chave
                key_prefix = key.split(':')[0] if ':' in key else key[:20]
                _cache_metrics['operation_counts_by_key_prefix'][f'get:{key_prefix}'] += 1
        
        return result
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """
        Define valor no cache.
        ALTERAÇÃO: Adicionado rastreamento de métricas de performance
        
        Args:
            key: Chave do cache
            value: Valor a armazenar
            ttl: Time to live em segundos (None para usar default_ttl)
        
        Returns:
            True se sucesso, False caso contrário
        """
        start_time = time.time()
        success = False
        
        try:
            ttl = ttl or self.default_ttl
            
            with _memory_cache_lock:
                _memory_cache[key] = value
                _memory_cache_timestamps[key] = time.time() + ttl
            success = True
        finally:
            # ALTERAÇÃO: Atualizar métricas de performance
            elapsed_time = time.time() - start_time
            with _metrics_lock:
                if success:
                    _cache_metrics['sets'] += 1
                    _cache_metrics['total_set_time'] += elapsed_time
                else:
                    _cache_metrics['errors'] += 1
                # Rastrear operações por prefixo de chave
                key_prefix = key.split(':')[0] if ':' in key else key[:20]
                _cache_metrics['operation_counts_by_key_prefix'][f'set:{key_prefix}'] += 1
        
        return success
    
    def delete(self, key: str) -> bool:
        """
        Remove valor do cache.
        ALTERAÇÃO: Adicionado rastreamento de métricas de performance
        
        Args:
            key: Chave do cache
        
        Returns:
            True se sucesso, False caso contrário
        """
        start_time = time.time()
        success = False
        
        try:
            with _memory_cache_lock:
                if key in _memory_cache:
                    del _memory_cache[key]
                if key in _memory_cache_timestamps:
                    del _memory_cache_timestamps[key]
            success = True
        finally:
            # ALTERAÇÃO: Atualizar métricas de performance
            elapsed_time = time.time() - start_time
            with _metrics_lock:
                if success:
                    _cache_metrics['deletes'] += 1
                    _cache_metrics['total_delete_time'] += elapsed_time
                else:
                    _cache_metrics['errors'] += 1
                # Rastrear operações por prefixo de chave
                key_prefix = key.split(':')[0] if ':' in key else key[:20]
                _cache_metrics['operation_counts_by_key_prefix'][f'delete:{key_prefix}'] += 1
        
        return success
    
    def clear_pattern(self, pattern: str) -> int:
        """
        Remove todas as chaves que correspondem ao padrão.
        ALTERAÇÃO: Adicionado rastreamento de métricas de performance
        
        Args:
            pattern: Padrão de chaves (ex: 'financial_movements:*')
        
        Returns:
            Número de chaves removidas
        """
        count = 0
        
        with _memory_cache_lock:
            # ALTERAÇÃO: Usar list comprehension com filtro direto para melhor performance
            prefix = pattern.replace('*', '')
            keys_to_delete = [k for k in _memory_cache.keys() if prefix in k]
            for key in keys_to_delete:
                del _memory_cache[key]
                if key in _memory_cache_timestamps:
                    del _memory_cache_timestamps[key]
            count = len(keys_to_delete)
        
        # ALTERAÇÃO: Atualizar métricas de performance
        with _metrics_lock:
            # Rastrear operações por prefixo de chave
            pattern_prefix = pattern.split(':')[0] if ':' in pattern else pattern[:20]
            _cache_metrics['operation_counts_by_key_prefix'][f'clear_pattern:{pattern_prefix}'] += 1
            # Adicionar contagem de deletes (clear_pattern é uma operação de delete em lote)
            if count > 0:
                _cache_metrics['deletes'] += count
        
        return count
    
    def exists(self, key: str) -> bool:
        """
        Verifica se chave existe no cache.
        
        Args:
            key: Chave do cache
        
        Returns:
            True se existe, False caso contrário
        """
        with _memory_cache_lock:
            if key in _memory_cache:
                # Verificar se expirou
                if key in _memory_cache_timestamps:
                    if time.time() < _memory_cache_timestamps[key]:
                        return True
                    else:
                        del _memory_cache[key]
                        del _memory_cache_timestamps[key]
                else:
                    return True
        return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Obtém métricas de performance do cache.
        ALTERAÇÃO: Implementado método para obter estatísticas do cache
        
        Returns:
            Dicionário com métricas de performance:
            - hits: Número de cache hits
            - misses: Número de cache misses
            - sets: Número de operações de set
            - deletes: Número de operações de delete
            - errors: Número de erros
            - hit_rate: Taxa de sucesso (hits / (hits + misses))
            - avg_get_time: Tempo médio de operações get (ms)
            - avg_set_time: Tempo médio de operações set (ms)
            - avg_delete_time: Tempo médio de operações delete (ms)
            - total_operations: Total de operações
            - cache_type: Tipo de cache usado ('memory')
            - operation_counts_by_prefix: Contadores por prefixo de chave
        """
        with _metrics_lock:
            total_gets = _cache_metrics['hits'] + _cache_metrics['misses']
            total_operations = (
                _cache_metrics['hits'] + 
                _cache_metrics['misses'] + 
                _cache_metrics['sets'] + 
                _cache_metrics['deletes']
            )
            
            # Calcular taxa de sucesso
            hit_rate = 0.0
            if total_gets > 0:
                hit_rate = (_cache_metrics['hits'] / total_gets) * 100
            
            # Calcular tempos médios (em milissegundos)
            avg_get_time = 0.0
            if total_gets > 0:
                avg_get_time = (_cache_metrics['total_get_time'] / total_gets) * 1000
            
            avg_set_time = 0.0
            if _cache_metrics['sets'] > 0:
                avg_set_time = (_cache_metrics['total_set_time'] / _cache_metrics['sets']) * 1000
            
            avg_delete_time = 0.0
            if _cache_metrics['deletes'] > 0:
                avg_delete_time = (_cache_metrics['total_delete_time'] / _cache_metrics['deletes']) * 1000
            
            # Converter defaultdict para dict para serialização
            operation_counts = dict(_cache_metrics['operation_counts_by_key_prefix'])
            
            return {
                'hits': _cache_metrics['hits'],
                'misses': _cache_metrics['misses'],
                'sets': _cache_metrics['sets'],
                'deletes': _cache_metrics['deletes'],
                'errors': _cache_metrics['errors'],
                'hit_rate': round(hit_rate, 2),
                'avg_get_time_ms': round(avg_get_time, 3),
                'avg_set_time_ms': round(avg_set_time, 3),
                'avg_delete_time_ms': round(avg_delete_time, 3),
                'total_operations': total_operations,
                'cache_type': 'memory',
                'operation_counts_by_prefix': operation_counts
            }
    
    def reset_metrics(self) -> None:
        """
        Reseta todas as métricas de performance.
        ALTERAÇÃO: Implementado método para resetar métricas
        """
        with _metrics_lock:
            _cache_metrics['hits'] = 0
            _cache_metrics['misses'] = 0
            _cache_metrics['sets'] = 0
            _cache_metrics['deletes'] = 0
            _cache_metrics['errors'] = 0
            _cache_metrics['total_get_time'] = 0.0
            _cache_metrics['total_set_time'] = 0.0
            _cache_metrics['total_delete_time'] = 0.0
            _cache_metrics['operation_counts_by_key_prefix'].clear()
            logger.info("Métricas de cache resetadas")


# Instância global do cache manager
_cache_manager_instance = None


def get_cache_manager() -> CacheManager:
    """
    Obtém instância global do cache manager (singleton).
    ALTERAÇÃO: Implementado singleton para reutilização
    """
    global _cache_manager_instance
    if _cache_manager_instance is None:
        _cache_manager_instance = CacheManager()
    return _cache_manager_instance


def cache_result(key_prefix: str, ttl: int = 300, key_builder: callable = None):
    """
    Decorator para cachear resultado de função.
    ALTERAÇÃO: Implementado decorator para facilitar cache de funções
    
    Args:
        key_prefix: Prefixo da chave do cache
        ttl: Time to live em segundos
        key_builder: Função para construir chave baseada nos argumentos
    
    Exemplo:
        @cache_result('financial_movements', ttl=60)
        def get_movements(filters):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = get_cache_manager()
            
            # Construir chave do cache
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Chave padrão baseada em args e kwargs
                key_parts = [key_prefix]
                if args:
                    key_parts.append(str(hash(str(args))))
                if kwargs:
                    key_parts.append(str(hash(str(sorted(kwargs.items())))))
                cache_key = ':'.join(key_parts)
            
            # Tentar obter do cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_result
            
            # Executar função e cachear resultado
            logger.debug(f"Cache miss: {cache_key}")
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator
