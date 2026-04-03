"""
Celery Tasks — Rotinas Agendadas
==================================
Substitui APScheduler para ambientes de produção distribuída.
Em single-server (dev), APScheduler ainda funciona normalmente.
"""

import logging
from celery import shared_task
from workers.celery_app import run_async

logger = logging.getLogger(__name__)


@shared_task(name="workers.tasks.routine_tasks.morning_briefing", queue="routines")
def morning_briefing():
    """Briefing matinal — 7h toda manhã."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.routine_service import RoutineService
        svc = RoutineService()
        await svc.initialize()
        return await svc.execute_routine_by_name("Briefing Matinal")

    result = run_async(_run())
    logger.info(f"Briefing matinal executado: {result}")
    return result


@shared_task(name="workers.tasks.routine_tasks.night_summary", queue="routines")
def night_summary():
    """Resumo noturno — 21h."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.routine_service import RoutineService
        svc = RoutineService()
        await svc.initialize()
        return await svc.execute_routine_by_name("Resumo Noturno")

    return run_async(_run())


@shared_task(name="workers.tasks.routine_tasks.weekly_review", queue="routines")
def weekly_review():
    """Revisão semanal — segunda-feira 9h."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.routine_service import RoutineService
        svc = RoutineService()
        await svc.initialize()
        return await svc.execute_routine_by_name("Revisão Semanal")

    return run_async(_run())


@shared_task(name="workers.tasks.routine_tasks.check_calendar_reminders", queue="routines")
def check_calendar_reminders():
    """Verifica lembretes de calendário a cada 5 minutos."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.calendar_service import CalendarService
        svc = CalendarService()
        await svc.initialize()
        return await svc.check_and_send_reminders()

    result = run_async(_run())
    return result


@shared_task(
    name="workers.tasks.routine_tasks.execute_routine",
    bind=True,
    max_retries=2,
    queue="routines",
)
def execute_routine(self, routine_id: str):
    """Executa uma rotina específica por ID."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.routine_service import RoutineService
        svc = RoutineService()
        await svc.initialize()
        return await svc.execute_routine(routine_id)

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error(f"Rotina {routine_id} falhou: {exc}")
        raise self.retry(exc=exc, countdown=60)
