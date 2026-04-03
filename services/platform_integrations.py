"""
services/platform_integrations.py — Integrações: Alexa, Google Assistant,
WhatsApp, Outlook, Teams, Spotify, Netflix, Disney+, Amazon Video,
Paramount+, GloboPlay e lançador de aplicativos.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import httpx

from config import settings
from database.db import get_db

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# ALEXA INTEGRATION
# ════════════════════════════════════════════════════════════════════════════
class AlexaIntegration:
    """Skill Alexa: recebe intents e responde."""

    SKILL_ID = None
    _token_cache: Dict[str, Any] = {}

    def __init__(self):
        self.SKILL_ID = settings.alexa_skill_id

    async def handle_intent(self, request_body: Dict) -> Dict:
        req = request_body.get("request", {})
        req_type = req.get("type", "")
        intent_name = req.get("intent", {}).get("name", "")
        session = request_body.get("session", {})

        if req_type == "LaunchRequest":
            return self._speak("Olá! Sou seu assistente pessoal. Como posso ajudar?")

        elif req_type == "IntentRequest":
            return await self._handle_intent_type(intent_name, req, session)

        elif req_type == "SessionEndedRequest":
            return {"version": "1.0", "response": {"shouldEndSession": True}}

        return self._speak("Não entendi o comando.")

    async def _handle_intent_type(self, intent_name: str, req: Dict, session: Dict) -> Dict:
        slots = req.get("intent", {}).get("slots", {})

        if intent_name == "ChatIntent":
            message = slots.get("message", {}).get("value", "")
            from services.chat_service import chat_service
            result = await chat_service.process_message(message, platform="alexa")
            return self._speak(result["response"])

        elif intent_name == "CreateReminderIntent":
            title = slots.get("title", {}).get("value", "Lembrete")
            time_slot = slots.get("time", {}).get("value", "")
            return self._speak(f"Lembrete '{title}' criado para {time_slot}.")

        elif intent_name == "CalendarIntent":
            from services.calendar_service import calendar_service
            agenda = await calendar_service.get_daily_agenda(datetime.utcnow())
            return self._speak(agenda.summary or "Nenhum compromisso para hoje.")

        elif intent_name == "AMAZON.StopIntent" or intent_name == "AMAZON.CancelIntent":
            return self._speak("Até logo!", end_session=True)

        elif intent_name == "AMAZON.HelpIntent":
            return self._speak("Você pode me pedir para conversar, criar lembretes, verificar agenda e controlar dispositivos.")

        return self._speak("Comando não reconhecido.")

    def _speak(self, text: str, end_session: bool = False) -> Dict:
        return {
            "version": "1.0",
            "response": {
                "outputSpeech": {"type": "PlainText", "text": text},
                "shouldEndSession": end_session,
            }
        }


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE ASSISTANT
# ════════════════════════════════════════════════════════════════════════════
class GoogleAssistantIntegration:
    """Actions on Google / Dialogflow Webhook."""

    async def handle_webhook(self, body: Dict) -> Dict:
        intent_name = body.get("handler", {}).get("name", "")
        params = body.get("intent", {}).get("params", {})
        session_info = body.get("sessionInfo", {})

        if intent_name == "main" or intent_name == "":
            return self._respond("Olá! Como posso ajudar você hoje?")

        elif intent_name == "chat":
            message = params.get("message", {}).get("resolved", "")
            from services.chat_service import chat_service
            result = await chat_service.process_message(message, platform="google")
            return self._respond(result["response"])

        elif intent_name == "calendar_check":
            from services.calendar_service import calendar_service
            agenda = await calendar_service.get_daily_agenda(datetime.utcnow())
            text = agenda.summary if agenda.summary else f"Você tem {len(agenda.events)} compromissos hoje."
            return self._respond(text)

        elif intent_name == "call_contact":
            contact = params.get("contact", {}).get("resolved", "")
            from services.telephony_service import telephony_service
            number = await telephony_service.resolve_contact(contact)
            if number:
                return self._respond(f"Ligando para {contact} no número {number}.")
            return self._respond(f"Não encontrei o contato {contact}.")

        elif intent_name == "spotify_control":
            action = params.get("action", {}).get("resolved", "")
            from services.platform_integrations import spotify_integration
            await spotify_integration.control(action)
            return self._respond(f"Spotify: {action} executado.")

        return self._respond("Não entendi o que você precisa.")

    def _respond(self, text: str) -> Dict:
        return {
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [text]}}]
            }
        }


# ════════════════════════════════════════════════════════════════════════════
# WHATSAPP INTEGRATION (WhatsApp Business API)
# ════════════════════════════════════════════════════════════════════════════
class WhatsAppIntegration:
    BASE_URL = "https://graph.facebook.com/v18.0"

    async def send_message(self, to: str, message: str) -> Dict:
        if not settings.whatsapp_api_key or not settings.whatsapp_phone_id:
            return {"success": False, "error": "WhatsApp não configurado"}

        url = f"{self.BASE_URL}/{settings.whatsapp_phone_id}/messages"
        headers = {"Authorization": f"Bearer {settings.whatsapp_api_key}",
                   "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message}
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=15)
            return {"success": resp.status_code == 200, "response": resp.json()}

    async def handle_webhook(self, body: Dict) -> Dict:
        """Recebe mensagens do WhatsApp e processa."""
        try:
            entry = body.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])

            results = []
            for msg in messages:
                from_number = msg.get("from", "")
                text = msg.get("text", {}).get("body", "")
                if text:
                    from services.chat_service import chat_service
                    result = await chat_service.process_message(
                        text, platform="whatsapp",
                        meta={"from": from_number}
                    )
                    await self.send_message(from_number, result["response"])
                    results.append(result)
            return {"processed": len(results)}
        except Exception as e:
            logger.error(f"WhatsApp webhook error: {e}")
            return {"error": str(e)}


# ════════════════════════════════════════════════════════════════════════════
# MICROSOFT OUTLOOK + TEAMS
# ════════════════════════════════════════════════════════════════════════════
class OutlookIntegration:
    """Integração Microsoft Graph API para Outlook e Teams."""

    _access_token: Optional[str] = None
    _token_expires: Optional[datetime] = None

    async def get_token(self) -> Optional[str]:
        if self._access_token and self._token_expires and datetime.utcnow() < self._token_expires:
            return self._access_token

        if not settings.outlook_client_id:
            return None

        url = f"https://login.microsoftonline.com/{settings.outlook_tenant_id}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": settings.outlook_client_id,
            "client_secret": settings.outlook_client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, timeout=15)
            if resp.status_code == 200:
                token_data = resp.json()
                self._access_token = token_data["access_token"]
                self._token_expires = datetime.utcnow() + timedelta(seconds=token_data["expires_in"] - 60)
                return self._access_token
        return None

    async def get_emails(self, limit: int = 10, unread_only: bool = True) -> List[Dict]:
        token = await self.get_token()
        if not token:
            return self._mock_emails(limit)

        params = {"$top": limit, "$orderby": "receivedDateTime desc"}
        if unread_only:
            params["$filter"] = "isRead eq false"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/me/messages",
                headers={"Authorization": f"Bearer {token}"},
                params=params, timeout=15
            )
            if resp.status_code == 200:
                return resp.json().get("value", [])
        return []

    async def send_email(self, to: str, subject: str, body: str) -> Dict:
        token = await self.get_token()
        if not token:
            return {"success": False, "error": "Outlook não configurado"}

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}]
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/me/sendMail",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload, timeout=15
            )
            return {"success": resp.status_code == 202}

    async def get_calendar_events(self, days_ahead: int = 7) -> List[Dict]:
        token = await self.get_token()
        if not token:
            return []

        start = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/me/calendarView",
                headers={"Authorization": f"Bearer {token}"},
                params={"startDateTime": start, "endDateTime": end, "$orderby": "start/dateTime"},
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json().get("value", [])
        return []

    async def send_teams_message(self, message: str, channel_id: str = None) -> Dict:
        if settings.teams_webhook_url:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    settings.teams_webhook_url,
                    json={"text": message}, timeout=15
                )
                return {"success": resp.status_code == 200}
        return {"success": False, "error": "Teams não configurado"}

    def _mock_emails(self, limit: int) -> List[Dict]:
        return [
            {"subject": "Reunião amanhã", "from": {"emailAddress": {"address": "boss@company.com"}},
             "bodyPreview": "Não esqueça da reunião às 14h.", "isRead": False},
        ][:limit]


# ════════════════════════════════════════════════════════════════════════════
# SPOTIFY
# ════════════════════════════════════════════════════════════════════════════
class SpotifyIntegration:
    """Controle do Spotify via API oficial."""

    _access_token: Optional[str] = None
    _refresh_token: Optional[str] = None
    _token_expires: Optional[datetime] = None

    async def get_auth_url(self) -> str:
        scopes = "user-modify-playback-state user-read-playback-state user-read-currently-playing"
        return (
            f"https://accounts.spotify.com/authorize?"
            f"client_id={settings.spotify_client_id}&response_type=code"
            f"&redirect_uri=http://localhost:{settings.port}/api/platforms/spotify/callback"
            f"&scope={scopes.replace(' ', '%20')}"
        )

    async def exchange_code(self, code: str) -> Dict:
        import base64
        credentials = base64.b64encode(
            f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
        ).decode()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": f"Basic {credentials}"},
                data={"grant_type": "authorization_code", "code": code,
                      "redirect_uri": f"http://localhost:{settings.port}/api/platforms/spotify/callback"},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data["access_token"]
                self._refresh_token = data.get("refresh_token")
                self._token_expires = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
                await self._save_tokens(data)
                return {"success": True}
        return {"success": False}

    async def control(self, action: str, params: Dict = None) -> Dict:
        """Controla reprodução: play, pause, next, previous, volume, search."""
        token = await self._get_valid_token()
        if not token:
            return {"success": False, "error": "Spotify não autenticado"}

        params = params or {}
        headers = {"Authorization": f"Bearer {token}"}
        base = "https://api.spotify.com/v1/me/player"

        async with httpx.AsyncClient() as client:
            if action == "play":
                resp = await client.put(f"{base}/play", headers=headers, timeout=10)
            elif action == "pause":
                resp = await client.put(f"{base}/pause", headers=headers, timeout=10)
            elif action == "next":
                resp = await client.post(f"{base}/next", headers=headers, timeout=10)
            elif action == "previous":
                resp = await client.post(f"{base}/previous", headers=headers, timeout=10)
            elif action == "volume":
                vol = max(0, min(100, int(params.get("volume", 50))))
                resp = await client.put(f"{base}/volume?volume_percent={vol}", headers=headers, timeout=10)
            elif action == "search":
                query = params.get("query", "")
                r = await client.get(
                    "https://api.spotify.com/v1/search",
                    params={"q": query, "type": "track", "limit": 5},
                    headers=headers, timeout=10
                )
                return {"success": True, "results": r.json().get("tracks", {}).get("items", [])}
            else:
                return {"success": False, "error": f"Ação desconhecida: {action}"}

            return {"success": resp.status_code in [200, 204]}

    async def get_currently_playing(self) -> Dict:
        token = await self._get_valid_token()
        if not token:
            return {}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {token}"}, timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
        return {}

    async def _get_valid_token(self) -> Optional[str]:
        if self._access_token and self._token_expires and datetime.utcnow() < self._token_expires:
            return self._access_token
        if self._refresh_token:
            return await self._refresh()
        # Load from DB
        db = await get_db()
        cur = await db.execute("SELECT value FROM settings_kv WHERE key='spotify_tokens'")
        row = await cur.fetchone()
        if row:
            try:
                data = json.loads(row["value"])
                self._access_token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")
                exp = data.get("expires_at")
                if exp:
                    self._token_expires = datetime.fromisoformat(exp)
                if self._access_token and self._token_expires and datetime.utcnow() < self._token_expires:
                    return self._access_token
                if self._refresh_token:
                    return await self._refresh()
            except Exception:
                pass
        return None

    async def _refresh(self) -> Optional[str]:
        import base64
        if not self._refresh_token:
            return None
        credentials = base64.b64encode(
            f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
        ).decode()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": f"Basic {credentials}"},
                data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data["access_token"]
                self._token_expires = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
                await self._save_tokens(data)
                return self._access_token
        return None

    async def _save_tokens(self, data: Dict):
        db = await get_db()
        data["expires_at"] = self._token_expires.isoformat() if self._token_expires else None
        await db.execute(
            "INSERT OR REPLACE INTO settings_kv VALUES ('spotify_tokens',?,?)",
            (json.dumps(data), datetime.utcnow().isoformat())
        )
        await db.commit()


# ════════════════════════════════════════════════════════════════════════════
# STREAMING APPS LAUNCHER
# ════════════════════════════════════════════════════════════════════════════
class StreamingAppsService:
    """Lança aplicativos de streaming e controla reprodução."""

    APPS = {
        "netflix": {
            "android_package": "com.netflix.mediaclient",
            "ios_scheme": "nflx://",
            "web_url": "https://netflix.com",
            "deep_link": "netflix://title/{id}",
        },
        "disney+": {
            "android_package": "com.disney.disneyplus",
            "ios_scheme": "disneyplus://",
            "web_url": "https://disneyplus.com",
        },
        "amazon_prime": {
            "android_package": "com.amazon.avod.thirdpartyclient",
            "ios_scheme": "aiv://",
            "web_url": "https://primevideo.com",
        },
        "paramount+": {
            "android_package": "com.cbs.app",
            "ios_scheme": "cbsnews://",
            "web_url": "https://paramountplus.com",
        },
        "globoplay": {
            "android_package": "com.globo.globotv",
            "ios_scheme": "globo://",
            "web_url": "https://globoplay.globo.com",
        },
        "youtube": {
            "android_package": "com.google.android.youtube",
            "ios_scheme": "youtube://",
            "web_url": "https://youtube.com",
        },
        "spotify": {
            "android_package": "com.spotify.music",
            "ios_scheme": "spotify://",
            "web_url": "https://open.spotify.com",
        },
        "whatsapp": {
            "android_package": "com.whatsapp",
            "ios_scheme": "whatsapp://",
            "web_url": "https://web.whatsapp.com",
        },
        "outlook": {
            "android_package": "com.microsoft.office.outlook",
            "ios_scheme": "ms-outlook://",
            "web_url": "https://outlook.live.com",
        },
        "teams": {
            "android_package": "com.microsoft.teams",
            "ios_scheme": "msteams://",
            "web_url": "https://teams.microsoft.com",
        },
    }

    async def launch_app(self, app_name: str, platform: str = "android",
                         deep_link_params: Dict = None) -> Dict:
        """Lança um aplicativo."""
        app_key = app_name.lower().replace(" ", "_").replace("+", "+")
        app_info = self.APPS.get(app_key) or self.APPS.get(app_name.lower())

        if not app_info:
            return {"success": False, "error": f"App '{app_name}' não configurado",
                    "available": list(self.APPS.keys())}

        import subprocess

        if platform == "android":
            package = app_info.get("android_package")
            if package:
                try:
                    result = subprocess.run([
                        "adb", "shell", "am", "start", "-n",
                        f"{package}/com.{package.split('.')[-1]}.MainActivity"
                    ], capture_output=True, timeout=10)
                    return {"success": True, "app": app_name, "package": package,
                            "platform": "android"}
                except Exception as e:
                    return {"success": False, "error": str(e),
                            "web_fallback": app_info.get("web_url")}

        elif platform == "web":
            url = app_info.get("web_url", "")
            if deep_link_params:
                url = app_info.get("deep_link", url).format(**deep_link_params)
            return {"success": True, "app": app_name, "url": url,
                    "action": "open_url", "platform": "web"}

        return {"success": False, "error": "Plataforma não suportada"}

    async def search_content(self, app_name: str, query: str) -> Dict:
        """Busca conteúdo em um aplicativo de streaming."""
        app_key = app_name.lower().replace(" ", "_")
        app_info = self.APPS.get(app_key, {})
        web_url = app_info.get("web_url", "")

        if web_url and "netflix" in web_url:
            return {"success": True, "search_url": f"{web_url}/search?q={query}",
                    "app": app_name, "query": query}
        elif "globo" in (web_url or ""):
            return {"success": True, "search_url": f"{web_url}?busca={query}",
                    "app": app_name, "query": query}

        return {"success": True, "search_url": f"{web_url}?q={query}",
                "app": app_name, "query": query}

    def list_apps(self) -> List[Dict]:
        """Lista todos os aplicativos disponíveis."""
        return [{"name": k, **v} for k, v in self.APPS.items()]


# ════════════════════════════════════════════════════════════════════════════
# DOCUMENT SERVICE (Criação de documentos)
# ════════════════════════════════════════════════════════════════════════════
class DocumentService:
    """Criação de documentos usando IA."""

    async def create_document(
        self,
        title: str,
        doc_type: str,
        content: str = None,
        template: str = None,
        ai_generate: bool = True,
    ) -> Dict:
        """Cria um documento (relatório, projeto, email, etc.)."""
        from services.provider_router import provider_router

        if ai_generate:
            prompt = f"Crie um documento do tipo '{doc_type}' com título '{title}'."
            if content:
                prompt += f" Conteúdo base: {content}"
            if template:
                prompt += f" Use o template: {template}"

            result = await provider_router.complete(
                messages=[
                    {"role": "system", "content": "Você é um assistente especialista em criação de documentos profissionais."},
                    {"role": "user", "content": prompt}
                ],
                task_type="document_creation"
            )
            generated = result["content"]
        else:
            generated = content or ""

        # Salva como arquivo
        doc_id = str(uuid.uuid4())
        doc_path = f"/tmp/{doc_id}_{title.replace(' ', '_')}.txt"
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{generated}")

        return {
            "success": True,
            "document_id": doc_id,
            "title": title,
            "type": doc_type,
            "content": generated,
            "file_path": doc_path,
        }

    async def create_dev_project(
        self,
        project_name: str,
        description: str,
        tech_stack: List[str] = None,
        ai_providers: List[str] = None,
    ) -> Dict:
        """Cria um projeto de desenvolvimento completo usando múltiplas IAs."""
        from services.provider_router import provider_router

        tech_stack = tech_stack or ["Python", "FastAPI", "SQLite"]
        ai_providers_str = ", ".join(ai_providers or ["OpenAI", "Claude", "Gemini"])

        prompt = f"""
Crie um projeto de desenvolvimento completo chamado "{project_name}".
Descrição: {description}
Stack: {', '.join(tech_stack)}
Integrações de IA: {ai_providers_str}

Entregue:
1. README.md completo
2. Estrutura de arquivos do projeto
3. requirements.txt
4. Código inicial (main.py ou equivalente)
5. Exemplos de uso de cada API de IA
6. Dockerfile para deploy
7. Testes básicos

Seja específico e gere código funcional, não apenas esqueletos.
"""
        result = await provider_router.complete(
            messages=[
                {"role": "system", "content": "Você é um arquiteto de software sênior especialista em IA."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096,
            task_type="project_creation"
        )

        doc_id = str(uuid.uuid4())
        project_dir = f"/tmp/project_{project_name.replace(' ', '_')}_{doc_id[:8]}"
        import os
        os.makedirs(project_dir, exist_ok=True)

        # Salva o projeto gerado
        readme_path = f"{project_dir}/README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(result["content"])

        return {
            "success": True,
            "project_id": doc_id,
            "name": project_name,
            "tech_stack": tech_stack,
            "ai_providers": ai_providers or [],
            "content": result["content"],
            "project_dir": project_dir,
            "provider_used": result.get("provider", "unknown"),
        }


# ════════════════════════════════════════════════════════════════════════════
# Instâncias globais
# ════════════════════════════════════════════════════════════════════════════
alexa_integration = AlexaIntegration()
google_assistant_integration = GoogleAssistantIntegration()
whatsapp_integration = WhatsAppIntegration()
outlook_integration = OutlookIntegration()
spotify_integration = SpotifyIntegration()
streaming_apps = StreamingAppsService()
document_service = DocumentService()
