"""
main.py — Personal AI Mobile — Servidor Principal FastAPI
Versão mobile com suporte offline, Bluetooth, voz contínua e auto-melhoria.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from database.db import init_db

# Logging estruturado
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("personal-ai-mobile")

WEB_DIR = Path(__file__).parent / "web"


# ─── WebSocket Manager ────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"WebSocket conectado. Total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws) if hasattr(self._connections, 'discard') else None
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, data: dict):
        msg = json.dumps(data)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, data: dict):
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            self.disconnect(ws)


ws_manager = ConnectionManager()


# ─── Background Tasks ─────────────────────────────────────────────────────────
async def background_monitor():
    """Coleta métricas periodicamente e transmite via WebSocket."""
    from services.self_monitoring import self_monitoring
    from services.sync_service import sync_service

    while True:
        try:
            metrics = await self_monitoring.collect_metrics()
            health = await self_monitoring.calculate_health_score(metrics)
            sync_st = await sync_service.get_status()
            await ws_manager.broadcast({
                "type": "metrics",
                "data": {
                    "cpu_percent": metrics.get("cpu_percent", 0),
                    "memory_percent": metrics.get("memory_percent", 0),
                    "health_score": health,
                    "online": sync_st["online"],
                    "pending_sync": sync_st["pending_items"],
                }
            })
        except Exception as e:
            logger.debug(f"Background monitor error: {e}")
        await asyncio.sleep(settings.monitoring_interval_seconds)


async def background_sync():
    """Sincroniza periodicamente com o servidor pai."""
    from services.sync_service import sync_service
    while True:
        await asyncio.sleep(settings.sync_interval_seconds)
        try:
            online = await sync_service.check_connectivity()
            if online and settings.sync_enabled:
                result = await sync_service.sync_pending()
                if result.get("synced", 0) > 0:
                    await ws_manager.broadcast({
                        "type": "sync_complete",
                        "data": result
                    })
        except Exception as e:
            logger.debug(f"Background sync error: {e}")


async def background_voice_commands():
    """Processa comandos de voz pendentes."""
    from services.voice_service import voice_service
    from services.chat_service import chat_service
    while True:
        try:
            commands = await voice_service.get_pending_commands()
            for cmd in commands:
                result = await chat_service.process_message(
                    cmd["text"], platform="voice", voice_response=True
                )
                await ws_manager.broadcast({
                    "type": "voice_command",
                    "data": {"command": cmd["text"], "response": result["response"],
                             "audio_url": result.get("audio_url")}
                })
        except Exception as e:
            logger.debug(f"Voice command error: {e}")
        await asyncio.sleep(0.5)


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Personal AI Mobile inicializando...")

    # Banco de dados
    await init_db()

    # Inicializa serviços
    from services.chat_service import chat_service
    from services.memory_service import memory_service
    from services.calendar_service import calendar_service
    from services.voice_service import voice_service
    from services.bluetooth_service import bluetooth_service
    from services.telephony_service import telephony_service
    from services.sync_service import sync_service
    from services.job_queue_service import job_queue
    from services.routine_service import routine_service
    from services.self_monitoring import self_monitoring

    await chat_service.initialize()
    await memory_service.initialize()
    await calendar_service.initialize()
    await voice_service.initialize()
    await bluetooth_service.initialize()
    await telephony_service.initialize()
    await sync_service.initialize()
    await job_queue.initialize()
    await routine_service.initialize()
    await self_monitoring.initialize()

    # Background tasks
    tasks = [
        asyncio.create_task(background_monitor()),
        asyncio.create_task(background_sync()),
        asyncio.create_task(background_voice_commands()),
    ]

    logger.info(f"✅ Personal AI Mobile v{settings.app_version} pronto em :{settings.port}")

    yield

    # Shutdown
    logger.info("🛑 Encerrando Personal AI Mobile...")
    for task in tasks:
        task.cancel()
    await job_queue.stop()
    from database.db import close_db
    await close_db()
    logger.info("👋 Encerrado com sucesso")


# ─── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Personal AI Mobile",
    description="Sistema de IA Pessoal Mobile — com voz, Bluetooth, autonomia e auto-melhoria",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas da API
from api.routes import router
app.include_router(router)

# Arquivos estáticos da web UI
if WEB_DIR.exists():
    if (WEB_DIR / "css").exists():
        app.mount("/css", StaticFiles(directory=str(WEB_DIR / "css")), name="css")
    if (WEB_DIR / "js").exists():
        app.mount("/js", StaticFiles(directory=str(WEB_DIR / "js")), name="js")
    if (WEB_DIR / "pwa").exists():
        app.mount("/pwa", StaticFiles(directory=str(WEB_DIR / "pwa")), name="pwa")
    # Favicon e outros arquivos raiz (evita 404 que causa lentidão no browser)
    app.mount("/static-root", StaticFiles(directory=str(WEB_DIR)), name="static-root")

# Rota explícita para favicon (mais rápido que StaticFiles para um único arquivo)
from fastapi.responses import FileResponse
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = WEB_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/x-icon",
                           headers={"Cache-Control": "public, max-age=86400"})
    # Fallback: retorna 204 No Content em vez de 404 (sem erro no browser)
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/favicon.svg", include_in_schema=False)
async def favicon_svg():
    svg_path = WEB_DIR / "favicon.svg"
    if svg_path.exists():
        return FileResponse(str(svg_path), media_type="image/svg+xml",
                           headers={"Cache-Control": "public, max-age=86400"})
    from fastapi.responses import Response
    return Response(status_code=204)


# ─── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        # Envia estado inicial
        from services.sync_service import sync_service
        from services.self_monitoring import self_monitoring
        sync_st = await sync_service.get_status()
        metrics = await self_monitoring.collect_metrics()
        await ws_manager.send_to(ws, {
            "type": "init",
            "data": {
                "version": settings.app_version,
                "online": sync_st["online"],
                "language": settings.language,
                "wake_word": settings.wake_word,
                "metrics": metrics,
            }
        })

        async for message in ws.iter_text():
            try:
                data = json.loads(message)
                await handle_ws_message(ws, data)
            except json.JSONDecodeError:
                await ws_manager.send_to(ws, {"type": "error", "data": "JSON inválido"})

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
        logger.info("WebSocket desconectado")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(ws)


async def handle_ws_message(ws: WebSocket, data: dict):
    """Processa mensagens recebidas via WebSocket."""
    msg_type = data.get("type", "")

    if msg_type == "chat":
        from services.chat_service import chat_service
        result = await chat_service.process_message(
            data.get("message", ""),
            conversation_id=data.get("conversation_id"),
            platform="mobile_ws",
            voice_response=data.get("voice", False),
        )
        await ws_manager.send_to(ws, {"type": "chat_response", "data": result})

    elif msg_type == "voice_command":
        from services.voice_service import voice_service
        from services.chat_service import chat_service
        text = data.get("text", "")
        result = await chat_service.process_message(text, platform="voice", voice_response=True)
        await ws_manager.send_to(ws, {
            "type": "voice_response",
            "data": {"text": result["response"], "audio_url": result.get("audio_url")}
        })

    elif msg_type == "ping":
        await ws_manager.send_to(ws, {"type": "pong", "data": {"ts": asyncio.get_event_loop().time()}})

    elif msg_type == "status_request":
        from services.sync_service import sync_service
        from services.self_monitoring import self_monitoring
        metrics = await self_monitoring.collect_metrics()
        sync_st = await sync_service.get_status()
        await ws_manager.send_to(ws, {
            "type": "status",
            "data": {"metrics": metrics, "sync": sync_st}
        })

    elif msg_type == "bluetooth_scan":
        from services.bluetooth_service import bluetooth_service
        result = await bluetooth_service.scan(data.get("duration", 10))
        await ws_manager.send_to(ws, {"type": "bluetooth_scan_result", "data": result.model_dump()})

    elif msg_type == "call":
        from services.telephony_service import telephony_service
        from models.schemas import CallRequest
        req = CallRequest(number=data.get("number", ""), via=data.get("via", "sip"))
        status = await telephony_service.dial(req)
        await ws_manager.send_to(ws, {"type": "call_status", "data": status.model_dump()})


# ─── Serve SPA ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    index = WEB_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return HTMLResponse("<h1>Personal AI Mobile - Web UI em construção</h1>")


@app.get("/manifest.json")
async def manifest():
    return {
        "name": "Personal AI Mobile",
        "short_name": "AI Mobile",
        "description": "Assistente Pessoal IA com voz, Bluetooth e autonomia",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f0f0f",
        "theme_color": "#6c63ff",
        "orientation": "portrait",
        "icons": [
            {"src": "/pwa/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/pwa/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


@app.get("/service-worker.js")
async def service_worker():
    sw_code = """
const CACHE_NAME = 'personal-ai-v2';
const OFFLINE_URLS = ['/', '/css/style.css', '/js/app.js'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(OFFLINE_URLS))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match(event.request).then(r => r || new Response('Offline'))
    )
  );
});
"""
    from fastapi.responses import Response
    return Response(content=sw_code, media_type="application/javascript")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
