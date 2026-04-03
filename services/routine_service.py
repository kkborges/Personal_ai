"""
services/routine_service.py — Rotinas automáticas com APScheduler
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from database.db import get_db
from models.schemas import RoutineCreate, Routine

logger = logging.getLogger(__name__)

ROUTINE_TEMPLATES = {
    "morning": {
        "name": "Briefing Matinal",
        "description": "Resumo do dia: agenda, clima, notícias e lembretes",
        "cron_expr": "0 7 * * *",
        "actions": [
            {"type": "agenda_summary", "params": {}},
            {"type": "speak", "params": {"text": "Bom dia! Aqui está seu resumo matinal."}},
        ]
    },
    "evening": {
        "name": "Resumo Noturno",
        "description": "Resumo do dia e preparação para o próximo",
        "cron_expr": "0 21 * * *",
        "actions": [
            {"type": "daily_summary", "params": {}},
            {"type": "agenda_summary", "params": {"days_ahead": 1}},
        ]
    },
    "weekly": {
        "name": "Revisão Semanal",
        "description": "Planejamento e revisão da semana",
        "cron_expr": "0 9 * * 1",
        "actions": [
            {"type": "weekly_review", "params": {}},
        ]
    },
    "sync": {
        "name": "Sincronização Automática",
        "description": "Sincroniza dados com o servidor",
        "cron_expr": "*/30 * * * *",
        "actions": [
            {"type": "sync", "params": {}}
        ]
    },
    "monitoring": {
        "name": "Monitoramento do Sistema",
        "description": "Coleta métricas e detecta anomalias",
        "cron_expr": "*/1 * * * *",
        "actions": [
            {"type": "collect_metrics", "params": {}}
        ]
    }
}


class RoutineService:
    def __init__(self):
        self._scheduler: Optional[AsyncIOScheduler] = None

    async def initialize(self):
        self._scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
        self._scheduler.start()

        # Carrega rotinas salvas
        routines = await self.get_all_routines()
        for r in routines:
            if r.get("enabled"):
                await self._schedule_routine(r["id"], r["cron_expr"])

        # Cria rotinas padrão se não existem
        await self._ensure_default_routines()

        logger.info(f"✅ RoutineService: {len(routines)} rotinas carregadas")

    async def create_routine(self, routine: RoutineCreate) -> Routine:
        r_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db = await get_db()
        await db.execute(
            "INSERT INTO routines VALUES (?,?,?,?,?,?,NULL,NULL,0,?,?)",
            (r_id, routine.name, routine.description, routine.cron_expr,
             json.dumps(routine.actions), 1 if routine.enabled else 0,
             now, json.dumps(routine.meta))
        )
        await db.commit()

        if routine.enabled:
            await self._schedule_routine(r_id, routine.cron_expr)

        return Routine(id=r_id, created_at=datetime.utcnow(), **routine.model_dump())

    async def get_all_routines(self) -> List[Dict]:
        db = await get_db()
        cur = await db.execute("SELECT * FROM routines ORDER BY created_at DESC")
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["actions"] = json.loads(d.get("actions") or "[]")
            except Exception:
                d["actions"] = []
            result.append(d)
        return result

    async def toggle_routine(self, r_id: str, enabled: bool) -> bool:
        db = await get_db()
        await db.execute("UPDATE routines SET enabled=? WHERE id=?", (1 if enabled else 0, r_id))
        await db.commit()
        if enabled:
            cur = await db.execute("SELECT cron_expr FROM routines WHERE id=?", (r_id,))
            row = await cur.fetchone()
            if row:
                await self._schedule_routine(r_id, row["cron_expr"])
        else:
            try:
                self._scheduler.remove_job(r_id)
            except Exception:
                pass
        return True

    async def delete_routine(self, r_id: str) -> bool:
        try:
            self._scheduler.remove_job(r_id)
        except Exception:
            pass
        db = await get_db()
        await db.execute("DELETE FROM routines WHERE id=?", (r_id,))
        await db.commit()
        return True

    async def run_routine_now(self, r_id: str) -> Dict:
        db = await get_db()
        cur = await db.execute("SELECT * FROM routines WHERE id=?", (r_id,))
        row = await cur.fetchone()
        if not row:
            return {"success": False, "error": "Rotina não encontrada"}
        return await self._execute_routine(r_id, dict(row))

    async def get_history(self, r_id: str = None, limit: int = 20) -> List[Dict]:
        db = await get_db()
        if r_id:
            cur = await db.execute(
                "SELECT * FROM routine_history WHERE routine_id=? ORDER BY executed_at DESC LIMIT ?",
                (r_id, limit)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM routine_history ORDER BY executed_at DESC LIMIT ?",
                (limit,)
            )
        return [dict(r) for r in await cur.fetchall()]

    async def get_templates(self) -> Dict:
        return ROUTINE_TEMPLATES

    async def create_from_template(self, template_name: str) -> Optional[Routine]:
        tpl = ROUTINE_TEMPLATES.get(template_name)
        if not tpl:
            return None
        routine = RoutineCreate(**tpl)
        return await self.create_routine(routine)

    # ─── Scheduling ──────────────────────────────────────────────────────────

    async def _schedule_routine(self, r_id: str, cron_expr: str):
        try:
            parts = cron_expr.split()
            if len(parts) == 5:
                minute, hour, day, month, day_of_week = parts
            else:
                minute, hour = parts[0], parts[1]
                day, month, day_of_week = "*", "*", "*"

            trigger = CronTrigger(
                minute=minute, hour=hour,
                day=day, month=month, day_of_week=day_of_week
            )
            if self._scheduler.get_job(r_id):
                self._scheduler.remove_job(r_id)

            self._scheduler.add_job(
                self._run_by_id,
                trigger=trigger,
                id=r_id,
                args=[r_id],
                replace_existing=True,
                max_instances=1,
            )
        except Exception as e:
            logger.error(f"Schedule routine {r_id} error: {e}")

    async def _run_by_id(self, r_id: str):
        db = await get_db()
        cur = await db.execute("SELECT * FROM routines WHERE id=?", (r_id,))
        row = await cur.fetchone()
        if row:
            await self._execute_routine(r_id, dict(row))

    async def _execute_routine(self, r_id: str, routine: Dict) -> Dict:
        history_id = str(uuid.uuid4())
        now = datetime.utcnow()
        results = []

        try:
            actions = json.loads(routine.get("actions") or "[]")
            for action in actions:
                result = await self._execute_action(action)
                results.append(result)

            # Atualiza última execução
            db = await get_db()
            await db.execute(
                "UPDATE routines SET last_run=?, run_count=run_count+1 WHERE id=?",
                (now.isoformat(), r_id)
            )
            await db.execute(
                "INSERT INTO routine_history VALUES (?,?,?,?,NULL,?)",
                (history_id, r_id, "success", json.dumps(results), now.isoformat())
            )
            await db.commit()
            return {"success": True, "results": results}

        except Exception as e:
            logger.error(f"Routine {r_id} execution error: {e}")
            db = await get_db()
            await db.execute(
                "INSERT INTO routine_history VALUES (?,?,?,NULL,?,?)",
                (history_id, r_id, "error", str(e), now.isoformat())
            )
            await db.commit()
            return {"success": False, "error": str(e)}

    async def _execute_action(self, action: Dict) -> Any:
        action_type = action.get("type", "")
        params = action.get("params", {})

        if action_type == "speak":
            from services.voice_service import voice_service
            text = params.get("text", "")
            audio = await voice_service.text_to_speech(text)
            return {"type": "speak", "audio_url": audio}

        elif action_type == "agenda_summary":
            from services.calendar_service import calendar_service
            days_ahead = params.get("days_ahead", 0)
            target = datetime.utcnow()
            if days_ahead:
                from datetime import timedelta
                target = target + timedelta(days=days_ahead)
            agenda = await calendar_service.get_daily_agenda(target)
            return {"type": "agenda_summary", "summary": agenda.summary}

        elif action_type == "sync":
            from services.sync_service import sync_service
            return await sync_service.sync_pending()

        elif action_type == "collect_metrics":
            from services.self_monitoring import self_monitoring
            return await self_monitoring.collect_metrics()

        elif action_type == "daily_summary":
            from services.chat_service import chat_service
            result = await chat_service.process_message(
                "Faça um resumo do meu dia e prepare as atividades de amanhã",
                platform="routine"
            )
            return {"type": "daily_summary", "summary": result["response"]}

        return {"type": action_type, "status": "executed"}

    async def _ensure_default_routines(self):
        existing = await self.get_all_routines()
        existing_names = {r["name"] for r in existing}
        for tpl_name, tpl in ROUTINE_TEMPLATES.items():
            if tpl["name"] not in existing_names:
                await self.create_from_template(tpl_name)


routine_service = RoutineService()
