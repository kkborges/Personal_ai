#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# start.sh — Script de inicialização do Personal AI Mobile
# ═══════════════════════════════════════════════════════════════════════

set -e

echo "🤖 Personal AI Mobile — Inicializando..."
echo "================================================"

# Diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cria diretórios necessários
mkdir -p data/audio logs self_improvement/{patches,generated,tests}

# Verifica Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado!"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION encontrado"

# Verifica e instala dependências
if [ ! -f ".venv/bin/python" ]; then
    echo "📦 Criando ambiente virtual..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "📦 Instalando dependências..."
pip install -r requirements.txt -q --no-warn-script-location

# Verifica arquivo .env
if [ ! -f ".env" ]; then
    echo "⚙️ Criando .env padrão..."
    cat > .env << 'ENVEOF'
# Personal AI Mobile — Configurações
# Copie e configure suas chaves de API

APP_NAME=Personal AI Mobile
PORT=8765
DEBUG=false
LANGUAGE=pt-BR

# ── IA Providers ─────────────────────────────────────────────────────
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
GENSPARK_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_PROVIDER=openai
DEFAULT_MODEL=gpt-4o-mini
FALLBACK_PROVIDER=ollama

# ── Voice ─────────────────────────────────────────────────────────────
TTS_BACKEND=edge-tts
TTS_VOICE=pt-BR-FranciscaNeural
ALWAYS_LISTEN=false
WAKE_WORD=LAS

# ── Autonomy ──────────────────────────────────────────────────────────
AUTONOMY_LEVEL=balanced

# ── Sync com Personal AI Web ──────────────────────────────────────────
PARENT_API_URL=http://localhost:8000
SYNC_ENABLED=true
SYNC_INTERVAL_SECONDS=30

# ── Platforms ─────────────────────────────────────────────────────────
TELEGRAM_TOKEN=
WHATSAPP_API_KEY=
WHATSAPP_PHONE_ID=
OUTLOOK_CLIENT_ID=
OUTLOOK_CLIENT_SECRET=
OUTLOOK_TENANT_ID=
TEAMS_WEBHOOK_URL=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
ALEXA_SKILL_ID=

# ── Bluetooth / Telephony ─────────────────────────────────────────────
BLUETOOTH_ENABLED=true
TELEPHONY_ENABLED=true
SIP_SERVER=
SIP_USER=
SIP_PASSWORD=
GSM_MODEM_PORT=

# ── Self-Monitoring ───────────────────────────────────────────────────
SELF_MONITORING_ENABLED=true
SELF_IMPROVEMENT_ENABLED=true
AUTO_DEPLOY_PATCHES=false
MONITORING_INTERVAL_SECONDS=60
ENVEOF
    echo "✅ .env criado. Configure suas chaves em .env antes de continuar."
fi

# Carrega variáveis de ambiente
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs -d '\n') 2>/dev/null || true
fi

PORT=${PORT:-8765}
HOST=${HOST:-0.0.0.0}

echo ""
echo "🌐 Iniciando servidor em http://$HOST:$PORT"
echo "📚 Documentação: http://localhost:$PORT/docs"
echo "📱 Interface Mobile: http://localhost:$PORT"
echo ""
echo "Pressione Ctrl+C para parar."
echo "================================================"

# Inicia o servidor
python3 -m uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    --access-log
