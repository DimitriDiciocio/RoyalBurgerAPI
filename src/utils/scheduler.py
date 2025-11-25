"""
Scheduler de Jobs Periódicos
Gerencia tarefas agendadas como limpeza de reservas temporárias expiradas
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import atexit

logger = logging.getLogger(__name__)

# Instância global do scheduler
_scheduler = None


def init_scheduler(app=None):
    """
    Inicializa e configura o scheduler de jobs periódicos.
    
    Args:
        app: Instância do Flask app (opcional)
    
    Returns:
        BackgroundScheduler: Instância do scheduler
    """
    global _scheduler
    
    if _scheduler is not None:
        logger.warning("Scheduler já foi inicializado. Ignorando nova inicialização.")
        return _scheduler
    
    logger.info("Inicializando scheduler de jobs periódicos...")
    
    # Cria scheduler com fuso horário local
    _scheduler = BackgroundScheduler(
        daemon=True,
        timezone='America/Sao_Paulo'  # Ajuste para o fuso horário correto
    )
    
    # Adiciona listener para logs de execução
    _scheduler.add_listener(
        _job_executed_listener,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
    )
    
    # Registra jobs
    _register_jobs()
    
    # Inicia o scheduler
    _scheduler.start()
    logger.info("Scheduler iniciado com sucesso")
    
    # Garante que o scheduler será finalizado ao encerrar a aplicação
    atexit.register(lambda: shutdown_scheduler())
    
    return _scheduler


def _register_jobs():
    """
    Registra todos os jobs periódicos do sistema.
    """
    # Job 1: Limpar reservas temporárias expiradas
    _scheduler.add_job(
        func=cleanup_expired_reservations_job,
        trigger=IntervalTrigger(minutes=5),  # Executa a cada 5 minutos
        id='cleanup_expired_reservations',
        name='Limpar Reservas Temporárias Expiradas',
        replace_existing=True,
        max_instances=1,  # Evita execuções simultâneas
        coalesce=True,  # Se perder execução, executa apenas uma vez ao invés de todas perdidas
        misfire_grace_time=300  # 5 minutos de tolerância para execuções atrasadas
    )
    
    logger.info("Jobs periódicos registrados:")
    logger.info("  - cleanup_expired_reservations: a cada 5 minutos")
    
    # ALTERAÇÃO: Outros jobs podem ser adicionados aqui no futuro
    # Exemplo:
    # _scheduler.add_job(
    #     func=send_pending_notifications_job,
    #     trigger=IntervalTrigger(minutes=10),
    #     id='send_pending_notifications',
    #     name='Enviar Notificações Pendentes',
    #     replace_existing=True
    # )


def cleanup_expired_reservations_job():
    """
    Job periódico para limpar reservas temporárias expiradas.
    Executa a cada 5 minutos.
    """
    try:
        # ALTERAÇÃO: Import local para evitar circular dependency
        from ..services import stock_service
        
        logger.info("[JOB] Iniciando limpeza de reservas temporárias expiradas...")
        
        # Chama função de limpeza (sem parâmetros = limpa apenas expiradas)
        success, cleared_count, error_code, message = stock_service.clear_temporary_reservations()
        
        if not success:
            logger.error(
                f"[JOB] Erro ao limpar reservas temporárias: {message} (código: {error_code})"
            )
            return
        
        if cleared_count > 0:
            logger.info(
                f"[JOB] Limpeza concluída: {cleared_count} reservas temporárias expiradas removidas"
            )
        else:
            logger.debug("[JOB] Limpeza concluída: nenhuma reserva expirada encontrada")
    
    except Exception as e:
        logger.error(
            f"[JOB] Erro inesperado ao executar job de limpeza de reservas: {e}",
            exc_info=True
        )


def _job_executed_listener(event):
    """
    Listener para eventos de execução de jobs.
    Registra sucesso e falhas para monitoramento.
    
    Args:
        event: Evento do APScheduler
    """
    if event.exception:
        logger.error(
            f"[SCHEDULER] Job '{event.job_id}' falhou com exceção: {event.exception}",
            exc_info=True
        )
    else:
        logger.debug(f"[SCHEDULER] Job '{event.job_id}' executado com sucesso")


def get_scheduler():
    """
    Retorna a instância global do scheduler.
    
    Returns:
        BackgroundScheduler: Instância do scheduler ou None se não inicializado
    """
    return _scheduler


def shutdown_scheduler():
    """
    Finaliza o scheduler de forma limpa.
    """
    global _scheduler
    
    if _scheduler is not None:
        logger.info("Finalizando scheduler de jobs periódicos...")
        _scheduler.shutdown(wait=True)
        _scheduler = None
        logger.info("Scheduler finalizado")


def get_jobs_status():
    """
    Retorna status de todos os jobs agendados.
    
    Returns:
        list: Lista de dicionários com informações dos jobs
    """
    if _scheduler is None:
        return []
    
    jobs_info = []
    for job in _scheduler.get_jobs():
        jobs_info.append({
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger),
            'max_instances': job.max_instances,
            'coalesce': job.coalesce
        })
    
    return jobs_info


def pause_job(job_id):
    """
    Pausa um job específico.
    
    Args:
        job_id: ID do job
    
    Returns:
        bool: True se pausado com sucesso, False caso contrário
    """
    if _scheduler is None:
        return False
    
    try:
        _scheduler.pause_job(job_id)
        logger.info(f"Job '{job_id}' pausado")
        return True
    except Exception as e:
        logger.error(f"Erro ao pausar job '{job_id}': {e}")
        return False


def resume_job(job_id):
    """
    Resume um job pausado.
    
    Args:
        job_id: ID do job
    
    Returns:
        bool: True se resumido com sucesso, False caso contrário
    """
    if _scheduler is None:
        return False
    
    try:
        _scheduler.resume_job(job_id)
        logger.info(f"Job '{job_id}' resumido")
        return True
    except Exception as e:
        logger.error(f"Erro ao resumir job '{job_id}': {e}")
        return False


def run_job_now(job_id):
    """
    Executa um job imediatamente (fora do agendamento).
    
    Args:
        job_id: ID do job
    
    Returns:
        bool: True se executado com sucesso, False caso contrário
    """
    if _scheduler is None:
        return False
    
    try:
        job = _scheduler.get_job(job_id)
        if job:
            job.func()
            logger.info(f"Job '{job_id}' executado manualmente")
            return True
        else:
            logger.warning(f"Job '{job_id}' não encontrado")
            return False
    except Exception as e:
        logger.error(f"Erro ao executar job '{job_id}' manualmente: {e}")
        return False

