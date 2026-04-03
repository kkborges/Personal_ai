#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# deploy.sh — Deploy / Update do Personal AI Mobile em produção
# ─────────────────────────────────────────────────────────────────────────────
# Uso: bash deploy/scripts/deploy.sh [--branch main] [--no-build] [--rollback]
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; NC='\033[0m'

log()     { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $*${NC}"; }
warn()    { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠️  $*${NC}"; }
err()     { echo -e "${RED}[$(date '+%H:%M:%S')] ❌ $*${NC}" >&2; exit 1; }
info()    { echo -e "${CYAN}[$(date '+%H:%M:%S')] ℹ️  $*${NC}"; }
step()    { echo -e "${BLUE}[$(date '+%H:%M:%S')] 🚀 $*${NC}"; }

# ── Argumentos ────────────────────────────────────────────────────────────────
BRANCH="main"
NO_BUILD=false
ROLLBACK=false
COMPOSE_FILE="docker-compose.prod.yml"
PROFILES=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --branch)   BRANCH="$2";       shift 2 ;;
        --no-build) NO_BUILD=true;     shift ;;
        --rollback) ROLLBACK=true;     shift ;;
        --profile)  PROFILES="$PROFILES --profile $2"; shift 2 ;;
        --file)     COMPOSE_FILE="$2"; shift 2 ;;
        *) warn "Argumento desconhecido: $1"; shift ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Verificações ──────────────────────────────────────────────────────────────
[[ ! -f "${APP_DIR}/.env" ]] && err ".env não encontrado em ${APP_DIR}"
cd "${APP_DIR}"

# Carrega variáveis
set -a; source .env; set +a

DOCKER_COMPOSE="docker compose -f ${COMPOSE_FILE} ${PROFILES}"

# ── Rollback ──────────────────────────────────────────────────────────────────
if [[ "$ROLLBACK" == "true" ]]; then
    step "Iniciando rollback..."
    if [[ -f ".env.backup" ]]; then
        cp .env.backup .env
        log ".env restaurado"
    fi
    # Tenta usar imagem anterior tagged como 'previous'
    $DOCKER_COMPOSE down --remove-orphans
    docker tag personal-ai-app:previous personal-ai-app:latest 2>/dev/null || warn "Sem imagem 'previous' disponível"
    $DOCKER_COMPOSE up -d
    log "Rollback concluído"
    exit 0
fi

# ── Backup de segurança ───────────────────────────────────────────────────────
step "Fazendo backup antes do deploy..."
cp .env .env.backup
BACKUP_DATE=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="/opt/personal-ai/backups/backup_${BACKUP_DATE}.sql"
mkdir -p /opt/personal-ai/backups

# Backup PostgreSQL
if docker ps | grep -q "ai-postgres"; then
    docker exec ai-postgres pg_dump \
        -U "${POSTGRES_USER:-ai_user}" \
        "${POSTGRES_DB:-personal_ai}" \
        --no-password \
        > "${BACKUP_FILE}" 2>/dev/null && log "Backup PostgreSQL: ${BACKUP_FILE}" || warn "Backup PostgreSQL falhou"
fi

# Remove backups com mais de 7 dias
find /opt/personal-ai/backups -name "*.sql" -mtime +7 -delete 2>/dev/null || true

# ── Git Pull ──────────────────────────────────────────────────────────────────
step "Atualizando código da branch ${BRANCH}..."
git fetch --all
git checkout "${BRANCH}"
git pull origin "${BRANCH}"
COMMIT=$(git rev-parse --short HEAD)
log "Código atualizado: ${COMMIT}"

# ── Build das imagens ─────────────────────────────────────────────────────────
if [[ "$NO_BUILD" == "false" ]]; then
    step "Buildando imagens Docker..."
    # Preserva imagem atual como 'previous' para rollback
    docker tag personal-ai-app:latest personal-ai-app:previous 2>/dev/null || true

    $DOCKER_COMPOSE build \
        --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --build-arg GIT_COMMIT="${COMMIT}" \
        --no-cache
    log "Build concluído"
fi

# ── Deploy dos serviços ────────────────────────────────────────────────────────
step "Fazendo deploy dos serviços..."

# Pull de imagens externas
$DOCKER_COMPOSE pull --ignore-pull-failures 2>/dev/null || true

# Cria diretórios de dados necessários
mkdir -p \
    "${DATA_DIR:-/opt/personal-ai/data}/postgres" \
    "${DATA_DIR:-/opt/personal-ai/data}/redis" \
    "${DATA_DIR:-/opt/personal-ai/data}/app" \
    "${DATA_DIR:-/opt/personal-ai/data}/audio" \
    "${DATA_DIR:-/opt/personal-ai/data}/certbot" \
    "/opt/personal-ai/logs"

# Sobe serviços com zero-downtime para o app
info "Reiniciando PostgreSQL e Redis..."
$DOCKER_COMPOSE up -d --no-recreate postgres redis

info "Aguardando banco de dados estar pronto..."
timeout 60 bash -c "until docker exec ai-postgres pg_isready -U ${POSTGRES_USER:-ai_user} 2>/dev/null; do sleep 2; done"
log "PostgreSQL pronto"

info "Reiniciando aplicação (rolling update)..."
$DOCKER_COMPOSE up -d --no-deps app
sleep 5

# Health check após deploy
MAX_TRIES=12
for i in $(seq 1 $MAX_TRIES); do
    if curl -sf "http://localhost:${APP_PORT:-8765}/health" > /dev/null 2>&1; then
        log "Health check OK após $((i * 5))s"
        break
    fi
    if [[ $i -eq $MAX_TRIES ]]; then
        err "Health check falhou após $((MAX_TRIES * 5))s — considere rollback"
    fi
    sleep 5
done

info "Reiniciando Celery workers..."
$DOCKER_COMPOSE up -d --no-deps celery-worker celery-beat

info "Reiniciando Nginx..."
$DOCKER_COMPOSE up -d --no-deps nginx

# ── Limpeza ───────────────────────────────────────────────────────────────────
step "Limpando recursos Docker antigos..."
docker image prune -f --filter "until=48h" > /dev/null 2>&1 || true
docker container prune -f > /dev/null 2>&1 || true

# ── Status final ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Personal AI Mobile — Deploy Concluído  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""
$DOCKER_COMPOSE ps
echo ""
HEALTH=$(curl -sf "http://localhost:${APP_PORT:-8765}/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "?")
log "App health: ${HEALTH}"
log "Commit: ${COMMIT}"
log "Deploy finalizado às $(date)"
echo ""
echo -e "${YELLOW}URLs de acesso:${NC}"
echo -e "  🌐 Web:    https://${DOMAIN:-localhost}"
echo -e "  📖 Docs:   https://${DOMAIN:-localhost}/docs"
echo -e "  🌸 Flower: https://${DOMAIN:-localhost}/flower"
echo ""
