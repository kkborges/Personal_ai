"""
services/job_queue_service.py — Fila de jobs async com prioridade, retry e dead letter
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from config import settings
from database.db import get_db

logger = logging.getLogger(__name__)


class JobQueueService:
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._active_count = 0
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def initialize(self):
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        self._register_default_handlers()
        logger.info(f"✅ JobQueueService: max_concurrent={settings.max_concurrent_jobs}")

    def register(self, job_type: str, handler: Callable):
        self._handlers[job_type] = handler

    def _register_default_handlers(self):
        self.register("tts", self._handle_tts)
        self.register("sync", self._handle_sync)
        self.register("reminder", self._handle_reminder)
        self.register("monitoring", self._handle_monitoring)
        self.register("improvement", self._handle_improvement)

    async def enqueue(self, job_type: str, payload: Dict = None,
                       priority: int = 5, scheduled_at: datetime = None,
                       depends_on: str = None, max_attempts: int = 3) -> str:
        job_id = str(uuid.uuid4())
        db = await get_db()
        await db.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,NULL,NULL,0,?,?,?,NULL,NULL,?)",
            (job_id, job_type, "pending", priority,
             json.dumps(payload or {}), max_attempts, depends_on,
             (scheduled_at or datetime.utcnow()).isoformat(),
             datetime.utcnow().isoformat())
        )
        await db.commit()
        return job_id

    async def get_job(self, job_id: str) -> Optional[Dict]:
        db = await get_db()
        cur = await db.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_jobs(self, status: str = None, limit: int = 50) -> List[Dict]:
        db = await get_db()
        if status:
            cur = await db.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY priority ASC, scheduled_at ASC LIMIT ?",
                (status, limit)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM jobs ORDER BY priority ASC, scheduled_at ASC LIMIT ?",
                (limit,)
            )
        return [dict(r) for r in await cur.fetchall()]

    async def cancel_job(self, job_id: str) -> bool:
        db = await get_db()
        await db.execute(
            "UPDATE jobs SET status='cancelled' WHERE id=? AND status='pending'",
            (job_id,)
        )
        await db.commit()
        return True

    async def get_stats(self) -> Dict[str, Any]:
        db = await get_db()
        cur = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
        )
        rows = await cur.fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    # ─── Worker Loop ─────────────────────────────────────────────────────────

    async def _worker_loop(self):
        while self._running:
            try:
                await self._process_next()
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(1)

    async def _process_next(self):
        db = await get_db()
        cur = await db.execute(
            "SELECT * FROM jobs WHERE status='pending' AND scheduled_at <= ? "
            "AND (depends_on IS NULL OR depends_on IN "
            "(SELECT id FROM jobs WHERE status='completed')) "
            "ORDER BY priority ASC, scheduled_at ASC LIMIT 1",
            (datetime.utcnow().isoformat(),)
        )
        row = await cur.fetchone()
        if not row:
            return

        job = dict(row)
        async with self._semaphore:
            self._active_count += 1
            await self._run_job(job)
            self._active_count -= 1

    async def _run_job(self, job: Dict):
        db = await get_db()
        job_id = job["id"]
        now = datetime.utcnow().isoformat()

        await db.execute(
            "UPDATE jobs SET status='running', started_at=?, attempts=attempts+1 WHERE id=?",
            (now, job_id)
        )
        await db.commit()

        handler = self._handlers.get(job["type"])
        if not handler:
            await db.execute(
                "UPDATE jobs SET status='failed', error='No handler registered', completed_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), job_id)
            )
            await db.commit()
            return

        payload = json.loads(job["payload"]) if isinstance(job["payload"], str) else job.get("payload", {})

        try:
            result = await asyncio.wait_for(handler(payload), timeout=settings.job_timeout_seconds)
            await db.execute(
                "UPDATE jobs SET status='completed', result=?, completed_at=? WHERE id=?",
                (json.dumps(result), datetime.utcnow().isoformat(), job_id)
            )
        except asyncio.TimeoutError:
            await self._handle_failure(job, "Timeout")
        except Exception as e:
            await self._handle_failure(job, str(e))

        await db.commit()

    async def _handle_failure(self, job: Dict, error: str):
        db = await get_db()
        attempts = job["attempts"] + 1
        max_attempts = job["max_attempts"]

        if attempts >= max_attempts:
            status = "dead_letter"
            logger.error(f"Job {job['id']} moved to dead_letter: {error}")
        else:
            # Exponential backoff
            import math
            delay = min(300, 2 ** attempts * 5)
            from datetime import timedelta
            next_run = (datetime.utcnow() + timedelta(seconds=delay)).isoformat()
            status = "pending"
            await db.execute(
                "UPDATE jobs SET scheduled_at=? WHERE id=?",
                (next_run, job["id"])
            )

        await db.execute(
            "UPDATE jobs SET status=?, error=?, completed_at=? WHERE id=?",
            (status, error[:500], datetime.utcnow().isoformat(), job["id"])
        )

    # ─── Default Handlers ─────────────────────────────────────────────────────

    async def _handle_tts(self, payload: Dict) -> Dict:
        from services.voice_service import voice_service
        audio_url = await voice_service.text_to_speech(
            payload.get("text", ""),
            voice=payload.get("voice"),
            speed=payload.get("speed", 1.0),
        )
        return {"audio_url": audio_url}

    async def _handle_sync(self, payload: Dict) -> Dict:
        from services.sync_service import sync_service
        return await sync_service.sync_pending()

    async def _handle_reminder(self, payload: Dict) -> Dict:
        from services.voice_service import voice_service
        from services.chat_service import chat_service
        msg = payload.get("message", "Lembrete!")
        await voice_service.text_to_speech(f"Lembrete: {msg}")
        return {"reminder_sent": True, "message": msg}

    async def _handle_monitoring(self, payload: Dict) -> Dict:
        from services.self_monitoring import self_monitoring
        metrics = await self_monitoring.collect_metrics()
        return metrics

    async def _handle_improvement(self, payload: Dict) -> Dict:
        from services.self_monitoring import self_monitoring
        return await self_monitoring.generate_improvement(payload)

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()


job_queue = JobQueueService()
