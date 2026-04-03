"""
services/sync_service.py — Sincronização com a versão web do Personal AI
Suporte a modo offline: fila de operações, reenvio automático ao voltar online.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from config import settings
from database.db import get_db

logger = logging.getLogger(__name__)


class SyncService:
    """Gerencia sincronização entre o mobile e o servidor web do Personal AI."""

    def __init__(self):
        self._online = False
        self._last_sync: Optional[datetime] = None
        self._synced_today = 0
        self._sync_errors: List[str] = []
        self._checking = False
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self):
        self._client = httpx.AsyncClient(
            base_url=settings.parent_api_url,
            timeout=10,
            headers={"X-API-Key": settings.parent_api_key} if settings.parent_api_key else {}
        )
        await self.check_connectivity()
        logger.info(f"✅ SyncService: online={self._online}, parent={settings.parent_api_url}")

    async def check_connectivity(self) -> bool:
        """Verifica conectividade com a internet e com o servidor pai."""
        if self._checking:
            return self._online
        self._checking = True
        try:
            # Verifica internet
            async with httpx.AsyncClient(timeout=5) as c:
                resp = await c.get("https://dns.google/resolve?name=google.com&type=A")
                internet_ok = resp.status_code == 200
        except Exception:
            internet_ok = False

        # Verifica servidor pai
        parent_ok = False
        if internet_ok and settings.parent_api_url:
            try:
                resp = await self._client.get("/health", timeout=5)
                parent_ok = resp.status_code == 200
            except Exception:
                parent_ok = False

        was_online = self._online
        self._online = internet_ok
        if not was_online and internet_ok:
            logger.info("🌐 Voltou online! Iniciando sincronização...")
            asyncio.create_task(self.sync_pending())

        self._checking = False
        return self._online

    async def queue_operation(self, entity_type: str, entity_id: str,
                               operation: str, payload: Dict) -> str:
        """Adiciona operação à fila de sincronização."""
        item_id = str(uuid.uuid4())
        db = await get_db()
        await db.execute(
            "INSERT INTO sync_queue VALUES (?,?,?,?,?,0,0,?,NULL)",
            (item_id, entity_type, entity_id, operation,
             json.dumps(payload), datetime.utcnow().isoformat())
        )
        await db.commit()

        # Se online, tenta sincronizar imediatamente
        if self._online:
            asyncio.create_task(self._sync_item(item_id))

        return item_id

    async def sync_pending(self) -> Dict[str, Any]:
        """Sincroniza todos os itens pendentes."""
        if not self._online:
            return {"synced": 0, "errors": ["Offline"]}

        db = await get_db()
        cur = await db.execute(
            "SELECT * FROM sync_queue WHERE synced=0 AND retry_count < 5 "
            "ORDER BY created_at ASC LIMIT 100"
        )
        items = await cur.fetchall()
        synced = 0
        errors = []

        for item in items:
            try:
                success = await self._push_item(dict(item))
                if success:
                    await db.execute(
                        "UPDATE sync_queue SET synced=1, synced_at=? WHERE id=?",
                        (datetime.utcnow().isoformat(), item["id"])
                    )
                    synced += 1
                else:
                    await db.execute(
                        "UPDATE sync_queue SET retry_count=retry_count+1 WHERE id=?",
                        (item["id"],)
                    )
                    errors.append(f"Failed: {item['entity_type']}/{item['entity_id']}")
            except Exception as e:
                errors.append(str(e))

        await db.commit()
        self._last_sync = datetime.utcnow()
        self._synced_today += synced
        self._sync_errors = errors

        if synced > 0:
            logger.info(f"Sync: {synced} itens sincronizados")

        return {"synced": synced, "errors": errors}

    async def _push_item(self, item: Dict) -> bool:
        """Envia um item para o servidor pai."""
        try:
            endpoint_map = {
                "conversation": "/api/chat/conversations",
                "message": "/api/chat/messages",
                "memory": "/api/memory",
                "calendar_event": "/api/calendar/events",
                "contact": "/api/contacts",
            }
            endpoint = endpoint_map.get(item["entity_type"])
            if not endpoint:
                return True  # Ignora tipos desconhecidos

            payload = json.loads(item["payload"]) if isinstance(item["payload"], str) else item["payload"]

            if item["operation"] == "create":
                resp = await self._client.post(endpoint, json=payload, timeout=10)
                return resp.status_code in [200, 201]
            elif item["operation"] == "update":
                resp = await self._client.put(f"{endpoint}/{item['entity_id']}", json=payload, timeout=10)
                return resp.status_code in [200, 204]
            elif item["operation"] == "delete":
                resp = await self._client.delete(f"{endpoint}/{item['entity_id']}", timeout=10)
                return resp.status_code in [200, 204, 404]  # 404 = já deletado = OK

        except Exception as e:
            logger.debug(f"Push item failed: {e}")
            return False

    async def _sync_item(self, item_id: str):
        """Sincroniza um item específico."""
        db = await get_db()
        cur = await db.execute("SELECT * FROM sync_queue WHERE id=?", (item_id,))
        row = await cur.fetchone()
        if row:
            success = await self._push_item(dict(row))
            if success:
                await db.execute(
                    "UPDATE sync_queue SET synced=1, synced_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), item_id)
                )
                await db.commit()

    async def pull_from_server(self) -> Dict[str, Any]:
        """Puxa dados do servidor pai para o mobile."""
        if not self._online:
            return {"pulled": 0, "error": "Offline"}

        pulled = 0
        try:
            # Puxa memórias recentes
            resp = await self._client.get("/api/memory?limit=50", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                memories = data.get("items", data if isinstance(data, list) else [])
                db = await get_db()
                for mem in memories:
                    await db.execute(
                        "INSERT OR IGNORE INTO memories VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            mem.get("id", str(uuid.uuid4())),
                            mem.get("type", "note"),
                            mem.get("content", ""),
                            mem.get("importance", 0.5),
                            mem.get("source", "server"),
                            json.dumps(mem.get("tags", [])),
                            mem.get("created_at", datetime.utcnow().isoformat()),
                            mem.get("updated_at", datetime.utcnow().isoformat()),
                            mem.get("expires_at"),
                            json.dumps(mem.get("meta", {}))
                        )
                    )
                    pulled += 1
                await db.commit()

            # Puxa eventos do calendário
            resp = await self._client.get("/api/calendar/events?days_ahead=30", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", data if isinstance(data, list) else [])
                db = await get_db()
                for ev in events:
                    await db.execute(
                        "INSERT OR IGNORE INTO calendar_events "
                        "(id, title, description, start_datetime, end_datetime, "
                        " location, all_day, recurrence, reminder_min, source, "
                        " external_id, status, platform, created_at, updated_at, meta) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            ev.get("id", str(uuid.uuid4())),
                            ev.get("title", ""),
                            ev.get("description"),
                            ev.get("start_datetime", ""),
                            ev.get("end_datetime"),
                            ev.get("location"),
                            1 if ev.get("all_day") else 0,
                            ev.get("recurrence"),
                            ev.get("reminder_min", 15),
                            "server",
                            ev.get("id"),
                            ev.get("status", "confirmed"),
                            ev.get("platform", "local"),
                            ev.get("created_at", datetime.utcnow().isoformat()),
                            ev.get("updated_at", datetime.utcnow().isoformat()),
                            json.dumps(ev.get("meta", {}))
                        )
                    )
                    pulled += 1
                await db.commit()

        except Exception as e:
            logger.error(f"Pull from server error: {e}")
            return {"pulled": pulled, "error": str(e)}

        logger.info(f"Pull sync: {pulled} itens recebidos do servidor")
        return {"pulled": pulled}

    async def get_status(self) -> Dict[str, Any]:
        """Retorna status da sincronização."""
        db = await get_db()
        cur = await db.execute("SELECT COUNT(*) as cnt FROM sync_queue WHERE synced=0")
        row = await cur.fetchone()
        pending = row["cnt"] if row else 0

        return {
            "online": self._online,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "pending_items": pending,
            "synced_today": self._synced_today,
            "errors": self._sync_errors[-5:],
            "parent_url": settings.parent_api_url,
        }

    async def cleanup(self):
        if self._client:
            await self._client.aclose()


sync_service = SyncService()
