# ═══════════════════════════════════════════════════════════════════════════
# Personal AI Mobile — Dockerfile Multi-Stage
# Suporta Ubuntu Server, VPS, cloud (AWS/GCP/Azure)
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder (instala dependências) ─────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Dependências do sistema para compilar pacotes C (numpy, scikit-learn, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python em cache layer separado
COPY requirements.txt requirements-prod.txt* ./

RUN pip install --upgrade pip && \
    pip install --no-cache-dir wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Instala extras para produção
    pip install --no-cache-dir \
        asyncpg \
        psycopg2-binary \
        celery[redis] \
        flower \
        alembic \
        sqlalchemy[asyncio] \
        greenlet \
        gunicorn


# ── Stage 2: Production Image ────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL maintainer="Personal AI Mobile"
LABEL version="2.0.0"
LABEL description="Personal AI Mobile - FastAPI + PostgreSQL + Celery"

# Dependências de runtime (só o necessário)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libffi8 \
    libssl3 \
    curl \
    ffmpeg \
    # Para edge-tts e processamento de áudio
    && rm -rf /var/lib/apt/lists/*

# Usuário não-root para segurança
RUN groupadd -r personalai && useradd -r -g personalai -d /app -s /sbin/nologin personalai

WORKDIR /app

# Copia pacotes instalados do builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copia código da aplicação
COPY --chown=personalai:personalai . .

# Cria diretórios necessários
RUN mkdir -p data logs data/audio self_improvement/{patches,generated,tests} && \
    chown -R personalai:personalai /app

# Troca para usuário não-root
USER personalai

# Variáveis de ambiente padrão (podem ser sobrescritas)
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    PORT=8765

EXPOSE 8765

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Entrypoint padrão (FastAPI com uvicorn)
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8765", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "h11", \
     "--access-log", \
     "--log-level", "info"]


# ── Stage 3: Development (com hot-reload) ──────────────────────────────
FROM production AS development

USER root
RUN pip install --no-cache-dir watchfiles pytest pytest-asyncio

USER personalai

ENV APP_ENV=development

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8765", \
     "--reload", \
     "--reload-dir", "/app", \
     "--log-level", "debug"]
