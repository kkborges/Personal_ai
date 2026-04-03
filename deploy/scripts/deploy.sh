#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# deploy.sh — Deploy / Update do Personal AI Mobile em produção
# ─────────────────────────────────────────────────────────────────────────────
# Uso: bash deploy/scripts/deploy.sh [opções]
#
# Opções:
#   --branch  <branch>   Branch git a usar (padrão: main)
#   --repo    <url>      URL do repositório git para clonar/atualizar
#   --no-git             Não usa git — apenas reconstrói com os arquivos atuais
#   --no-build           Não reconstrói as imagens Docker
#   --rollback           Reverte para a versão anterior
#   --profile <perfil>   Adiciona perfil Docker Compose (ex: monitoring, ollama)
#   --file    <arquivo>  Arquivo docker-compose a usar
#
# SOLUÇÃO PARA O ERRO "fatal: not a git repository":
#   Se você copiou/extraiu o código sem o histórico git, use:
#     bash deploy/scripts/deploy.sh --no-git
#   Se quiser clonar do GitHub antes do deploy:
#     bash deploy/scripts/deploy.sh --repo https://github.com/kkborges/Personal_ai.git
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
REPO_URL=""
NO_GIT=false
NO_BUILD=false
ROLLBACK=false
COMPOSE_FILE="docker-compose.prod.yml"
PROFILES=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --branch)   BRANCH="$2";       shift 2 ;;
        --repo)     REPO_URL="$2";     shift 2 ;;
        --no-git)   NO_GIT=true;       shift ;;
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
if [[ ! -f "${APP_DIR}/.env" ]]; then
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ERRO: arquivo .env não encontrado!                  ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Diretório verificado: ${APP_DIR}${NC}"
    echo ""
    echo -e "${CYAN}Para resolver, execute um dos comandos abaixo:${NC}"
    echo -e "  cp .env.example .env && nano .env"
    echo -e "  # ou, se está em outro diretório:"
    echo -e "  bash quickstart.sh --no-git"
    echo ""
    exit 1
fi
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
BACKUP_DIR="/opt/personal-ai/backups"
mkdir -p "${BACKUP_DIR}"
BACKUP_FILE="${BACKUP_DIR}/backup_${BACKUP_DATE}.sql"

if docker ps 2>/dev/null | grep -q "ai-postgres"; then
    docker exec ai-postgres pg_dump \
        -U "${POSTGRES_USER:-ai_user}" \
        "${POSTGRES_DB:-personal_ai}" \
        --no-password \
        > "${BACKUP_FILE}" 2>/dev/null \
        && log "Backup PostgreSQL: ${BACKUP_FILE}" \
        || warn "Backup PostgreSQL falhou (ignorado)"
fi

find "${BACKUP_DIR}" -name "*.sql" -mtime +7 -delete 2>/dev/null || true

# ── Atualização do código ─────────────────────────────────────────────────────
COMMIT="local"

# Detecta se é um repositório git
IS_GIT_REPO=false
if git -C "${APP_DIR}" rev-parse --git-dir > /dev/null 2>&1; then
    IS_GIT_REPO=true
fi

if [[ "$NO_GIT" == "true" ]]; then
    # Modo sem git: usa os arquivos já presentes no diretório
    info "Modo --no-git: usando arquivos locais sem atualização via git."
    COMMIT="$(date '+%Y%m%d%H%M%S')"

elif [[ "$IS_GIT_REPO" == "true" ]]; then
    # Repositório git já existe — apenas faz pull
    step "Atualizando código via git (branch: ${BRANCH})..."
    git fetch --all
    git checkout "${BRANCH}"
    git pull origin "${BRANCH}"
    COMMIT="$(git rev-parse --short HEAD)"
    log "Código atualizado: ${COMMIT}"

elif [[ -n "$REPO_URL" ]]; then
    # Não é git, mas foi fornecida URL — clona o repositório
    step "Clonando repositório ${REPO_URL} (branch: ${BRANCH})..."
    TEMP_DIR="$(mktemp -d)"
    git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${TEMP_DIR}"
    # Copia arquivos clonados para APP_DIR preservando .env
    cp "${APP_DIR}/.env" "${TEMP_DIR}/.env"
    rsync -a --exclude='.git' "${TEMP_DIR}/" "${APP_DIR}/"
    rm -rf "${TEMP_DIR}"
    COMMIT="$(git -C "${APP_DIR}" rev-parse --short HEAD 2>/dev/null || echo 'cloned')"
    log "Repositório clonado: ${COMMIT}"

else
    # Nem git local nem URL fornecida — avisa detalhadamente e continua
    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  AVISO: Diretório sem repositório git                        ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    warn "O diretório '${APP_DIR}' não é um repositório git."
    warn "Isso geralmente ocorre quando o código foi copiado/extraído de um .tar.gz"
    warn "sem incluir o diretório .git."
    echo ""
    info "Soluções disponíveis:"
    echo -e "  ${CYAN}1. Deploy com arquivos atuais (sem atualizar código):${NC}"
    echo -e "     bash deploy/scripts/deploy.sh ${BOLD}--no-git${NC}"
    echo ""
    echo -e "  ${CYAN}2. Clonar do GitHub antes do deploy:${NC}"
    echo -e "     bash deploy/scripts/deploy.sh ${BOLD}--repo https://github.com/kkborges/Personal_ai.git${NC}"
    echo ""
    echo -e "  ${CYAN}3. Instalação completa do zero:${NC}"
    echo -e "     bash quickstart.sh --no-git   # já na pasta do projeto"
    echo -e "     bash quickstart.sh --repo https://github.com/kkborges/Personal_ai.git"
    echo ""
    warn "Continuando deploy com os arquivos presentes (equivalente a --no-git)..."
    COMMIT="$(date '+%Y%m%d%H%M%S')"
fi

# ── Build das imagens ─────────────────────────────────────────────────────────
if [[ "$NO_BUILD" == "false" ]]; then
    step "Buildando imagens Docker..."
    docker tag personal-ai-app:latest personal-ai-app:previous 2>/dev/null || true

    $DOCKER_COMPOSE build \
        --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --build-arg GIT_COMMIT="${COMMIT}"
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
