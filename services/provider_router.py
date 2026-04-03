"""
services/provider_router.py — Roteador de provedores de IA com fallback automático
"""
import time
import uuid
import logging
import asyncio
from typing import AsyncGenerator, Optional, Dict, Any, List
import httpx
from config import settings
from database.db import get_db

logger = logging.getLogger(__name__)


class ProviderRouter:
    """Roteia requisições de IA para diferentes provedores com fallback e telemetria."""

    def __init__(self):
        self.providers_order = self._build_order()
        self.rate_limits: Dict[str, List[float]] = {}  # provider -> timestamps
        self._client = httpx.AsyncClient(timeout=60)

    def _build_order(self) -> List[str]:
        order = []
        if settings.openai_api_key:
            order.append("openai")
        if settings.anthropic_api_key:
            order.append("anthropic")
        if settings.google_api_key:
            order.append("gemini")
        if settings.genspark_api_key:
            order.append("genspark")
        order.append("ollama")   # always last (local fallback)
        return order

    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider: Optional[str] = None,
        task_type: str = "chat",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        providers_to_try = [provider] if provider else self.providers_order
        last_error = None

        for p in providers_to_try:
            if not self._check_rate_limit(p):
                continue
            try:
                start = time.time()
                result = await self._call_provider(p, messages, model, max_tokens, temperature)
                elapsed_ms = int((time.time() - start) * 1000)
                await self._log_usage(p, model or "default", result, elapsed_ms, task_type)
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {p} failed: {e}, trying next...")

        # All failed → graceful degradation
        logger.error(f"All providers failed. Last error: {last_error}")
        return {
            "content": "Estou sem conectividade com serviços de IA no momento. Posso ajudá-lo com funções offline como calendário, lembretes e controle de dispositivos.",
            "provider": "offline",
            "tokens_in": 0,
            "tokens_out": 0,
        }

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        p = provider or (self.providers_order[0] if self.providers_order else "ollama")
        try:
            async for chunk in self._stream_provider(p, messages, model, max_tokens, temperature):
                yield chunk
        except Exception as e:
            logger.error(f"Stream failed from {p}: {e}")
            yield "Erro ao gerar resposta em tempo real. Tente novamente."

    # ─── Provider Implementations ────────────────────────────────────────────

    async def _call_provider(self, provider: str, messages, model, max_tokens, temperature) -> Dict:
        if provider == "openai":
            return await self._openai(messages, model or "gpt-4o-mini", max_tokens, temperature)
        elif provider == "anthropic":
            return await self._anthropic(messages, model or "claude-3-haiku-20240307", max_tokens, temperature)
        elif provider == "gemini":
            return await self._gemini(messages, model or "gemini-1.5-flash", max_tokens, temperature)
        elif provider == "genspark":
            return await self._genspark(messages, model or "gpt-4o", max_tokens, temperature)
        else:
            return await self._ollama(messages, model or "llama3.2", max_tokens, temperature)

    async def _openai(self, messages, model, max_tokens, temperature) -> Dict:
        headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        resp = await self._client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "provider": "openai",
            "model": model,
            "tokens_in": data["usage"]["prompt_tokens"],
            "tokens_out": data["usage"]["completion_tokens"],
        }

    async def _anthropic(self, messages, model, max_tokens, temperature) -> Dict:
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_messages = [m for m in messages if m["role"] != "system"]
        payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                   "system": system_msg, "messages": user_messages}
        resp = await self._client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["content"][0]["text"],
            "provider": "anthropic",
            "model": model,
            "tokens_in": data["usage"]["input_tokens"],
            "tokens_out": data["usage"]["output_tokens"],
        }

    async def _gemini(self, messages, model, max_tokens, temperature) -> Dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.google_api_key}"
        parts = [{"text": m["content"]} for m in messages if m["role"] == "user"]
        payload = {"contents": [{"parts": parts}], "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return {
            "content": content,
            "provider": "gemini",
            "model": model,
            "tokens_in": usage.get("promptTokenCount", 0),
            "tokens_out": usage.get("candidatesTokenCount", 0),
        }

    async def _genspark(self, messages, model, max_tokens, temperature) -> Dict:
        headers = {"Authorization": f"Bearer {settings.genspark_api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        resp = await self._client.post("https://api.genspark.ai/v1/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "provider": "genspark",
            "model": model,
            "tokens_in": data.get("usage", {}).get("prompt_tokens", 0),
            "tokens_out": data.get("usage", {}).get("completion_tokens", 0),
        }

    async def _ollama(self, messages, model, max_tokens, temperature) -> Dict:
        payload = {"model": model, "messages": messages, "stream": False,
                   "options": {"num_predict": max_tokens, "temperature": temperature}}
        try:
            resp = await self._client.post(f"{settings.ollama_base_url}/api/chat", json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return {
                "content": data["message"]["content"],
                "provider": "ollama",
                "model": model,
                "tokens_in": data.get("prompt_eval_count", 0),
                "tokens_out": data.get("eval_count", 0),
            }
        except Exception:
            raise ConnectionError("Ollama não disponível localmente")

    async def _stream_provider(self, provider, messages, model, max_tokens, temperature) -> AsyncGenerator[str, None]:
        if provider == "openai":
            headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
            payload = {"model": model or "gpt-4o-mini", "messages": messages,
                       "max_tokens": max_tokens, "temperature": temperature, "stream": True}
            async with self._client.stream("POST", "https://api.openai.com/v1/chat/completions",
                                           headers=headers, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        import json
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            pass
        else:
            result = await self._call_provider(provider, messages, model, max_tokens, temperature)
            yield result["content"]

    # ─── Rate Limit ──────────────────────────────────────────────────────────

    def _check_rate_limit(self, provider: str) -> bool:
        limits = {"openai": 60, "anthropic": 40, "gemini": 60, "genspark": 30, "ollama": 200}
        window = 60
        now = time.time()
        times = self.rate_limits.setdefault(provider, [])
        self.rate_limits[provider] = [t for t in times if now - t < window]
        if len(self.rate_limits[provider]) >= limits.get(provider, 60):
            return False
        self.rate_limits[provider].append(now)
        return True

    async def _log_usage(self, provider, model, result, elapsed_ms, task_type):
        try:
            db = await get_db()
            cost = self._estimate_cost(provider, model, result.get("tokens_in", 0), result.get("tokens_out", 0))
            await db.execute(
                "INSERT INTO provider_usage VALUES (?,?,?,?,?,?,?,1,?)",
                (str(uuid.uuid4()), provider, model,
                 result.get("tokens_in", 0), result.get("tokens_out", 0),
                 cost, elapsed_ms, task_type)
            )
            await db.commit()
        except Exception as e:
            logger.debug(f"Usage log error: {e}")

    def _estimate_cost(self, provider, model, t_in, t_out) -> float:
        prices = {
            ("openai", "gpt-4o"): (0.0025, 0.01),
            ("openai", "gpt-4o-mini"): (0.00015, 0.0006),
            ("anthropic", "claude-3-haiku-20240307"): (0.00025, 0.00125),
            ("gemini", "gemini-1.5-flash"): (0.000075, 0.0003),
        }
        p_in, p_out = prices.get((provider, model), (0.001, 0.002))
        return round((t_in * p_in + t_out * p_out) / 1000, 6)

    async def get_stats(self) -> Dict[str, Any]:
        db = await get_db()
        cur = await db.execute(
            "SELECT provider, COUNT(*) as calls, SUM(tokens_in+tokens_out) as tokens, "
            "SUM(cost_usd) as cost, AVG(latency_ms) as avg_latency "
            "FROM provider_usage WHERE created_at > datetime('now','-24 hours') GROUP BY provider"
        )
        rows = await cur.fetchall()
        return {r["provider"]: dict(r) for r in rows}


provider_router = ProviderRouter()
