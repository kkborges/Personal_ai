# ═══════════════════════════════════════════════════════════════════════════════
# Personal AI Mobile — Dockerfile Multi-Stage
# ─────────────────────────────────────────────
# Stages:
#   base        → Python deps system + venv
#   development → base + dev tools (sem otimização de tamanho)
#   production  → base otimizado, sem root, sem cache pip
# ═══════════════════════════════════════════════════════════════════════════════

# ── Base ──────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# Metadados
LABEL maintainer="Personal AI Mobile"
LABEL version="2.0.0"
LABEL description="Sistema de IA Pessoal com voz, Bluetooth e autonomia"

# Variáveis de ambiente Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Dependências de sistema (ffmpeg para áudio, libpq para PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libpq-dev \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    portaudio19-dev \
    libasound2-dev \
    bluetooth \
    libbluetooth-dev \
    && rm -rf /var/lib/apt/lists/*

# Cria virtualenv
RUN python -m venv $VIRTUAL_ENV

# Copia e instala dependências Python
COPY requirements.prod.txt /tmp/requirements.prod.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements.prod.txt

# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs /app/data/audio \
             /app/self_improvement/patches \
             /app/self_improvement/generated \
             /app/self_improvement/tests

EXPOSE 8765

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8765", "--reload"]

# ── Production ────────────────────────────────────────────────────────────────
FROM base AS production

# Usuário não-root
RUN groupadd -r aiuser && useradd -r -g aiuser -d /app -s /sbin/nologin aiuser

WORKDIR /app

# Copia apenas o necessário (sem .git, sem testes, sem cache)
COPY --chown=aiuser:aiuser . .

# Remove arquivos desnecessários em produção
RUN find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find . -name "*.pyc" -delete \
    && find . -name "*.pyo" -delete \
    && rm -rf .git tests/ *.md

# Cria diretórios necessários
RUN mkdir -p /app/data /app/logs /app/data/audio \
             /app/self_improvement/patches \
             /app/self_improvement/generated \
             /app/self_improvement/tests \
    && chown -R aiuser:aiuser /app

# Instala gunicorn para produção
RUN pip install gunicorn==23.0.0

USER aiuser

# Health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8765/health || exit 1

EXPOSE 8765

# Gunicorn com UvicornWorker (multi-process)
CMD ["gunicorn", "main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "--bind", "0.0.0.0:8765", \
     "--timeout", "120", \
     "--keepalive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
