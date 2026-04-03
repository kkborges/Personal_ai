"""
services/chat_service.py — Serviço de chat com contexto, memória e personalidade
"""
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional, Any

from config import settings
from database.db import get_db

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o Assistente Pessoal IA Mobile — um assistente inteligente, proativo e sempre disponível.

Características:
- Fala pt-BR de forma natural e amigável
- Pode controlar dispositivos Bluetooth, fazer ligações, gerenciar calendário
- Tem acesso a memórias e contexto do usuário
- Pode lançar apps, controlar Spotify, acessar e-mails e muito mais
- Opera em modo offline quando necessário
- Aprende com as preferências do usuário

Seja conciso nas respostas por voz, detalhado quando pedido por texto.
Sempre confirme ações importantes antes de executar."""


class ChatService:
    """Serviço de chat com contexto deslizante, memória e geração de respostas."""

    def __init__(self):
        self._context_window = 20  # mensagens
        self._active_sessions: Dict[str, List[Dict]] = {}

    async def initialize(self):
        logger.info("✅ ChatService inicializado")

    async def process_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        platform: str = "mobile",
        voice_response: bool = False,
        provider: Optional[str] = None,
        meta: Dict = None,
    ) -> Dict[str, Any]:
        """Processa mensagem e retorna resposta com contexto."""
        from services.provider_router import provider_router
        from services.memory_service import memory_service

        # Gerencia conversa
        if not conversation_id:
            conversation_id = await self._create_conversation(platform)

        # Adiciona mensagem ao histórico
        msg_id = await self._save_message(conversation_id, "user", message)

        # Carrega contexto
        history = await self._load_context(conversation_id)

        # Busca memórias relevantes
        memories = await memory_service.search(message, limit=5)
        memory_context = ""
        if memories:
            memory_context = "\n".join([f"- {m.content}" for m in memories])

        # Constrói mensagens para o LLM
        system = SYSTEM_PROMPT
        if memory_context:
            system += f"\n\nMemórias relevantes do usuário:\n{memory_context}"

        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        # Gera resposta
        result = await provider_router.complete(
            messages=messages,
            provider=provider,
            task_type="chat"
        )
        response_text = result["content"]

        # Salva resposta
        resp_id = await self._save_message(conversation_id, "assistant", response_text,
                                            tokens=result.get("tokens_out", 0))

        # Auto-extrai memórias
        await memory_service.auto_extract(message, response_text, conversation_id)

        # Gera áudio se solicitado
        audio_url = None
        if voice_response:
            try:
                from services.voice_service import voice_service
                audio_url = await voice_service.text_to_speech(response_text)
            except Exception as e:
                logger.warning(f"TTS error: {e}")

        # Sugestões proativas
        suggestions = await self._generate_suggestions(message, response_text)

        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "message_id": resp_id,
            "provider_used": result.get("provider", "unknown"),
            "tokens_used": result.get("tokens_out", 0),
            "audio_url": audio_url,
            "suggestions": suggestions,
            "memories_used": [m.id for m in memories],
        }

    async def stream_response(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta em streaming."""
        from services.provider_router import provider_router

        if not conversation_id:
            conversation_id = await self._create_conversation("mobile")

        history = await self._load_context(conversation_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        full_response = []
        async for chunk in provider_router.stream(messages=messages, provider=provider):
            full_response.append(chunk)
            yield chunk

        # Salva conversa completa
        await self._save_message(conversation_id, "user", message)
        await self._save_message(conversation_id, "assistant", "".join(full_response))

    async def get_conversations(self, platform: str = None, limit: int = 20) -> List[Dict]:
        """Lista conversas."""
        db = await get_db()
        if platform:
            cur = await db.execute(
                "SELECT c.*, COUNT(m.id) as message_count FROM conversations c "
                "LEFT JOIN messages m ON c.id = m.conversation_id "
                "WHERE c.platform=? GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?",
                (platform, limit)
            )
        else:
            cur = await db.execute(
                "SELECT c.*, COUNT(m.id) as message_count FROM conversations c "
                "LEFT JOIN messages m ON c.id = m.conversation_id "
                "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?",
                (limit,)
            )
        return [dict(r) for r in await cur.fetchall()]

    async def get_messages(self, conversation_id: str, limit: int = 50) -> List[Dict]:
        """Retorna mensagens de uma conversa."""
        db = await get_db()
        cur = await db.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit)
        )
        return [dict(r) for r in reversed(await cur.fetchall())]

    async def delete_conversation(self, conversation_id: str) -> bool:
        db = await get_db()
        await db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
        await db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
        await db.commit()
        return True

    # ─── Helpers ─────────────────────────────────────────────────────────────

    async def _create_conversation(self, platform: str) -> str:
        conv_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db = await get_db()
        await db.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            (conv_id, None, platform, now, now, "{}")
        )
        await db.commit()
        return conv_id

    async def _save_message(self, conv_id: str, role: str, content: str,
                             tokens: int = 0) -> str:
        msg_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db = await get_db()
        await db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
            (msg_id, conv_id, role, content, tokens, now, "{}")
        )
        await db.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?",
            (now, conv_id)
        )
        await db.commit()
        return msg_id

    async def _load_context(self, conv_id: str) -> List[Dict]:
        db = await get_db()
        cur = await db.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (conv_id, self._context_window)
        )
        rows = await cur.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def _generate_suggestions(self, user_msg: str, ai_response: str) -> List[str]:
        """Gera sugestões de próximos passos."""
        suggestions = []
        lower = user_msg.lower()

        if any(w in lower for w in ["reunião", "meeting", "compromisso"]):
            suggestions.append("Adicionar ao calendário")
        if any(w in lower for w in ["ligar", "chamar", "contato"]):
            suggestions.append("Fazer ligação")
        if any(w in lower for w in ["email", "e-mail", "mensagem"]):
            suggestions.append("Abrir email")
        if any(w in lower for w in ["música", "spotify", "tocar"]):
            suggestions.append("Abrir Spotify")
        if any(w in lower for w in ["lembrar", "lembrete", "não esquecer"]):
            suggestions.append("Criar lembrete")

        return suggestions[:3]


chat_service = ChatService()
