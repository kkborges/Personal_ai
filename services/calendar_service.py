"""
services/calendar_service.py — Calendário local com CRUD, recorrências e iCal
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any

from config import settings
from database.db import get_db
from models.schemas import CalendarEventCreate, CalendarEvent, DailyAgenda

logger = logging.getLogger(__name__)


class CalendarService:
    async def initialize(self):
        logger.info("✅ CalendarService inicializado")

    async def create_event(self, event: CalendarEventCreate) -> CalendarEvent:
        ev_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db = await get_db()
        await db.execute(
            "INSERT INTO calendar_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ev_id, event.title, event.description,
             event.start_datetime.isoformat(),
             event.end_datetime.isoformat() if event.end_datetime else None,
             event.location, 1 if event.all_day else 0,
             event.recurrence, event.reminder_min,
             event.platform or "local", event.external_id,
             "confirmed", event.platform or "local", now, now,
             json.dumps(event.meta))
        )
        await db.commit()

        # Queue sync
        try:
            from services.sync_service import sync_service
            await sync_service.queue_operation("calendar_event", ev_id, "create", event.model_dump(mode="json"))
        except Exception:
            pass

        return CalendarEvent(id=ev_id, status="confirmed",
                             created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
                             **event.model_dump())

    async def get_event(self, ev_id: str) -> Optional[Dict]:
        db = await get_db()
        cur = await db.execute("SELECT * FROM calendar_events WHERE id=?", (ev_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_event(self, ev_id: str, updates: Dict) -> Optional[Dict]:
        db = await get_db()
        updates["updated_at"] = datetime.utcnow().isoformat()
        fields = ", ".join([f"{k}=?" for k in updates.keys()])
        values = list(updates.values()) + [ev_id]
        await db.execute(f"UPDATE calendar_events SET {fields} WHERE id=?", values)
        await db.commit()
        return await self.get_event(ev_id)

    async def delete_event(self, ev_id: str) -> bool:
        db = await get_db()
        await db.execute("DELETE FROM calendar_events WHERE id=?", (ev_id,))
        await db.commit()
        return True

    async def get_events(self, start: datetime = None, end: datetime = None,
                          platform: str = None) -> List[Dict]:
        db = await get_db()
        q = "SELECT * FROM calendar_events WHERE 1=1"
        params = []
        if start:
            q += " AND start_datetime >= ?"
            params.append(start.isoformat())
        if end:
            q += " AND start_datetime <= ?"
            params.append(end.isoformat())
        if platform:
            q += " AND platform=?"
            params.append(platform)
        q += " ORDER BY start_datetime ASC"
        cur = await db.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]

    async def get_daily_agenda(self, day: datetime) -> DailyAgenda:
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        events = await self.get_events(start, end)

        cal_events = []
        for e in events:
            try:
                cal_events.append(CalendarEvent(
                    id=e["id"], title=e["title"],
                    description=e.get("description"),
                    start_datetime=datetime.fromisoformat(e["start_datetime"]),
                    end_datetime=datetime.fromisoformat(e["end_datetime"]) if e.get("end_datetime") else None,
                    location=e.get("location"),
                    all_day=bool(e.get("all_day")),
                    reminder_min=e.get("reminder_min", 15),
                    platform=e.get("platform", "local"),
                    status=e.get("status", "confirmed"),
                    created_at=datetime.fromisoformat(e["created_at"]),
                    updated_at=datetime.fromisoformat(e["updated_at"]),
                ))
            except Exception:
                pass

        if not cal_events:
            summary = f"Sem compromissos para {day.strftime('%d/%m/%Y')}."
        else:
            items = []
            for ev in cal_events:
                time_str = ev.start_datetime.strftime("%H:%M")
                items.append(f"{time_str} - {ev.title}")
            summary = f"Compromissos para {day.strftime('%d/%m/%Y')}: " + "; ".join(items)

        return DailyAgenda(
            date=day.strftime("%Y-%m-%d"),
            events=cal_events,
            summary=summary
        )

    async def get_upcoming_events(self, hours: int = 24) -> List[Dict]:
        now = datetime.utcnow()
        end = now + timedelta(hours=hours)
        return await self.get_events(now, end)

    async def check_conflicts(self, start: datetime, end: datetime, exclude_id: str = None) -> List[Dict]:
        db = await get_db()
        q = ("SELECT * FROM calendar_events WHERE "
             "start_datetime < ? AND (end_datetime > ? OR end_datetime IS NULL)")
        params = [end.isoformat(), start.isoformat()]
        if exclude_id:
            q += " AND id != ?"
            params.append(exclude_id)
        cur = await db.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]

    async def export_ical(self) -> str:
        events = await self.get_events()
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//Personal AI Mobile//PT//",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH"
        ]
        for ev in events:
            start = ev["start_datetime"].replace("-", "").replace(":", "").replace("T", "T")[:15] + "Z"
            end_dt = ev.get("end_datetime", ev["start_datetime"])
            if end_dt:
                end = end_dt.replace("-", "").replace(":", "").replace("T", "T")[:15] + "Z"
            else:
                end = start
            lines += [
                "BEGIN:VEVENT",
                f"UID:{ev['id']}",
                f"DTSTART:{start}",
                f"DTEND:{end}",
                f"SUMMARY:{ev['title']}",
                f"DESCRIPTION:{ev.get('description', '')}",
                "END:VEVENT"
            ]
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    async def import_ical(self, ical_content: str) -> int:
        try:
            from icalendar import Calendar
            cal = Calendar.from_ical(ical_content)
            imported = 0
            for component in cal.walk():
                if component.name == "VEVENT":
                    try:
                        start = component.get("dtstart").dt
                        if isinstance(start, date) and not isinstance(start, datetime):
                            start = datetime.combine(start, datetime.min.time())
                        end = component.get("dtend")
                        if end:
                            end = end.dt
                            if isinstance(end, date) and not isinstance(end, datetime):
                                end = datetime.combine(end, datetime.min.time())
                        event = CalendarEventCreate(
                            title=str(component.get("summary", "Sem título")),
                            description=str(component.get("description", "")),
                            start_datetime=start,
                            end_datetime=end,
                            location=str(component.get("location", "")) or None,
                            external_id=str(component.get("uid", "")),
                            platform="ical_import",
                        )
                        await self.create_event(event)
                        imported += 1
                    except Exception as e:
                        logger.debug(f"iCal event import error: {e}")
            return imported
        except ImportError:
            logger.warning("icalendar não instalado")
            return 0

    async def natural_language_event(self, text: str) -> Optional[Dict]:
        """Cria evento a partir de texto em linguagem natural."""
        from services.provider_router import provider_router
        prompt = f"""
Extraia informações de evento a partir deste texto e retorne JSON:
"{text}"

JSON esperado:
{{
  "title": "Nome do evento",
  "start_datetime": "YYYY-MM-DDTHH:MM:SS",
  "end_datetime": "YYYY-MM-DDTHH:MM:SS ou null",
  "location": "local ou null",
  "description": "descrição ou null",
  "reminder_min": 15
}}

Data atual: {datetime.utcnow().isoformat()}
Responda APENAS com o JSON, sem explicações.
"""
        try:
            result = await provider_router.complete(
                messages=[{"role": "user", "content": prompt}],
                task_type="calendar_extraction",
                temperature=0.1
            )
            import re
            json_match = re.search(r'\{.*\}', result["content"], re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                event = CalendarEventCreate(**data)
                created = await self.create_event(event)
                return created.model_dump(mode="json")
        except Exception as e:
            logger.error(f"NL event creation error: {e}")
        return None


calendar_service = CalendarService()
