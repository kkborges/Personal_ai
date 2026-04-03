#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# Personal AI Mobile — Script de Instalação para Ubuntu Server 22.04 / 24.04
# ═══════════════════════════════════════════════════════════════════════════
# Uso: sudo bash deploy/install_ubuntu.sh [--with-postgres] [--with-celery] [--with-nginx]
#
# Modos de instalação:
#   Básico (SQLite):          sudo bash install_ubuntu.sh
#   Com PostgreSQL:           sudo bash install_ubuntu.sh --with-postgres
#   Completo (prod full):     sudo bash install_ubuntu.sh --with-postgres --with-celery --with-nginx

set -euo pipefail

# ── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
head() { echo -e "\n${BLUE}══ $* ══${NC}"; }

# ── Argumentos ───────────────────────────────────────────────────────────────
WITH_POSTGRES=false
WITH_CELERY=false
WITH_NGINX=false
WITH_OLLAMA=false

for arg in "$@"; do
    case $arg in
        --with-postgres) WITH_POSTGRES=true ;;
        --with-celery)   WITH_CELERY=true ;;
        --with-nginx)    WITH_NGINX=true ;;
        --with-ollama)   WITH_OLLAMA=true ;;
        --full)          WITH_POSTGRES=true; WITH_CELERY=true; WITH_NGINX=true ;;
    esac
done

# ── Verificações ─────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && err "Execute como root: sudo bash install_ubuntu.sh"
[[ -f /etc/os-release ]] || err "Sistema não suportado"

APP_DIR="/opt/personal-ai-mobile"
APP_USER="personalai"
APP_PORT=8765

head "Personal AI Mobile — Instalação Ubuntu"
log "Modo: SQLite=${!WITH_POSTGRES} PostgreSQL=$WITH_POSTGRES Celery=$WITH_CELERY Nginx=$WITH_NGINX"

# ── 1. Sistema ───────────────────────────────────────────────────────────────
head "Atualizando sistema"
apt-get update -qq
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    git curl wget ffmpeg \
    build-essential libffi-dev libssl-dev \
    supervisor \
    --no-install-recommends

# ── 2. PostgreSQL (opcional) ──────────────────────────────────────────────────
if $WITH_POSTGRES; then
    head "Instalando PostgreSQL 16"
    apt-get install -y -qq postgresql-16 postgresql-client-16 libpq-dev
    
    PG_DB="personal_ai"
    PG_USER="personal_ai"
    PG_PASS=$(openssl rand -base64 24)
    
    sudo -u postgres psql -c "CREATE USER $PG_USER WITH PASSWORD '$PG_PASS';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE $PG_DB OWNER $PG_USER;" 2>/dev/null || true
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $PG_DB TO $PG_USER;" 2>/dev/null || true
    
    log "PostgreSQL configurado"
    log "  DB: $PG_DB | User: $PG_USER | Pass: $PG_PASS"
    echo "DATABASE_URL=postgresql+asyncpg://$PG_USER:$PG_PASS@localhost:5432/$PG_DB" > /tmp/pg_env
fi

# ── 3. Redis (para Celery) ────────────────────────────────────────────────────
if $WITH_CELERY; then
    head "Instalando Redis"
    apt-get install -y -qq redis-server
    
    # Configuração básica de segurança
    REDIS_PASS=$(openssl rand -base64 16)
    sed -i "s/# requirepass foobared/requirepass $REDIS_PASS/" /etc/redis/redis.conf
    sed -i "s/# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/" /etc/redis/redis.conf
    echo "maxmemory 256mb" >> /etc/redis/redis.conf
    
    systemctl enable redis-server
    systemctl restart redis-server
    
    log "Redis configurado (senha: $REDIS_PASS)"
    REDIS_URL="redis://:$REDIS_PASS@localhost:6379"
fi

# ── 4. Nginx (reverse proxy) ──────────────────────────────────────────────────
if $WITH_NGINX; then
    head "Instalando Nginx"
    apt-get install -y -qq nginx certbot python3-certbot-nginx
    
    cat > /etc/nginx/sites-available/personal-ai << EOF
server {
    listen 80;
    server_name _;
    
    client_max_body_size 50M;
    
    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }
}
EOF
    
    ln -sf /etc/nginx/sites-available/personal-ai /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl enable nginx && systemctl reload nginx
    log "Nginx configurado"
fi

# ── 5. Usuário e diretório ────────────────────────────────────────────────────
head "Criando usuário e diretório da aplicação"
useradd -r -s /sbin/nologin -d $APP_DIR $APP_USER 2>/dev/null || true

if [[ -d $APP_DIR ]]; then
    warn "$APP_DIR já existe, fazendo backup..."
    mv $APP_DIR "${APP_DIR}.bak.$(date +%Y%m%d%H%M%S)"
fi

# Copia arquivos (assumindo que estamos no diretório do projeto)
cp -r . $APP_DIR
chown -R $APP_USER:$APP_USER $APP_DIR

# ── 6. Ambiente Python ────────────────────────────────────────────────────────
head "Configurando ambiente Python"
sudo -u $APP_USER python3.11 -m venv $APP_DIR/.venv
sudo -u $APP_USER $APP_DIR/.venv/bin/pip install --upgrade pip -q
sudo -u $APP_USER $APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt -q

# Extras para produção
EXTRA_PKGS="uvloop h11"
$WITH_POSTGRES && EXTRA_PKGS="$EXTRA_PKGS asyncpg psycopg2-binary"
$WITH_CELERY && EXTRA_PKGS="$EXTRA_PKGS celery[redis] flower"

sudo -u $APP_USER $APP_DIR/.venv/bin/pip install $EXTRA_PKGS -q
log "Ambiente Python configurado"

# ── 7. Arquivo .env ───────────────────────────────────────────────────────────
head "Configurando variáveis de ambiente"
ENV_FILE="$APP_DIR/.env"

cat > $ENV_FILE << EOF
APP_ENV=production
SECRET_KEY=$(openssl rand -base64 32)
PORT=$APP_PORT
LANGUAGE=pt-BR
EOF

if $WITH_POSTGRES && [[ -f /tmp/pg_env ]]; then
    cat /tmp/pg_env >> $ENV_FILE
    rm /tmp/pg_env
fi

if $WITH_CELERY; then
    cat >> $ENV_FILE << EOF
REDIS_URL=$REDIS_URL/0
CELERY_BROKER_URL=$REDIS_URL/1
CELERY_RESULT_BACKEND=$REDIS_URL/2
EOF
fi

chown $APP_USER:$APP_USER $ENV_FILE
chmod 600 $ENV_FILE
log ".env criado em $ENV_FILE"

# ── 8. Banco de dados ─────────────────────────────────────────────────────────
head "Inicializando banco de dados"
mkdir -p $APP_DIR/data $APP_DIR/logs
chown $APP_USER:$APP_USER $APP_DIR/data $APP_DIR/logs

if $WITH_POSTGRES; then
    # Importa schema PostgreSQL
    sudo -u postgres psql personal_ai < $APP_DIR/database/init_postgres.sql
    log "Schema PostgreSQL importado"
fi

# ── 9. Supervisor (gerenciador de processos) ──────────────────────────────────
head "Configurando Supervisor"
VENV="$APP_DIR/.venv"

cat > /etc/supervisor/conf.d/personal-ai.conf << EOF
[program:personal-ai-app]
command=$VENV/bin/uvicorn main:app --host 0.0.0.0 --port $APP_PORT --workers 2
directory=$APP_DIR
user=$APP_USER
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=30
environment=PYTHONPATH="$APP_DIR"
stdout_logfile=$APP_DIR/logs/app.log
stderr_logfile=$APP_DIR/logs/app_error.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
EOF

if $WITH_CELERY; then
    cat >> /etc/supervisor/conf.d/personal-ai.conf << EOF

[program:personal-ai-worker]
command=$VENV/bin/celery -A workers.celery_app worker --loglevel=info --concurrency=4 -Q default,ai,voice,sync,routines
directory=$APP_DIR
user=$APP_USER
autostart=true
autorestart=true
stopwaitsecs=60
environment=PYTHONPATH="$APP_DIR"
stdout_logfile=$APP_DIR/logs/worker.log
stderr_logfile=$APP_DIR/logs/worker_error.log

[program:personal-ai-beat]
command=$VENV/bin/celery -A workers.celery_app beat --loglevel=info
directory=$APP_DIR
user=$APP_USER
autostart=true
autorestart=true
environment=PYTHONPATH="$APP_DIR"
stdout_logfile=$APP_DIR/logs/beat.log
stderr_logfile=$APP_DIR/logs/beat_error.log
EOF
fi

cat >> /etc/supervisor/conf.d/personal-ai.conf << EOF

[group:personal-ai]
programs=personal-ai-app$([ "$WITH_CELERY" = "true" ] && echo ",personal-ai-worker,personal-ai-beat")
EOF

supervisorctl reread
supervisorctl update
supervisorctl start personal-ai:*

log "Supervisor configurado"

# ── 10. Firewall ──────────────────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    ufw allow 22/tcp comment "SSH" 2>/dev/null || true
    ufw allow 80/tcp comment "HTTP" 2>/dev/null || true
    ufw allow 443/tcp comment "HTTPS" 2>/dev/null || true
    $WITH_NGINX || ufw allow $APP_PORT/tcp comment "Personal AI" 2>/dev/null || true
fi

# ── Resumo ────────────────────────────────────────────────────────────────────
head "Instalação concluída!"
echo ""
log "Personal AI Mobile instalado em: $APP_DIR"
log "Usuário do serviço: $APP_USER"
log ""
log "URLs de acesso:"
IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
if $WITH_NGINX; then
    log "  http://$IP  (via Nginx)"
else
    log "  http://$IP:$APP_PORT"
fi
log "  http://localhost:$APP_PORT/health"
log "  http://localhost:$APP_PORT/docs"
echo ""
log "Comandos úteis:"
log "  supervisorctl status                    # Ver status dos serviços"
log "  supervisorctl restart personal-ai:*     # Reiniciar tudo"
log "  tail -f $APP_DIR/logs/app.log           # Ver logs"
$WITH_CELERY && log "  $VENV/bin/celery -A workers.celery_app flower --port=5555  # Monitor Celery"
echo ""
warn "IMPORTANTE: Edite $ENV_FILE com suas chaves de API!"
warn "Depois: supervisorctl restart personal-ai:*"
