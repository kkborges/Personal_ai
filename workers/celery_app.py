"""
Personal AI Mobile — Celery Application
========================================
Workers assíncronos para substituir/complementar APScheduler em produção.

Filas disponíveis:
  - default:   tarefas gerais
  - ai:        chamadas a LLMs (OpenAI, Anthropic, Gemini, Ollama)
  - voice:     TTS e STT (edge-tts, Whisper)
  - sync:      sincronização de dados entre dispositivos
  - routines:  rotinas agendadas (briefing, resumo, monitoramento)

Deploy:
  celery -A workers.celery_app worker --loglevel=info -Q default,ai,voice,sync,routines
  celery -A workers.celery_app beat   --loglevel=info
  celery -A workers.celery_app flower --port=5555
"""

import os
import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_prerun, task_postrun, task_failure

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════════════════

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Cria instância Celery
celery_app = Celery(
    "personal_ai",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "workers.tasks.ai_tasks",
        "workers.tasks.voice_tasks",
        "workers.tasks.sync_tasks",
        "workers.tasks.routine_tasks",
        "workers.tasks.monitoring_tasks",
    ],
)

# ─── Configuração do Celery ───────────────────────────────────────────────
celery_app.conf.update(
    # Serialização
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    
    # Timezone
    timezone="America/Sao_Paulo",
    enable_utc=True,
    
    # Filas e roteamento
    task_default_queue="default",
    task_queues={
        "default": {
            "exchange": "default",
            "routing_key": "default",
            "queue_arguments": {"x-max-priority": 10},
        },
        "ai": {
            "exchange": "ai",
            "routing_key": "ai",
            "queue_arguments": {"x-max-priority": 10},
        },
        "voice": {
            "exchange": "voice",
            "routing_key": "voice",
        },
        "sync": {
            "exchange": "sync",
            "routing_key": "sync",
        },
        "routines": {
            "exchange": "routines",
            "routing_key": "routines",
        },
    },
    task_routes={
        "workers.tasks.ai_tasks.*": {"queue": "ai"},
        "workers.tasks.voice_tasks.*": {"queue": "voice"},
        "workers.tasks.sync_tasks.*": {"queue": "sync"},
        "workers.tasks.routine_tasks.*": {"queue": "routines"},
        "workers.tasks.monitoring_tasks.*": {"queue": "default"},
    },
    
    # Retry e timeout
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=60,    # 60s soft limit (warning)
    task_time_limit=120,         # 120s hard limit (kill)
    
    # Resultados
    result_expires=3600,  # 1 hora
    
    # Worker
    worker_prefetch_multiplier=1,  # Fair dispatch (uma tarefa por vez por worker)
    worker_max_tasks_per_child=500,  # Reinicia worker a cada 500 tarefas (evita memory leak)
    
    # Dead Letter Queue — tarefas que falharam vão para fila de erro
    task_annotations={
        "*": {"rate_limit": "100/m"},
        "workers.tasks.ai_tasks.*": {
            "rate_limit": "30/m",  # Limita chamadas a LLMs
            "max_retries": 3,
        },
    },
)

# ─── Beat Schedule (tarefas recorrentes via Celery Beat) ─────────────────
celery_app.conf.beat_schedule = {
    # Monitoramento do sistema — a cada minuto
    "system-monitoring": {
        "task": "workers.tasks.monitoring_tasks.collect_metrics",
        "schedule": timedelta(minutes=1),
        "options": {"queue": "default"},
    },
    
    # Sincronização automática — a cada 30 minutos
    "auto-sync": {
        "task": "workers.tasks.sync_tasks.auto_sync",
        "schedule": timedelta(minutes=30),
        "options": {"queue": "sync"},
    },
    
    # Briefing matinal — 7h toda manhã
    "morning-briefing": {
        "task": "workers.tasks.routine_tasks.morning_briefing",
        "schedule": crontab(hour=7, minute=0),
        "options": {"queue": "routines"},
    },
    
    # Resumo noturno — 21h
    "night-summary": {
        "task": "workers.tasks.routine_tasks.night_summary",
        "schedule": crontab(hour=21, minute=0),
        "options": {"queue": "routines"},
    },
    
    # Revisão semanal — segunda-feira 9h
    "weekly-review": {
        "task": "workers.tasks.routine_tasks.weekly_review",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
        "options": {"queue": "routines"},
    },
    
    # Limpeza de dados antigos — madrugada
    "cleanup-old-data": {
        "task": "workers.tasks.monitoring_tasks.cleanup_old_data",
        "schedule": crontab(hour=3, minute=30),
        "options": {"queue": "default"},
    },
    
    # Verificação de lembretes de calendário — a cada 5 min
    "calendar-reminders": {
        "task": "workers.tasks.routine_tasks.check_calendar_reminders",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "routines"},
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# SIGNALS — Logging e métricas
# ═══════════════════════════════════════════════════════════════════════════

logger = logging.getLogger(__name__)

@task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **extra):
    logger.info(f"[Celery] INICIO tarefa={task.name} id={task_id}")

@task_postrun.connect
def task_postrun_handler(task_id, task, args, kwargs, retval, state, **extra):
    logger.info(f"[Celery] FIM tarefa={task.name} id={task_id} estado={state}")

@task_failure.connect
def task_failure_handler(task_id, exception, traceback, einfo, **extra):
    logger.error(f"[Celery] FALHA task_id={task_id} erro={exception}", exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════
# HELPER — Executar coroutines async dentro de tasks Celery síncronas
# ═══════════════════════════════════════════════════════════════════════════

def run_async(coro):
    """Executa coroutines async dentro de tarefas Celery síncronas."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
