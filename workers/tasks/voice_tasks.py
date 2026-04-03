"""Celery Tasks — Voz (TTS e STT)."""

import logging
from celery import shared_task
from workers.celery_app import run_async

logger = logging.getLogger(__name__)


@shared_task(
    name="workers.tasks.voice_tasks.synthesize_speech",
    bind=True,
    max_retries=2,
    queue="voice",
    time_limit=60,
)
def synthesize_speech(self, text: str, voice: str = None,
                       speed: float = 1.0, output_format: str = "mp3") -> dict:
    """
    Sintetiza fala (TTS) em background.
    Útil para pré-gerar áudios de respostas longas.
    """
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.voice_service import VoiceService
        svc = VoiceService()
        await svc.initialize()
        audio_path = await svc.synthesize(text, voice=voice, speed=speed)
        return {"audio_path": audio_path, "text_length": len(text)}

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error(f"TTS falhou: {exc}")
        raise self.retry(exc=exc, countdown=5)


@shared_task(
    name="workers.tasks.voice_tasks.transcribe_audio",
    bind=True,
    max_retries=2,
    queue="voice",
    time_limit=120,
)
def transcribe_audio(self, audio_path: str, language: str = "pt-BR") -> dict:
    """
    Transcreve áudio (STT) em background via Whisper.
    """
    async def _run():
        import sys
        sys.path.insert(0, "/app")
        from services.voice_service import VoiceService
        svc = VoiceService()
        await svc.initialize()
        text = await svc.transcribe(audio_path, language=language)
        return {"text": text, "language": language}

    try:
        return run_async(_run())
    except Exception as exc:
        logger.error(f"STT falhou: {exc}")
        raise self.retry(exc=exc, countdown=10)
