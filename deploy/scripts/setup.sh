#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# setup.sh — Provisionamento inicial do servidor Linux para Personal AI Mobile
# ─────────────────────────────────────────────────────────────────────────────
# Compatível com: Ubuntu 22.04 / 24.04 LTS, Debian 12
# Uso: sudo bash setup.sh [--domain yourdomain.com] [--email admin@yourdomain.com]
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Cores ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $*${NC}"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠️  $*${NC}"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ❌ $*${NC}" >&2; exit 1; }
info() { echo -e "${CYAN}[$(date '+%H:%M:%S')] ℹ️  $*${NC}"; }

# ── Argumentos ────────────────────────────────────────────────────────────────
DOMAIN=""
EMAIL=""
DATA_DIR="/opt/personal-ai/data"
APP_DIR="/opt/personal-ai/app"
DEPLOY_ENV="production"
SKIP_SSL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --domain)  DOMAIN="$2";  shift 2 ;;
        --email)   EMAIL="$2";   shift 2 ;;
        --data)    DATA_DIR="$2"; shift 2 ;;
        --app)     APP_DIR="$2";  shift 2 ;;
        --no-ssl)  SKIP_SSL=true; shift ;;
        *) warn "Argumento desconhecido: $1"; shift ;;
    esac
done

# ── Validações ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && err "Execute como root: sudo bash setup.sh"
[[ -z "$DOMAIN" && "$SKIP_SSL" == "false" ]] && {
    warn "Sem domínio definido — SSL será pulado"
    SKIP_SSL=true
}

# ── Sistema Operacional ───────────────────────────────────────────────────────
info "Detectando SO..."
. /etc/os-release
[[ "$ID" != "ubuntu" && "$ID" != "debian" ]] && warn "SO não testado: $ID $VERSION_ID"
log "SO: $PRETTY_NAME"

# ── Atualiza pacotes ──────────────────────────────────────────────────────────
info "Atualizando pacotes do sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip htop iotop \
    ca-certificates gnupg lsb-release \
    apt-transport-https software-properties-common \
    build-essential python3-pip python3-venv \
    postgresql-client redis-tools \
    ffmpeg portaudio19-dev libasound2-dev \
    ufw fail2ban certbot python3-certbot-nginx \
    jq net-tools
log "Pacotes do sistema instalados"

# ── Docker ────────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Instalando Docker..."
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.gpg] \
          https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    log "Docker instalado: $(docker --version)"
else
    log "Docker já instalado: $(docker --version)"
fi

# ── Docker Compose ────────────────────────────────────────────────────────────
if ! docker compose version &>/dev/null 2>&1; then
    info "Instalando Docker Compose plugin..."
    mkdir -p /usr/local/lib/docker/cli-plugins
    COMPOSE_VER=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | jq -r .tag_name)
    curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VER}/docker-compose-linux-$(uname -m)" \
         -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    log "Docker Compose instalado: $(docker compose version)"
fi

# ── Usuário deploy ────────────────────────────────────────────────────────────
if ! id -u deploy &>/dev/null; then
    info "Criando usuário 'deploy'..."
    useradd -m -s /bin/bash -G docker,sudo deploy
    mkdir -p /home/deploy/.ssh
    chmod 700 /home/deploy/.ssh
    log "Usuário 'deploy' criado"
fi
usermod -aG docker "$SUDO_USER" 2>/dev/null || true

# ── Diretórios de dados ────────────────────────────────────────────────────────
info "Criando diretórios de dados..."
mkdir -p \
    "${DATA_DIR}/postgres" \
    "${DATA_DIR}/redis" \
    "${DATA_DIR}/app" \
    "${DATA_DIR}/audio" \
    "${DATA_DIR}/certbot" \
    "${DATA_DIR}/pgadmin" \
    "/opt/personal-ai/logs" \
    "${APP_DIR}"

chown -R 1000:1000 "${DATA_DIR}/app" "${DATA_DIR}/audio" "/opt/personal-ai/logs"
chown -R 999:999   "${DATA_DIR}/postgres"
chown -R 5050:5050 "${DATA_DIR}/pgadmin" 2>/dev/null || true
chmod -R 750 "${DATA_DIR}"
log "Diretórios criados em ${DATA_DIR}"

# ── Firewall UFW ──────────────────────────────────────────────────────────────
info "Configurando firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp    comment "HTTP"
ufw allow 443/tcp   comment "HTTPS"
ufw --force enable
log "Firewall configurado"

# ── Fail2ban ──────────────────────────────────────────────────────────────────
info "Configurando fail2ban..."
cat > /etc/fail2ban/jail.local << 'FAIL2BAN'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s
backend = %(sshd_backend)s

[nginx-http-auth]
enabled  = true
port     = http,https
logpath  = /var/log/nginx/error.log
FAIL2BAN
systemctl enable --now fail2ban
log "Fail2ban configurado"

# ── Otimizações do kernel ─────────────────────────────────────────────────────
info "Aplicando otimizações do kernel..."
cat >> /etc/sysctl.conf << 'SYSCTL'
# Personal AI Mobile — Otimizações
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_local_port_range = 1024 65535
vm.overcommit_memory = 1
vm.swappiness = 10
fs.file-max = 1000000
SYSCTL
sysctl -p > /dev/null 2>&1
log "Kernel otimizado"

# ── Swap ─────────────────────────────────────────────────────────────────────
if [[ ! -f /swapfile ]]; then
    info "Criando swap de 4GB..."
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo "/swapfile none swap sw 0 0" >> /etc/fstab
    log "Swap criado"
fi

# ── Logrotate ─────────────────────────────────────────────────────────────────
cat > /etc/logrotate.d/personal-ai << LOGROTATE
/opt/personal-ai/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        docker kill --signal=USR1 ai-nginx 2>/dev/null || true
    endscript
}
LOGROTATE
log "Logrotate configurado"

# ── SSL Let's Encrypt ─────────────────────────────────────────────────────────
if [[ "$SKIP_SSL" == "false" && -n "$DOMAIN" && -n "$EMAIL" ]]; then
    info "Obtendo certificado SSL para ${DOMAIN}..."
    certbot certonly --standalone \
        -d "${DOMAIN}" \
        --email "${EMAIL}" \
        --agree-tos \
        --non-interactive \
        --no-eff-email || warn "SSL falhou — configure manualmente"

    # Cron para renovação automática
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet") | crontab -
    log "SSL configurado para ${DOMAIN}"
fi

# ── Arquivo .env de exemplo ───────────────────────────────────────────────────
if [[ ! -f "${APP_DIR}/.env" ]]; then
    cat > "${APP_DIR}/.env.example" << ENVFILE
# ═══════════ Personal AI Mobile — Configuração de Produção ════════════
# Copie para .env e preencha os valores reais
# ═══════════════════════════════════════════════════════════════════════

# ── App ────────────────────────────────────────────────────────────────
APP_ENV=production
SECRET_KEY=$(openssl rand -hex 32)
DOMAIN=${DOMAIN:-yourdomain.com}
CORS_ORIGINS=https://${DOMAIN:-yourdomain.com}

# ── PostgreSQL ─────────────────────────────────────────────────────────
POSTGRES_DB=personal_ai
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=$(openssl rand -hex 24)
DATA_DIR=${DATA_DIR}

# ── Redis ──────────────────────────────────────────────────────────────
REDIS_PASSWORD=$(openssl rand -hex 16)

# ── AI Providers ──────────────────────────────────────────────────────
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GENSPARK_API_KEY=...

# ── Voz ───────────────────────────────────────────────────────────────
TTS_BACKEND=edge-tts
TTS_VOICE=pt-BR-FranciscaNeural
LANGUAGE=pt-BR

# ── Integrações ───────────────────────────────────────────────────────
TELEGRAM_TOKEN=
WHATSAPP_API_KEY=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
OUTLOOK_CLIENT_ID=
OUTLOOK_CLIENT_SECRET=
OUTLOOK_TENANT_ID=

# ── Monitoramento ─────────────────────────────────────────────────────
FLOWER_USER=admin
FLOWER_PASSWORD=$(openssl rand -hex 12)
PGADMIN_EMAIL=admin@${DOMAIN:-example.com}
PGADMIN_PASSWORD=$(openssl rand -hex 12)
ENVFILE
    log ".env.example criado em ${APP_DIR}"
fi

# ── Resumo ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Personal AI Mobile — Setup Concluído ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✅ Docker:       $(docker --version)${NC}"
echo -e "${GREEN}✅ Compose:      $(docker compose version)${NC}"
echo -e "${GREEN}✅ Firewall:     UFW ativo${NC}"
echo -e "${GREEN}✅ Fail2ban:     Ativo${NC}"
[[ "$SKIP_SSL" == "false" ]] && echo -e "${GREEN}✅ SSL:          ${DOMAIN}${NC}" || warn "SSL: Não configurado"
echo ""
echo -e "${YELLOW}📋 Próximos passos:${NC}"
echo -e "  1. cd ${APP_DIR} && cp .env.example .env && nano .env"
echo -e "  2. bash deploy/scripts/deploy.sh"
echo ""
