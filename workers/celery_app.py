"""
workers/celery_app.py — Celery Application para Produção
=========================================================
Tasks distribuídas para: IA, voz, sync, rotinas, monitoramento.
Broker: Redis | Backend: Redis | DB: PostgreSQL via asyncpg
"""
import asyncio
import logging
import os
from functools import wraps
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready, worker_shutdown
from kombu import Queue, Exchange

logger = logging.getLogger(__name__)

# ─── Configuração ─────────────────────────────────────────────────────────────
BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/1"))
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://redis:6379/2"))

app = Celery(
    "personal-ai-mobile",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

# ─── Queues ───────────────────────────────────────────────────────────────────
default_exchange = Exchange("default", type="direct")
ai_exchange      = Exchange("ai",      type="direct")
voice_exchange   = Exchange("voice",   type="direct")

app.conf.task_queues = (
    Queue("default",    default_exchange, routing_key="default",    queue_arguments={"x-max-priority": 10}),
    Queue("ai",         ai_exchange,      routing_key="ai",         queue_arguments={"x-max-priority": 10}),
    Queue("voice",      voice_exchange,   routing_key="voice"),
    Queue("sync",       default_exchange, routing_key="sync"),
    Queue("routines",   default_exchange, routing_key="routines"),
    Queue("monitoring", default_exchange, routing_key="monitoring"),
)

app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

app.conf.task_routes = {
    "workers.celery_app.task_ai_chat":          {"queue": "ai"},
    "workers.celery_app.task_ai_generate":      {"queue": "ai"},
    "workers.celery_app.task_tts_generate":     {"queue": "voice"},
    "workers.celery_app.task_stt_process":      {"queue": "voice"},
    "workers.celery_app.task_sync_pending":     {"queue": "sync"},
    "workers.celery_app.task_run_routine":      {"queue": "routines"},
    "workers.celery_app.task_collect_metrics":  {"queue": "monitoring"},
    "workers.celery_app.task_self_improvement": {"queue": "monitoring"},
}

# ─── Configuração Geral ────────────────────────────────────────────────────────
app.conf.update(
    # Serialização
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Resultados
    result_expires=3600,           # 1 hora
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,
    # Workers
    worker_prefetch_multiplier=1,   # Fair dispatch
    worker_max_tasks_per_child=100,
    # Heartbeat
    broker_heartbeat=30,
    broker_connection_retry_on_startup=True,
)

# ─── Beat Schedule (tarefas recorrentes) ──────────────────────────────────────
app.conf.beat_schedule = {
    # Coleta métricas a cada minuto
    "collect-metrics-every-minute": {
        "task": "workers.celery_app.task_collect_metrics",
        "schedule": 60.0,
        "options": {"queue": "monitoring"},
    },
    # Sincroniza itens pendentes a cada 30s
    "sync-pending-every-30s": {
        "task": "workers.celery_app.task_sync_pending",
        "schedule": 30.0,
        "options": {"queue": "sync"},
    },
    # Verifica melhorias a cada 6 horas
    "self-improvement-check": {
        "task": "workers.celery_app.task_self_improvement",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "monitoring"},
    },
    # Limpeza de métricas antigas diariamente às 3h
    "cleanup-old-metrics": {
        "task": "workers.celery_app.task_cleanup_old_data",
        "schedule": crontab(minute=0, hour=3),
        "options": {"queue": "monitoring"},
    },
    # Briefing matinal às 7h (dias úteis)
    "morning-briefing": {
        "task": "workers.celery_app.task_morning_briefing",
        "schedule": crontab(minute=0, hour=7, day_of_week="1-5"),
        "options": {"queue": "routines"},
    },
    # Resumo noturno às 21h
    "evening-summary": {
        "task": "workers.celery_app.task_evening_summary",
        "schedule": crontab(minute=0, hour=21),
        "options": {"queue": "routines"},
    },
}


# ─── Helper async ─────────────────────────────────────────────────────────────
def run_async(coro):
    """Executa coroutine em novo event loop (worker é síncrono)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Tasks ────────────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="workers.celery_app.task_ai_chat",
    queue="ai",
    max_retries=3,
    default_retry_delay=5,
    soft_time_limit=90,
    time_limit=120,
)
def task_ai_chat(self, message: str, conversation_id: str = None,
                 provider: str = None, platform: str = "celery"):
    """Processa mensagem de chat via IA."""
    try:
        async def _run():
            from database.db import init_db
            await init_db()
            from services.chat_service import chat_service
            await chat_service.initialize()
            return await chat_service.process_message(
                message,
                conversation_id=conversation_id,
                platform=platform,
            )
        return run_async(_run())
    except Exception as exc:
        logger.error(f"task_ai_chat error: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@app.task(
    bind=True,
    name="workers.celery_app.task_ai_generate",
    queue="ai",
    max_retries=2,
    soft_time_limit=180,
    time_limit=240,
)
def task_ai_generate(self, prompt: str, provider: str = None,
                     system: str = None, task_type: str = "generate"):
    """Gera texto via IA (não-chat)."""
    try:
        async def _run():
            from database.db import init_db
            await init_db()
            from services.provider_router import provider_router
            return await provider_router.generate(
                prompt=prompt,
                system=system,
                provider_name=provider,
                task_type=task_type,
            )
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)


@app.task(
    bind=True,
    name="workers.celery_app.task_tts_generate",
    queue="voice",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def task_tts_generate(self, text: str, voice: str = None, output_path: str = None):
    """Gera áudio TTS."""
    try:
        async def _run():
            from services.voice_service import voice_service
            await voice_service.initialize()
            return await voice_service.text_to_speech(text, voice=voice, output_path=output_path)
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=3)


@app.task(
    bind=True,
    name="workers.celery_app.task_stt_process",
    queue="voice",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def task_stt_process(self, audio_path: str):
    """Transcreve áudio para texto."""
    try:
        async def _run():
            from services.voice_service import voice_service
            await voice_service.initialize()
            return await voice_service.speech_to_text(audio_path)
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=3)


@app.task(
    name="workers.celery_app.task_sync_pending",
    queue="sync",
    soft_time_limit=55,
    time_limit=60,
)
def task_sync_pending():
    """Sincroniza itens pendentes com servidor pai."""
    async def _run():
        from database.db import init_db
        await init_db()
        from services.sync_service import sync_service
        await sync_service.initialize()
        online = await sync_service.check_connectivity()
        if online:
            return await sync_service.sync_pending()
        return {"synced": 0, "online": False}
    return run_async(_run())


@app.task(
    bind=True,
    name="workers.celery_app.task_run_routine",
    queue="routines",
    max_retries=1,
    soft_time_limit=280,
    time_limit=300,
)
def task_run_routine(self, routine_id: str):
    """Executa uma rotina agendada."""
    try:
        async def _run():
            from database.db import init_db
            await init_db()
            from services.routine_service import routine_service
            await routine_service.initialize()
            return await routine_service.execute_routine(routine_id)
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)


@app.task(
    name="workers.celery_app.task_collect_metrics",
    queue="monitoring",
    soft_time_limit=55,
    time_limit=60,
)
def task_collect_metrics():
    """Coleta e armazena métricas do sistema."""
    async def _run():
        from database.db import init_db
        await init_db()
        from services.self_monitoring import self_monitoring
        await self_monitoring.initialize()
        metrics = await self_monitoring.collect_metrics()
        await self_monitoring.save_metrics(metrics)
        return metrics
    return run_async(_run())


@app.task(
    name="workers.celery_app.task_self_improvement",
    queue="monitoring",
    soft_time_limit=350,
    time_limit=360,
)
def task_self_improvement():
    """Verifica e propõe melhorias automáticas."""
    async def _run():
        from database.db import init_db
        await init_db()
        from services.self_monitoring import self_monitoring
        await self_monitoring.initialize()
        return await self_monitoring.run_improvement_cycle()
    return run_async(_run())


@app.task(
    name="workers.celery_app.task_cleanup_old_data",
    queue="monitoring",
    soft_time_limit=120,
    time_limit=180,
)
def task_cleanup_old_data():
    """Remove dados antigos para liberar espaço."""
    async def _run():
        from database.db import init_db, db_execute
        await init_db()
        # Remove métricas com mais de 7 dias
        await db_execute(
            "DELETE FROM monitoring_metrics WHERE recorded_at < NOW() - INTERVAL '7 days'"
            if hasattr(__import__('config', fromlist=['settings']).settings, 'is_postgres') and
               __import__('config', fromlist=['settings']).settings.is_postgres
            else "DELETE FROM monitoring_metrics WHERE recorded_at < datetime('now', '-7 days')"
        )
        # Remove logs de ações com mais de 30 dias
        await db_execute(
            "DELETE FROM action_logs WHERE executed_at < NOW() - INTERVAL '30 days'"
            if __import__('config', fromlist=['settings']).settings.is_postgres
            else "DELETE FROM action_logs WHERE executed_at < datetime('now', '-30 days')"
        )
        return {"cleaned": True}
    return run_async(_run())


@app.task(
    name="workers.celery_app.task_morning_briefing",
    queue="routines",
    soft_time_limit=120,
    time_limit=150,
)
def task_morning_briefing():
    """Gera briefing matinal e notifica via WebSocket."""
    async def _run():
        from database.db import init_db
        await init_db()
        from services.chat_service import chat_service
        await chat_service.initialize()
        result = await chat_service.process_message(
            "Gere um briefing matinal com resumo do dia, compromissos e sugestões.",
            platform="routine",
        )
        return result
    return run_async(_run())


@app.task(
    name="workers.celery_app.task_evening_summary",
    queue="routines",
    soft_time_limit=120,
    time_limit=150,
)
def task_evening_summary():
    """Gera resumo noturno das atividades do dia."""
    async def _run():
        from database.db import init_db
        await init_db()
        from services.chat_service import chat_service
        await chat_service.initialize()
        result = await chat_service.process_message(
            "Gere um resumo das atividades de hoje e sugira preparações para amanhã.",
            platform="routine",
        )
        return result
    return run_async(_run())


# ─── Signals ──────────────────────────────────────────────────────────────────
@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    logger.info("🚀 Celery Worker pronto — Personal AI Mobile")


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    logger.info("🛑 Celery Worker encerrando")
