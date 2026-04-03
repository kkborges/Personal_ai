"""
api/routes.py — Todas as rotas da API do Personal AI Mobile
"""
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, File, Body
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse

from config import settings
from models.schemas import (
    APIResponse, ChatRequest, CalendarEventCreate, CallRequest,
    ContactCreate, GoalCreate, JobCreate, MemoryCreate, MemoryType,
    RoutineCreate, TTSRequest, SpotifyCommand, AppLaunchRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════════════════
# HEALTH & STATUS
# ════════════════════════════════════════════════════════════════════════════
@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(),
            "version": settings.app_version}


@router.get("/api/status")
async def system_status():
    from services.self_monitoring import self_monitoring
    from services.sync_service import sync_service
    from services.bluetooth_service import bluetooth_service
    from services.telephony_service import telephony_service
    from services.job_queue_service import job_queue
    import psutil, time

    metrics = await self_monitoring.collect_metrics()
    health = await self_monitoring.calculate_health_score(metrics)
    sync_status = await sync_service.get_status()
    jobs_stats = await job_queue.get_stats()

    return {
        "app_version": settings.app_version,
        "uptime_s": self_monitoring.uptime_seconds,
        "online": sync_status["online"],
        "autonomy_level": settings.autonomy_level,
        "health_score": health,
        "cpu_percent": metrics.get("cpu_percent", 0),
        "memory_mb": metrics.get("memory_mb", 0),
        "memory_percent": metrics.get("memory_percent", 0),
        "disk_free_gb": metrics.get("disk_free_gb", 0),
        "bluetooth_connected": bluetooth_service.connected_count,
        "active_calls": len(await telephony_service.get_active_calls()),
        "jobs": jobs_stats,
        "sync": sync_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/api/config")
async def get_config():
    return {
        "language": settings.language,
        "tts_backend": settings.tts_backend,
        "tts_voice": settings.tts_voice,
        "always_listen": settings.always_listen,
        "wake_word": settings.wake_word,
        "autonomy_level": settings.autonomy_level,
        "default_provider": settings.default_provider,
        "bluetooth_enabled": settings.bluetooth_enabled,
        "telephony_enabled": settings.telephony_enabled,
        "sync_enabled": settings.sync_enabled,
        "parent_api_url": settings.parent_api_url,
        "offline_mode": settings.offline_mode,
        "self_monitoring_enabled": settings.self_monitoring_enabled,
        "self_improvement_enabled": settings.self_improvement_enabled,
    }


@router.patch("/api/config")
async def update_config(data: Dict[str, Any] = Body(...)):
    """Atualiza configurações em tempo de execução."""
    db_settings = {}
    allowed = ["language", "tts_voice", "tts_backend", "tts_speed", "always_listen",
                "wake_word", "autonomy_level", "default_provider", "sync_enabled",
                "auto_deploy_patches", "offline_mode"]
    for key, value in data.items():
        if key in allowed:
            db_settings[key] = str(value)

    from database.db import get_db
    db = await get_db()
    for k, v in db_settings.items():
        await db.execute(
            "INSERT OR REPLACE INTO settings_kv VALUES (?,?,?)",
            (k, v, datetime.utcnow().isoformat())
        )
    await db.commit()
    return {"success": True, "updated": list(db_settings.keys())}


# ════════════════════════════════════════════════════════════════════════════
# CHAT
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/chat")
async def chat(request: ChatRequest):
    from services.chat_service import chat_service
    try:
        result = await chat_service.process_message(
            message=request.message,
            conversation_id=request.conversation_id,
            platform=request.platform,
            voice_response=request.voice_response,
            provider=request.provider.value if request.provider else None,
        )
        return result
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/chat/stream")
async def chat_stream(message: str, conversation_id: str = None):
    from services.chat_service import chat_service

    async def event_generator():
        async for chunk in chat_service.stream_response(message, conversation_id):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/chat/conversations")
async def get_conversations(platform: str = None, limit: int = 20):
    from services.chat_service import chat_service
    return await chat_service.get_conversations(platform=platform, limit=limit)


@router.get("/api/chat/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, limit: int = 50):
    from services.chat_service import chat_service
    return await chat_service.get_messages(conv_id, limit)


@router.delete("/api/chat/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    from services.chat_service import chat_service
    success = await chat_service.delete_conversation(conv_id)
    return {"success": success}


# ════════════════════════════════════════════════════════════════════════════
# VOICE
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/voice/tts")
async def text_to_speech(request: TTSRequest):
    from services.voice_service import voice_service
    try:
        url = await voice_service.text_to_speech(
            text=request.text, voice=request.voice,
            speed=request.speed, language=request.language,
            backend=request.backend
        )
        return {"audio_url": url, "text": request.text}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/api/voice/stt")
async def speech_to_text(audio: UploadFile = File(...), language: str = "pt-BR"):
    from services.voice_service import voice_service
    data = await audio.read()
    result = await voice_service.speech_to_text(data, language)
    return result


@router.get("/api/voice/status")
async def voice_status():
    from services.voice_service import voice_service
    return await voice_service.get_status()


@router.post("/api/voice/listen/start")
async def start_listening():
    from services.voice_service import voice_service
    from services.chat_service import chat_service

    async def on_command(text: str):
        await chat_service.process_message(text, platform="voice", voice_response=True)

    await voice_service.start_always_on(callback=on_command)
    return {"status": "listening", "wake_word": settings.wake_word}


@router.post("/api/voice/listen/stop")
async def stop_listening():
    from services.voice_service import voice_service
    await voice_service.stop_always_on()
    return {"status": "stopped"}


@router.get("/api/voice/commands/pending")
async def get_pending_commands():
    from services.voice_service import voice_service
    return await voice_service.get_pending_commands()


@router.get("/api/voice/voices")
async def list_voices():
    from services.voice_service import voice_service
    return await voice_service.list_voices()


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    path = AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Arquivo de áudio não encontrado")
    return FileResponse(str(path), media_type="audio/mpeg")


# ════════════════════════════════════════════════════════════════════════════
# MEMORY
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/memory")
async def add_memory(memory: MemoryCreate):
    from services.memory_service import memory_service
    result = await memory_service.add(memory)
    return result


@router.get("/api/memory")
async def get_memories(type: str = None, limit: int = 50):
    from services.memory_service import memory_service
    items = await memory_service.get_all(memory_type=type, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/api/memory/search")
async def search_memory(q: str, type: str = None, limit: int = 10):
    from services.memory_service import memory_service
    results = await memory_service.search(q, limit=limit, memory_type=type)
    return {"results": [r.model_dump() for r in results], "total": len(results)}


@router.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    from services.memory_service import memory_service
    success = await memory_service.delete(memory_id)
    return {"success": success}


# ════════════════════════════════════════════════════════════════════════════
# CALENDAR
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/calendar/events")
async def create_event(event: CalendarEventCreate):
    from services.calendar_service import calendar_service
    return await calendar_service.create_event(event)


@router.get("/api/calendar/events")
async def get_events(start: str = None, end: str = None, platform: str = None):
    from services.calendar_service import calendar_service
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    events = await calendar_service.get_events(start_dt, end_dt, platform)
    return {"events": events}


@router.get("/api/calendar/agenda")
async def daily_agenda(date: str = None):
    from services.calendar_service import calendar_service
    day = datetime.fromisoformat(date) if date else datetime.utcnow()
    agenda = await calendar_service.get_daily_agenda(day)
    return agenda


@router.get("/api/calendar/upcoming")
async def upcoming_events(hours: int = 24):
    from services.calendar_service import calendar_service
    return await calendar_service.get_upcoming_events(hours)


@router.put("/api/calendar/events/{ev_id}")
async def update_event(ev_id: str, updates: Dict[str, Any] = Body(...)):
    from services.calendar_service import calendar_service
    result = await calendar_service.update_event(ev_id, updates)
    if not result:
        raise HTTPException(404, "Evento não encontrado")
    return result


@router.delete("/api/calendar/events/{ev_id}")
async def delete_event(ev_id: str):
    from services.calendar_service import calendar_service
    return {"success": await calendar_service.delete_event(ev_id)}


@router.post("/api/calendar/natural")
async def natural_language_event(text: str = Body(..., embed=True)):
    from services.calendar_service import calendar_service
    result = await calendar_service.natural_language_event(text)
    if not result:
        raise HTTPException(422, "Não foi possível extrair evento do texto")
    return result


@router.get("/api/calendar/export.ical")
async def export_ical():
    from services.calendar_service import calendar_service
    content = await calendar_service.export_ical()
    return StreamingResponse(
        iter([content]),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=agenda.ics"}
    )


# ════════════════════════════════════════════════════════════════════════════
# BLUETOOTH
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/bluetooth/scan")
async def bluetooth_scan(duration: int = 10):
    from services.bluetooth_service import bluetooth_service
    result = await bluetooth_service.scan(duration)
    return result


@router.get("/api/bluetooth/devices")
async def bluetooth_devices():
    from services.bluetooth_service import bluetooth_service
    return await bluetooth_service.get_paired_devices()


@router.get("/api/bluetooth/connected")
async def bluetooth_connected():
    from services.bluetooth_service import bluetooth_service
    return await bluetooth_service.get_connected_devices()


@router.post("/api/bluetooth/connect/{mac}")
async def bluetooth_connect(mac: str):
    from services.bluetooth_service import bluetooth_service
    return await bluetooth_service.connect(mac)


@router.post("/api/bluetooth/disconnect/{mac}")
async def bluetooth_disconnect(mac: str):
    from services.bluetooth_service import bluetooth_service
    return await bluetooth_service.disconnect(mac)


@router.post("/api/bluetooth/pair/{mac}")
async def bluetooth_pair(mac: str):
    from services.bluetooth_service import bluetooth_service
    return await bluetooth_service.pair(mac)


@router.post("/api/bluetooth/audio/{mac}")
async def bluetooth_audio_output(mac: str):
    from services.bluetooth_service import bluetooth_service
    return await bluetooth_service.set_audio_output(mac)


# ════════════════════════════════════════════════════════════════════════════
# TELEPHONY
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/phone/call")
async def make_call(request: CallRequest):
    from services.telephony_service import telephony_service
    return await telephony_service.dial(request)


@router.post("/api/phone/answer")
async def answer_call(call_id: str = None):
    from services.telephony_service import telephony_service
    return await telephony_service.answer(call_id)


@router.post("/api/phone/hangup")
async def hangup(call_id: str = None):
    from services.telephony_service import telephony_service
    return await telephony_service.hangup(call_id)


@router.get("/api/phone/active")
async def active_calls():
    from services.telephony_service import telephony_service
    return await telephony_service.get_active_calls()


@router.get("/api/phone/history")
async def call_history(limit: int = 50):
    from services.telephony_service import telephony_service
    calls = await telephony_service.get_call_history(limit)
    return [c.model_dump() for c in calls]


@router.get("/api/phone/status")
async def phone_status():
    from services.telephony_service import telephony_service
    return await telephony_service.get_status()


# ════════════════════════════════════════════════════════════════════════════
# CONTACTS
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/contacts")
async def create_contact(contact: ContactCreate):
    from database.db import get_db
    c_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    db = await get_db()
    await db.execute(
        "INSERT INTO contacts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (c_id, contact.name, contact.phone, contact.email, contact.platform,
         contact.external_id, json.dumps(contact.tags), contact.notes, now, now,
         json.dumps(contact.meta))
    )
    await db.commit()
    return {"id": c_id, **contact.model_dump()}


@router.get("/api/contacts")
async def get_contacts(search: str = None, limit: int = 50):
    from database.db import get_db
    db = await get_db()
    if search:
        cur = await db.execute(
            "SELECT * FROM contacts WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? LIMIT ?",
            (f"%{search}%", f"%{search}%", f"%{search}%", limit)
        )
    else:
        cur = await db.execute("SELECT * FROM contacts ORDER BY name LIMIT ?", (limit,))
    return [dict(r) for r in await cur.fetchall()]


# ════════════════════════════════════════════════════════════════════════════
# JOBS
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/jobs")
async def create_job(job: JobCreate):
    from services.job_queue_service import job_queue
    job_id = await job_queue.enqueue(
        job_type=job.type, payload=job.payload, priority=job.priority,
        scheduled_at=job.scheduled_at, depends_on=job.depends_on,
        max_attempts=job.max_attempts
    )
    return {"job_id": job_id, "status": "pending"}


@router.get("/api/jobs")
async def get_jobs(status: str = None, limit: int = 50):
    from services.job_queue_service import job_queue
    return await job_queue.get_jobs(status=status, limit=limit)


@router.get("/api/jobs/stats")
async def jobs_stats():
    from services.job_queue_service import job_queue
    return await job_queue.get_stats()


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    from services.job_queue_service import job_queue
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado")
    return job


@router.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    from services.job_queue_service import job_queue
    return {"success": await job_queue.cancel_job(job_id)}


# ════════════════════════════════════════════════════════════════════════════
# ROUTINES
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/routines")
async def create_routine(routine: RoutineCreate):
    from services.routine_service import routine_service
    return await routine_service.create_routine(routine)


@router.get("/api/routines")
async def get_routines():
    from services.routine_service import routine_service
    return await routine_service.get_all_routines()


@router.get("/api/routines/templates")
async def get_routine_templates():
    from services.routine_service import routine_service
    return await routine_service.get_templates()


@router.post("/api/routines/template/{name}")
async def create_from_template(name: str):
    from services.routine_service import routine_service
    result = await routine_service.create_from_template(name)
    if not result:
        raise HTTPException(404, f"Template '{name}' não encontrado")
    return result


@router.post("/api/routines/{r_id}/run")
async def run_routine(r_id: str):
    from services.routine_service import routine_service
    return await routine_service.run_routine_now(r_id)


@router.patch("/api/routines/{r_id}/toggle")
async def toggle_routine(r_id: str, enabled: bool = Body(..., embed=True)):
    from services.routine_service import routine_service
    return {"success": await routine_service.toggle_routine(r_id, enabled)}


@router.delete("/api/routines/{r_id}")
async def delete_routine(r_id: str):
    from services.routine_service import routine_service
    return {"success": await routine_service.delete_routine(r_id)}


@router.get("/api/routines/{r_id}/history")
async def routine_history(r_id: str, limit: int = 20):
    from services.routine_service import routine_service
    return await routine_service.get_history(r_id, limit)


# ════════════════════════════════════════════════════════════════════════════
# GOALS / AUTONOMY
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/goals")
async def create_goal(goal: GoalCreate):
    g_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    from database.db import get_db
    db = await get_db()
    await db.execute(
        "INSERT INTO goals VALUES (?,?,?,?,0.0,?,?,?,?)",
        (g_id, goal.title, goal.description, "active",
         goal.due_date.isoformat() if goal.due_date else None,
         now, now, json.dumps(goal.meta))
    )
    await db.commit()
    return {"id": g_id, "status": "active", "progress": 0.0, **goal.model_dump()}


@router.get("/api/goals")
async def get_goals(status: str = None):
    from database.db import get_db
    db = await get_db()
    if status:
        cur = await db.execute("SELECT * FROM goals WHERE status=? ORDER BY created_at DESC", (status,))
    else:
        cur = await db.execute("SELECT * FROM goals ORDER BY created_at DESC")
    return [dict(r) for r in await cur.fetchall()]


@router.patch("/api/goals/{g_id}/progress")
async def update_goal_progress(g_id: str, progress: float = Body(..., embed=True)):
    from database.db import get_db
    db = await get_db()
    status = "completed" if progress >= 1.0 else "active"
    await db.execute(
        "UPDATE goals SET progress=?, status=?, updated_at=? WHERE id=?",
        (min(1.0, max(0.0, progress)), status, datetime.utcnow().isoformat(), g_id)
    )
    await db.commit()
    return {"success": True, "progress": progress, "status": status}


# ════════════════════════════════════════════════════════════════════════════
# SELF-MONITORING & IMPROVEMENT
# ════════════════════════════════════════════════════════════════════════════
@router.get("/api/monitoring/metrics")
async def get_metrics():
    from services.self_monitoring import self_monitoring
    metrics = await self_monitoring.collect_metrics()
    health = await self_monitoring.calculate_health_score(metrics)
    return {"metrics": metrics, "health_score": health}


@router.get("/api/monitoring/report")
async def monitoring_report(hours: int = 24):
    from services.self_monitoring import self_monitoring
    return await self_monitoring.generate_report(hours)


@router.get("/api/monitoring/anomalies")
async def detect_anomalies():
    from services.self_monitoring import self_monitoring
    return await self_monitoring.detect_anomalies()


@router.post("/api/monitoring/improve")
async def generate_improvement(context: Dict = Body(default={})):
    from services.self_monitoring import self_monitoring
    return await self_monitoring.generate_improvement(context)


@router.get("/api/monitoring/patches")
async def get_patches(status: str = None):
    from services.self_monitoring import self_monitoring
    return await self_monitoring.get_patches(status)


@router.post("/api/monitoring/patches/{patch_id}/test")
async def run_patch_tests(patch_id: str):
    from services.self_monitoring import self_monitoring
    return await self_monitoring.run_tests(patch_id)


@router.post("/api/monitoring/patches/{patch_id}/apply")
async def apply_patch(patch_id: str):
    from services.self_monitoring import self_monitoring
    return await self_monitoring.apply_patch(patch_id)


# ════════════════════════════════════════════════════════════════════════════
# SYNC
# ════════════════════════════════════════════════════════════════════════════
@router.get("/api/sync/status")
async def sync_status():
    from services.sync_service import sync_service
    return await sync_service.get_status()


@router.post("/api/sync/push")
async def sync_push():
    from services.sync_service import sync_service
    return await sync_service.sync_pending()


@router.post("/api/sync/pull")
async def sync_pull():
    from services.sync_service import sync_service
    return await sync_service.pull_from_server()


@router.post("/api/sync/check")
async def check_connectivity():
    from services.sync_service import sync_service
    online = await sync_service.check_connectivity()
    return {"online": online}


# ════════════════════════════════════════════════════════════════════════════
# PLATFORM INTEGRATIONS
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/platforms/alexa")
async def alexa_webhook(body: Dict = Body(...)):
    from services.platform_integrations import alexa_integration
    return await alexa_integration.handle_intent(body)


@router.post("/api/platforms/google")
async def google_webhook(body: Dict = Body(...)):
    from services.platform_integrations import google_assistant_integration
    return await google_assistant_integration.handle_webhook(body)


@router.post("/api/platforms/whatsapp/webhook")
async def whatsapp_webhook(body: Dict = Body(...)):
    from services.platform_integrations import whatsapp_integration
    return await whatsapp_integration.handle_webhook(body)


@router.post("/api/platforms/whatsapp/send")
async def send_whatsapp(to: str = Body(...), message: str = Body(...)):
    from services.platform_integrations import whatsapp_integration
    return await whatsapp_integration.send_message(to, message)


@router.get("/api/platforms/outlook/emails")
async def get_emails(limit: int = 10, unread_only: bool = True):
    from services.platform_integrations import outlook_integration
    return await outlook_integration.get_emails(limit, unread_only)


@router.post("/api/platforms/outlook/send")
async def send_email(to: str = Body(...), subject: str = Body(...), body: str = Body(...)):
    from services.platform_integrations import outlook_integration
    return await outlook_integration.send_email(to, subject, body)


@router.get("/api/platforms/outlook/calendar")
async def outlook_calendar(days_ahead: int = 7):
    from services.platform_integrations import outlook_integration
    return await outlook_integration.get_calendar_events(days_ahead)


@router.post("/api/platforms/teams/send")
async def send_teams(message: str = Body(..., embed=True)):
    from services.platform_integrations import outlook_integration
    return await outlook_integration.send_teams_message(message)


@router.get("/api/platforms/spotify/auth")
async def spotify_auth():
    from services.platform_integrations import spotify_integration
    url = await spotify_integration.get_auth_url()
    return {"auth_url": url}


@router.get("/api/platforms/spotify/callback")
async def spotify_callback(code: str):
    from services.platform_integrations import spotify_integration
    return await spotify_integration.exchange_code(code)


@router.post("/api/platforms/spotify/control")
async def spotify_control(cmd: SpotifyCommand):
    from services.platform_integrations import spotify_integration
    return await spotify_integration.control(cmd.action, cmd.model_dump())


@router.get("/api/platforms/spotify/now")
async def spotify_now_playing():
    from services.platform_integrations import spotify_integration
    return await spotify_integration.get_currently_playing()


# ════════════════════════════════════════════════════════════════════════════
# APP LAUNCHER
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/apps/launch")
async def launch_app(request: AppLaunchRequest):
    from services.platform_integrations import streaming_apps
    return await streaming_apps.launch_app(
        request.app_name, request.platform, request.params
    )


@router.get("/api/apps/list")
async def list_apps():
    from services.platform_integrations import streaming_apps
    return streaming_apps.list_apps()


@router.get("/api/apps/search")
async def search_in_app(app: str, q: str):
    from services.platform_integrations import streaming_apps
    return await streaming_apps.search_content(app, q)


# ════════════════════════════════════════════════════════════════════════════
# DOCUMENTS & PROJECTS
# ════════════════════════════════════════════════════════════════════════════
@router.post("/api/documents/create")
async def create_document(
    title: str = Body(...), doc_type: str = Body(...),
    content: str = Body(default=None), ai_generate: bool = Body(default=True)
):
    from services.platform_integrations import document_service
    return await document_service.create_document(title, doc_type, content, ai_generate=ai_generate)


@router.post("/api/documents/project")
async def create_dev_project(
    project_name: str = Body(...),
    description: str = Body(...),
    tech_stack: List[str] = Body(default=["Python", "FastAPI"]),
    ai_providers: List[str] = Body(default=["OpenAI", "Claude", "Gemini", "GenSpark"]),
):
    from services.platform_integrations import document_service
    return await document_service.create_dev_project(
        project_name, description, tech_stack, ai_providers
    )


# ════════════════════════════════════════════════════════════════════════════
# PROVIDER STATS
# ════════════════════════════════════════════════════════════════════════════
@router.get("/api/providers/stats")
async def provider_stats():
    from services.provider_router import provider_router
    return await provider_router.get_stats()
