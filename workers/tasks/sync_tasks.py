"""Celery Tasks — Sincronização de Dados."""

import logging
from celery import shared_task
from workers.celery_app import run_async

logger = logging.getLogger(__name__)


@shared_task(name="workers.tasks.sync_tasks.auto_sync", queue="sync")
def auto_sync():
    """Sincronização automática a cada 30 minutos."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.sync_service import SyncService
        svc = SyncService()
        await svc.initialize()
        return await svc.auto_sync()

    try:
        return run_async(_run())
    except Exception as exc:
        logger.warning(f"Sync automático falhou: {exc}")
        return {"error": str(exc), "synced": 0}


@shared_task(
    name="workers.tasks.sync_tasks.push_item",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    queue="sync",
)
def push_item(self, item_type: str, item_data: dict):
    """Envia um item específico para o servidor pai (modo offline→online)."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.sync_service import SyncService
        svc = SyncService()
        await svc.initialize()
        return await svc.push_single_item(item_type, item_data)

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error(f"Push falhou para {item_type}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
