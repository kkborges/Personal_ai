"""
config.py — Configurações centrais do Personal AI Mobile
==========================================================
Suporta múltiplos bancos de dados e brokers de mensagens:
  - SQLite  (dev/local): DATABASE_URL=sqlite+aiosqlite:///./data/mobile_ai.db
  - PostgreSQL (prod):   DATABASE_URL=postgresql+asyncpg://user:pass@host/db
  - Redis (Celery):      REDIS_URL=redis://localhost:6379/0

Deploy targets:
  - Local (SQLite + APScheduler)
  - Ubuntu Server / VPS (PostgreSQL + Redis + Celery)
  - Docker / Docker Compose
  - Cloud (AWS, GCP, Azure, Railway, Render)
"""
import os
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
WEB_DIR = BASE_DIR / "web"
SELF_IMPROVEMENT_DIR = BASE_DIR / "self_improvement"

for d in [DATA_DIR, LOGS_DIR, SELF_IMPROVEMENT_DIR / "patches",
          SELF_IMPROVEMENT_DIR / "generated", SELF_IMPROVEMENT_DIR / "tests"]:
    d.mkdir(parents=True, exist_ok=True)


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION  = "production"
    TESTING     = "testing"


class DatabaseBackend(str, Enum):
    SQLITE     = "sqlite"
    POSTGRESQL = "postgresql"


class WorkerBackend(str, Enum):
    APSCHEDULER = "apscheduler"   # Dev / single-process
    CELERY      = "celery"        # Prod / distribuído


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str    = "Personal AI Mobile"
    app_version: str = "2.0.0"
    app_env: AppEnv  = AppEnv.DEVELOPMENT
    host: str        = "0.0.0.0"
    port: int        = 8765
    debug: bool      = False
    secret_key: str  = "mobile-ai-secret-change-in-prod-32chars!!"
    language: str    = "pt-BR"

    # ── Database ─────────────────────────────────────────────────────────────
    # SQLite (padrão para dev): sqlite+aiosqlite:///./data/mobile_ai.db
    # PostgreSQL (prod):        postgresql+asyncpg://user:pass@host:5432/db
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR}/mobile_ai.db",
        description="URL de conexão com o banco de dados"
    )
    # Mantido para compatibilidade retroativa com código SQLite direto
    db_path: str = str(DATA_DIR / "mobile_ai.db")
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_database_url(cls, v: str) -> str:
        """Garante que o path do SQLite seja absoluto."""
        if v.startswith("sqlite") and "///" in v:
            path_part = v.split("///", 1)[1]
            if not path_part.startswith("/"):
                # Caminho relativo → absoluto
                abs_path = Path(path_part).resolve()
                return f"sqlite+aiosqlite:///{abs_path}"
        return v

    @property
    def db_backend(self) -> DatabaseBackend:
        if "sqlite" in self.database_url:
            return DatabaseBackend.SQLITE
        return DatabaseBackend.POSTGRESQL

    @property
    def is_postgres(self) -> bool:
        return self.db_backend == DatabaseBackend.POSTGRESQL

    # ── Redis & Celery ────────────────────────────────────────────────────────
    # Deixe em branco para usar APScheduler em vez de Celery
    redis_url: str             = ""    # redis://localhost:6379/0
    celery_broker_url: str     = ""    # redis://localhost:6379/1
    celery_result_backend: str = ""    # redis://localhost:6379/2

    @property
    def worker_backend(self) -> WorkerBackend:
        """Retorna Celery se Redis configurado, caso contrário APScheduler."""
        if self.redis_url or self.celery_broker_url:
            return WorkerBackend.CELERY
        return WorkerBackend.APSCHEDULER

    @property
    def use_celery(self) -> bool:
        return self.worker_backend == WorkerBackend.CELERY

    # ── Parent Web API (personal-ai web version) ──────────────────────────
    parent_api_url: str          = "http://localhost:8000"
    parent_api_key: str          = ""
    sync_interval_seconds: int   = 30
    sync_enabled: bool           = True

    # ── AI Providers ─────────────────────────────────────────────────────────
    openai_api_key: str     = ""
    anthropic_api_key: str  = ""
    google_api_key: str     = ""
    genspark_api_key: str   = ""
    ollama_base_url: str    = "http://localhost:11434"
    ollama_host: str        = ""   # alias para docker-compose
    default_provider: str   = "openai"   # openai | anthropic | gemini | ollama
    default_model: str      = "gpt-4o-mini"
    fallback_provider: str  = "ollama"
    autonomy_level: str     = "balanced" # passive | balanced | proactive

    @property
    def effective_ollama_url(self) -> str:
        return self.ollama_host or self.ollama_base_url

    # ── Voice ────────────────────────────────────────────────────────────────
    tts_backend: str           = "edge-tts"            # edge-tts | openai | piper
    tts_voice: str             = "pt-BR-FranciscaNeural"
    tts_speed: float           = 1.0
    stt_backend: str           = "whisper"             # whisper | google | sphinx
    always_listen: bool        = False
    wake_word: str             = "LAS"
    wake_word_sensitivity: float = 0.5
    voice_timeout_seconds: int = 5

    # ── Bluetooth ────────────────────────────────────────────────────────────
    bluetooth_enabled: bool    = True
    bluetooth_scan_duration: int = 10
    bluetooth_auto_connect: bool = True
    trusted_devices: str       = ""  # JSON list de MACs confiáveis

    # ── Telephony ────────────────────────────────────────────────────────────
    telephony_enabled: bool    = True
    sip_server: str            = ""
    sip_user: str              = ""
    sip_password: str          = ""
    gsm_modem_port: str        = ""  # ex: /dev/ttyUSB0

    # ── Platform Integrations ─────────────────────────────────────────────
    telegram_token: str            = ""
    alexa_skill_id: str            = ""
    alexa_client_id: str           = ""
    alexa_client_secret: str       = ""
    google_assistant_project_id: str = ""
    whatsapp_api_key: str          = ""
    whatsapp_phone_id: str         = ""
    outlook_client_id: str         = ""
    outlook_client_secret: str     = ""
    outlook_tenant_id: str         = ""
    teams_webhook_url: str         = ""
    spotify_client_id: str         = ""
    spotify_client_secret: str     = ""

    # ── Offline Mode ─────────────────────────────────────────────────────────
    offline_mode: bool              = False
    offline_queue_max: int          = 500
    connectivity_check_url: str     = "https://8.8.8.8"
    connectivity_check_interval: int = 15

    # ── Self-Monitoring & Self-Improvement ────────────────────────────────
    self_monitoring_enabled: bool       = True
    self_improvement_enabled: bool      = True
    monitoring_interval_seconds: int    = 60
    improvement_check_interval_hours: int = 6
    auto_deploy_patches: bool           = False
    max_memory_mb: int                  = 512
    max_cpu_percent: float              = 80.0

    # ── Job Queue ────────────────────────────────────────────────────────────
    max_concurrent_jobs: int  = 5
    job_timeout_seconds: int  = 300
    job_retry_max: int        = 3

    # ── Servidor Web ─────────────────────────────────────────────────────────
    uvicorn_workers: int      = 1   # >1 requer PostgreSQL (SQLite não é thread-safe em multi-worker)
    cors_origins: str         = "*"

    @property
    def cors_origins_list(self) -> list:
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",")]

    def summary(self) -> dict:
        """Retorna resumo das configurações (sem secrets)."""
        return {
            "app_env": self.app_env,
            "db_backend": self.db_backend,
            "worker_backend": self.worker_backend,
            "use_celery": self.use_celery,
            "is_postgres": self.is_postgres,
            "providers": {
                "openai": bool(self.openai_api_key),
                "anthropic": bool(self.anthropic_api_key),
                "google": bool(self.google_api_key),
                "ollama": bool(self.ollama_base_url),
            },
            "features": {
                "bluetooth": self.bluetooth_enabled,
                "telephony": self.telephony_enabled,
                "voice": True,
                "self_monitoring": self.self_monitoring_enabled,
                "sync": self.sync_enabled,
            }
        }

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "case_sensitive": False,
    }


settings = Settings()

