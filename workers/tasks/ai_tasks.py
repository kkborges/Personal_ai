"""
Celery Tasks — AI / LLM
========================
Tarefas de chamada a LLMs rodam em fila separada 'ai'
para isolar rate limiting e timeouts dos outros workers.
"""

import logging
from celery import shared_task
from workers.celery_app import run_async

logger = logging.getLogger(__name__)


@shared_task(
    name="workers.tasks.ai_tasks.send_ai_message",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="ai",
)
def send_ai_message(self, message: str, conversation_id: str = None,
                    provider: str = None, model: str = None,
                    system_prompt: str = None) -> dict:
    """
    Envia mensagem para LLM de forma assíncrona via Celery.
    Usado quando o cliente não precisa de streaming imediato.
    """
    try:
        async def _call():
            import sys, os
            sys.path.insert(0, "/app")
            from services.provider_router import ProviderRouter
            router = ProviderRouter()
            result = await router.route_request(
                messages=[{"role": "user", "content": message}],
                provider=provider,
                model=model,
                system_prompt=system_prompt,
            )
            return result

        result = run_async(_call())
        logger.info(f"AI task concluída: provider={result.get('provider_used')}")
        return result

    except Exception as exc:
        logger.error(f"Erro AI task: {exc}")
        raise self.retry(exc=exc, countdown=10)


@shared_task(
    name="workers.tasks.ai_tasks.extract_memory_facts",
    bind=True,
    max_retries=2,
    queue="ai",
)
def extract_memory_facts(self, text: str, conversation_id: str = None) -> dict:
    """
    Extrai fatos importantes de uma conversa para salvar na memória de longo prazo.
    Roda em background sem bloquear o chat.
    """
    try:
        async def _extract():
            import sys
            sys.path.insert(0, "/app")
            from services.memory_service import MemoryService
            svc = MemoryService()
            await svc.initialize()
            facts = await svc.extract_and_store_facts(text, conversation_id)
            return {"facts_extracted": len(facts), "facts": facts}

        return run_async(_extract())

    except Exception as exc:
        logger.warning(f"Extração de fatos falhou: {exc}")
        raise self.retry(exc=exc, countdown=30)


@shared_task(
    name="workers.tasks.ai_tasks.generate_improvement",
    bind=True,
    max_retries=1,
    queue="ai",
    time_limit=300,
)
def generate_improvement(self, metrics: dict) -> dict:
    """
    Gera sugestão de melhoria de código usando IA.
    Tarefa longa — pode levar até 5 minutos.
    """
    try:
        async def _improve():
            import sys
            sys.path.insert(0, "/app")
            from services.self_monitoring import SelfMonitoringService
            svc = SelfMonitoringService()
            await svc.initialize()
            return await svc.generate_improvement_patch(metrics)

        return run_async(_improve())

    except Exception as exc:
        logger.error(f"Geração de melhoria falhou: {exc}")
        raise self.retry(exc=exc)
