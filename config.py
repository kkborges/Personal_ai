"""
config.py — Configurações centrais do Personal AI Mobile
Carrega variáveis de ambiente com defaults seguros para uso offline/mobile.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
WEB_DIR = BASE_DIR / "web"
SELF_IMPROVEMENT_DIR = BASE_DIR / "self_improvement"

for d in [DATA_DIR, LOGS_DIR, SELF_IMPROVEMENT_DIR / "patches",
          SELF_IMPROVEMENT_DIR / "generated", SELF_IMPROVEMENT_DIR / "tests"]:
    d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "Personal AI Mobile"
    app_version: str = "2.0.0"
    host: str = "0.0.0.0"
    port: int = 8765
    debug: bool = False
    secret_key: str = "mobile-ai-secret-change-in-prod-2024"
    language: str = "pt-BR"

    # ── Database ─────────────────────────────────────────────────────────────
    db_path: str = str(DATA_DIR / "mobile_ai.db")
    db_echo: bool = False

    # ── Parent Web API (personal-ai web version) ──────────────────────────
    parent_api_url: str = "http://localhost:8000"
    parent_api_key: str = ""
    sync_interval_seconds: int = 30
    sync_enabled: bool = True

    # ── AI Providers ─────────────────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    genspark_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_provider: str = "openai"          # openai | anthropic | gemini | ollama
    default_model: str = "gpt-4o-mini"
    fallback_provider: str = "ollama"
    autonomy_level: str = "balanced"          # passive | balanced | proactive

    # ── Voice ────────────────────────────────────────────────────────────────
    tts_backend: str = "edge-tts"             # edge-tts | openai | piper
    tts_voice: str = "pt-BR-FranciscaNeural"
    tts_speed: float = 1.0
    stt_backend: str = "whisper"              # whisper | google | sphinx (offline)
    always_listen: bool = False               # escuta contínua
    wake_word: str = "LAS"                    # palavra de ativação
    wake_word_sensitivity: float = 0.5
    voice_timeout_seconds: int = 5

    # ── Bluetooth ────────────────────────────────────────────────────────────
    bluetooth_enabled: bool = True
    bluetooth_scan_duration: int = 10
    bluetooth_auto_connect: bool = True
    trusted_devices: str = ""                 # JSON list de MACs confiáveis

    # ── Telephony ────────────────────────────────────────────────────────────
    telephony_enabled: bool = True
    sip_server: str = ""
    sip_user: str = ""
    sip_password: str = ""
    gsm_modem_port: str = ""                  # ex: /dev/ttyUSB0

    # ── Platform Integrations ─────────────────────────────────────────────
    telegram_token: str = ""
    alexa_skill_id: str = ""
    alexa_client_id: str = ""
    alexa_client_secret: str = ""
    google_assistant_project_id: str = ""
    whatsapp_api_key: str = ""
    whatsapp_phone_id: str = ""
    outlook_client_id: str = ""
    outlook_client_secret: str = ""
    outlook_tenant_id: str = ""
    teams_webhook_url: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""

    # ── Offline Mode ─────────────────────────────────────────────────────────
    offline_mode: bool = False
    offline_queue_max: int = 500
    connectivity_check_url: str = "https://8.8.8.8"
    connectivity_check_interval: int = 15

    # ── Self-Monitoring & Self-Improvement ────────────────────────────────
    self_monitoring_enabled: bool = True
    self_improvement_enabled: bool = True
    monitoring_interval_seconds: int = 60
    improvement_check_interval_hours: int = 6
    auto_deploy_patches: bool = False         # False = apenas propõe, True = aplica
    max_memory_mb: int = 512
    max_cpu_percent: float = 80.0

    # ── Job Queue ────────────────────────────────────────────────────────────
    max_concurrent_jobs: int = 5
    job_timeout_seconds: int = 300
    job_retry_max: int = 3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
