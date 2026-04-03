"""
services/voice_service.py — TTS/STT, escuta contínua, palavra de ativação (LAS)
"""
import asyncio
import io
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from config import settings

logger = logging.getLogger(__name__)

AUDIO_DIR = Path(__file__).parent.parent / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logger.warning("SpeechRecognition não instalado")


class VoiceService:
    """TTS multimodo, STT, escuta contínua com wake word 'LAS'."""

    def __init__(self):
        self._listening = False
        self._always_on = False
        self._recognizer = None
        self._microphone = None
        self._callback: Optional[Callable] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._command_queue: queue.Queue = queue.Queue()
        self._current_call_audio = False
        self._last_tts_file: Optional[str] = None

    async def initialize(self):
        """Inicializa o serviço de voz."""
        if SR_AVAILABLE:
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = 300
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 0.8

        if settings.always_listen:
            await self.start_always_on()

        logger.info(f"✅ VoiceService inicializado. TTS: {settings.tts_backend}, Wake word: '{settings.wake_word}'")

    # ─── TTS ─────────────────────────────────────────────────────────────────

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = None,
        language: str = None,
        backend: Optional[str] = None,
    ) -> str:
        """Converte texto em áudio e retorna o caminho do arquivo."""
        voice = voice or settings.tts_voice
        speed = speed or settings.tts_speed
        language = language or settings.language
        backend = backend or settings.tts_backend
        filename = f"{uuid.uuid4()}.mp3"
        filepath = AUDIO_DIR / filename

        try:
            if backend == "edge-tts" and EDGE_TTS_AVAILABLE:
                await self._tts_edge(text, voice, speed, str(filepath))
            elif backend == "openai" and settings.openai_api_key:
                await self._tts_openai(text, voice, speed, str(filepath))
            elif backend == "piper":
                await self._tts_piper(text, str(filepath))
            else:
                # Fallback: edge-tts se disponível
                if EDGE_TTS_AVAILABLE:
                    await self._tts_edge(text, voice, speed, str(filepath))
                else:
                    raise RuntimeError("Nenhum backend TTS disponível")

            self._last_tts_file = str(filepath)
            logger.info(f"TTS gerado: {filename} ({len(text)} chars)")
            return f"/audio/{filename}"

        except Exception as e:
            logger.error(f"TTS error: {e}")
            raise

    async def _tts_edge(self, text: str, voice: str, speed: float, output: str):
        rate_str = f"+{int((speed - 1.0) * 100)}%" if speed >= 1.0 else f"{int((speed - 1.0) * 100)}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        await communicate.save(output)

    async def _tts_openai(self, text: str, voice: str, speed: float, output: str):
        import httpx
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        payload = {
            "model": "tts-1",
            "input": text,
            "voice": voice if voice in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] else "nova",
            "speed": speed,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.openai.com/v1/audio/speech",
                                     headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            with open(output, "wb") as f:
                f.write(resp.content)

    async def _tts_piper(self, text: str, output: str):
        proc = await asyncio.create_subprocess_exec(
            "piper", "--model", "pt_BR-faber-medium", "--output_file", output,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        await proc.communicate(input=text.encode())

    async def list_voices(self) -> list:
        """Lista vozes disponíveis (edge-tts)."""
        if EDGE_TTS_AVAILABLE:
            voices = await edge_tts.list_voices()
            return [v for v in voices if "pt-BR" in v["Locale"] or "pt-PT" in v["Locale"]]
        return [{"Name": settings.tts_voice, "Locale": "pt-BR"}]

    # ─── STT ─────────────────────────────────────────────────────────────────

    async def speech_to_text(self, audio_data: bytes, language: str = "pt-BR") -> Dict[str, Any]:
        """Converte áudio em texto."""
        if settings.openai_api_key:
            return await self._stt_whisper_api(audio_data, language)
        elif SR_AVAILABLE:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._stt_google, audio_data, language
            )
        else:
            return {"text": "", "confidence": 0.0, "error": "STT não disponível"}

    async def _stt_whisper_api(self, audio_data: bytes, language: str) -> Dict[str, Any]:
        import httpx
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        files = {"file": ("audio.wav", io.BytesIO(audio_data), "audio/wav")}
        data = {"model": "whisper-1", "language": language[:2]}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers, files=files, data=data
            )
            resp.raise_for_status()
            result = resp.json()
            return {"text": result["text"], "confidence": 0.9, "language": language}

    def _stt_google(self, audio_data: bytes, language: str) -> Dict[str, Any]:
        try:
            audio = sr.AudioData(audio_data, 16000, 2)
            text = self._recognizer.recognize_google(audio, language=language)
            return {"text": text, "confidence": 0.8, "language": language}
        except sr.UnknownValueError:
            return {"text": "", "confidence": 0.0, "error": "Não entendi"}
        except sr.RequestError as e:
            return {"text": "", "confidence": 0.0, "error": str(e)}

    # ─── Always-On Listening ─────────────────────────────────────────────────

    async def start_always_on(self, callback: Callable = None):
        """Inicia escuta contínua com detecção da wake word."""
        if self._listening:
            return
        self._listening = True
        self._always_on = True
        self._callback = callback
        self._stop_event.clear()
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        logger.info(f"🎙️ Escuta contínua ativada. Wake word: '{settings.wake_word}'")

    async def stop_always_on(self):
        """Para a escuta contínua."""
        self._stop_event.set()
        self._listening = False
        self._always_on = False
        logger.info("🔇 Escuta contínua desativada")

    def _listen_loop(self):
        """Loop de escuta em thread separada."""
        if not SR_AVAILABLE:
            logger.warning("SpeechRecognition não disponível - escuta simulada")
            return

        try:
            mic = sr.Microphone(sample_rate=16000)
        except Exception as e:
            logger.error(f"Microfone não disponível: {e}")
            return

        with mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=1)

        logger.info("🎙️ Microfone ativo, aguardando wake word...")

        while not self._stop_event.is_set():
            try:
                with mic as source:
                    audio = self._recognizer.listen(
                        source,
                        timeout=settings.voice_timeout_seconds,
                        phrase_time_limit=8
                    )

                # Primeiro reconhece para detectar wake word
                try:
                    text = self._recognizer.recognize_google(
                        audio, language=settings.language
                    )
                    logger.debug(f"STT detected: {text}")

                    wake = settings.wake_word.upper()
                    if wake in text.upper() or self._always_on:
                        # Remove wake word do texto
                        command = text.upper().replace(wake, "").strip()
                        if command:
                            self._command_queue.put({
                                "text": command,
                                "raw": text,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                            if self._callback:
                                asyncio.run_coroutine_threadsafe(
                                    self._callback(command), asyncio.get_event_loop()
                                )
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    logger.warning(f"STT service error: {e}")
                    time.sleep(2)

            except sr.WaitTimeoutError:
                pass
            except Exception as e:
                logger.error(f"Listen loop error: {e}")
                time.sleep(1)

    async def get_pending_commands(self) -> list:
        """Retorna comandos de voz pendentes."""
        commands = []
        while not self._command_queue.empty():
            try:
                commands.append(self._command_queue.get_nowait())
            except queue.Empty:
                break
        return commands

    # ─── Voice for Calls ─────────────────────────────────────────────────────

    async def speak_for_call(self, text: str) -> str:
        """TTS específico para chamadas (qualidade de telefone)."""
        return await self.text_to_speech(text, voice="pt-BR-FranciscaNeural", speed=1.0)

    async def get_audio_file_path(self, filename: str) -> Optional[str]:
        """Retorna caminho físico de arquivo de áudio."""
        path = AUDIO_DIR / filename
        if path.exists():
            return str(path)
        return None

    async def get_status(self) -> Dict[str, Any]:
        return {
            "listening": self._listening,
            "always_on": self._always_on,
            "wake_word": settings.wake_word,
            "tts_backend": settings.tts_backend,
            "stt_available": SR_AVAILABLE,
            "edge_tts_available": EDGE_TTS_AVAILABLE,
            "language": settings.language,
        }


voice_service = VoiceService()
