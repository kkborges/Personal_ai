"""Celery Tasks — Monitoramento e Manutenção."""

import logging
from celery import shared_task
from workers.celery_app import run_async

logger = logging.getLogger(__name__)


@shared_task(name="workers.tasks.monitoring_tasks.collect_metrics")
def collect_metrics():
    """Coleta métricas do sistema a cada minuto."""
    async def _run():
        import sys, psutil, datetime
        sys.path.insert(0, "/app")
        from database.db import get_db_connection
        
        metrics = {
            "cpu": psutil.cpu_percent(interval=1),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
        
        async with get_db_connection() as db:
            await db.execute(
                "INSERT INTO monitoring_metrics (cpu_percent, memory_percent, disk_percent) VALUES (?,?,?)",
                (metrics["cpu"], metrics["memory"], metrics["disk"])
            )
            await db.commit()
        
        return metrics

    try:
        return run_async(_run())
    except Exception as exc:
        logger.warning(f"Coleta de métricas falhou: {exc}")
        return {"error": str(exc)}


@shared_task(name="workers.tasks.monitoring_tasks.cleanup_old_data")
def cleanup_old_data():
    """Remove dados antigos do banco para manter performance."""
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from database.db import get_db_connection
        
        deleted = {}
        async with get_db_connection() as db:
            # Remove métricas com mais de 7 dias
            r1 = await db.execute(
                "DELETE FROM monitoring_metrics WHERE created_at < datetime('now', '-7 days')"
            )
            deleted["monitoring_metrics"] = r1.rowcount
            
            # Remove jobs finalizados com mais de 30 dias
            r2 = await db.execute(
                "DELETE FROM jobs WHERE status IN ('completed','failed') AND created_at < datetime('now', '-30 days')"
            )
            deleted["old_jobs"] = r2.rowcount
            
            await db.commit()
        
        logger.info(f"Limpeza concluída: {deleted}")
        return deleted

    return run_async(_run())
