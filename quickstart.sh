#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# quickstart.sh — Instalação e deploy COMPLETO do Personal AI Mobile
# ─────────────────────────────────────────────────────────────────────────────
# Este script é o PONTO DE ENTRADA para um servidor Linux limpo.
# Ele detecta a situação atual e guia o deploy de ponta a ponta.
#
# Uso (no servidor, como root ou com sudo):
#   # Opção A — servidor com acesso ao GitHub:
#   bash quickstart.sh --repo https://github.com/kkborges/Personal_ai.git \
#                      --domain meuai.com.br --email admin@meuai.com.br
#
#   # Opção B — código já copiado/extraído para este diretório:
#   bash quickstart.sh --no-git --domain meuai.com.br --email admin@meuai.com.br
#
#   # Opção C — desenvolvimento local (sem domínio/SSL):
#   bash quickstart.sh --no-git --no-ssl
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Cores ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()   { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $*${NC}"; }
warn()  { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠️  $*${NC}"; }
err()   { echo -e "${RED}[$(date '+%H:%M:%S')] ❌ $*${NC}" >&2; exit 1; }
info()  { echo -e "${CYAN}[$(date '+%H:%M:%S')] ℹ️  $*${NC}"; }
step()  { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}\n"; }
banner(){ echo -e "\n${BOLD}${BLUE}$*${NC}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║        Personal AI Mobile v2.0                   ║${NC}"
echo -e "${BOLD}${CYAN}║        Instalação Rápida — quickstart.sh         ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Argumentos ────────────────────────────────────────────────────────────────
DOMAIN=""
EMAIL=""
REPO_URL="https://github.com/kkborges/Personal_ai.git"
BRANCH="main"
APP_DIR="/opt/personal-ai/app"
DATA_DIR="/opt/personal-ai/data"
NO_GIT=false
NO_SSL=false
SKIP_SETUP=false   # Pula instalação de dependências (Docker, etc.)

while [[ $# -gt 0 ]]; do
    case $1 in
        --domain)      DOMAIN="$2";     shift 2 ;;
        --email)       EMAIL="$2";      shift 2 ;;
        --repo)        REPO_URL="$2";   shift 2 ;;
        --branch)      BRANCH="$2";     shift 2 ;;
        --app-dir)     APP_DIR="$2";    shift 2 ;;
        --no-git)      NO_GIT=true;     shift ;;
        --no-ssl)      NO_SSL=true;     shift ;;
        --skip-setup)  SKIP_SETUP=true; shift ;;
        --help|-h)
            echo "Uso: bash quickstart.sh [opções]"
            echo ""
            echo "  --domain   <domínio>  Domínio para SSL (ex: meuai.com.br)"
            echo "  --email    <email>    E-mail para Let's Encrypt"
            echo "  --repo     <url>      URL do repositório git"
            echo "                        (padrão: github.com/kkborges/Personal_ai)"
            echo "  --branch   <branch>   Branch git (padrão: main)"
            echo "  --app-dir  <path>     Diretório do app (padrão: /opt/personal-ai/app)"
            echo "  --no-git             Não usa git — usa os arquivos do diretório atual"
            echo "  --no-ssl             Pula configuração de SSL"
            echo "  --skip-setup         Pula instalação de Docker e dependências"
            echo ""
            exit 0 ;;
        *) warn "Argumento desconhecido: $1"; shift ;;
    esac
done

# ── Validações iniciais ────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && err "Execute como root: sudo bash quickstart.sh [opções]"

if [[ -z "$DOMAIN" ]]; then
    warn "Nenhum --domain definido. SSL será desativado."
    NO_SSL=true
fi

if [[ "$NO_SSL" == "false" && -z "$EMAIL" ]]; then
    warn "SSL ativo mas sem --email. SSL será desativado."
    NO_SSL=true
fi

# ── ETAPA 1: Instalar dependências do sistema ─────────────────────────────────
if [[ "$SKIP_SETUP" == "false" ]]; then
    step "ETAPA 1: Instalando dependências do sistema"

    # Verifica se setup.sh existe neste diretório ou em subpastas comuns
    SETUP_SCRIPT=""
    for p in \
        "$(dirname "${BASH_SOURCE[0]}")/deploy/scripts/setup.sh" \
        "/opt/personal-ai/app/deploy/scripts/setup.sh" \
        "./deploy/scripts/setup.sh"; do
        if [[ -f "$p" ]]; then
            SETUP_SCRIPT="$p"
            break
        fi
    done

    if [[ -n "$SETUP_SCRIPT" ]]; then
        info "Executando setup.sh: ${SETUP_SCRIPT}"
        SSL_ARGS=""
        [[ "$NO_SSL" == "false" && -n "$DOMAIN" && -n "$EMAIL" ]] && \
            SSL_ARGS="--domain ${DOMAIN} --email ${EMAIL}" || SSL_ARGS="--no-ssl"
        bash "${SETUP_SCRIPT}" --app "${APP_DIR}" --data "${DATA_DIR}" ${SSL_ARGS}
    else
        # Instalação mínima inline
        warn "setup.sh não encontrado — instalando dependências mínimas..."
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq curl wget git ca-certificates gnupg jq

        if ! command -v docker &>/dev/null; then
            info "Instalando Docker..."
            curl -fsSL https://get.docker.com | bash
            systemctl enable --now docker
            log "Docker instalado"
        else
            log "Docker já instalado: $(docker --version)"
        fi
    fi
else
    info "Pulando instalação de dependências (--skip-setup)"
fi

# ── ETAPA 2: Obter / atualizar código ─────────────────────────────────────────
step "ETAPA 2: Obtendo código-fonte"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$NO_GIT" == "true" ]]; then
    # Usa o diretório onde este script está como APP_DIR
    info "Modo --no-git: usando código em ${SCRIPT_DIR}"
    APP_DIR="${SCRIPT_DIR}"

elif git -C "${SCRIPT_DIR}" rev-parse --git-dir > /dev/null 2>&1; then
    # Já é um repositório git — faz pull
    info "Repositório git detectado em ${SCRIPT_DIR}"
    APP_DIR="${SCRIPT_DIR}"
    git -C "${APP_DIR}" fetch --all
    git -C "${APP_DIR}" checkout "${BRANCH}"
    git -C "${APP_DIR}" pull origin "${BRANCH}"
    COMMIT="$(git -C "${APP_DIR}" rev-parse --short HEAD)"
    log "Código atualizado: commit ${COMMIT}"

elif [[ -n "$REPO_URL" ]]; then
    # Clona o repositório no APP_DIR
    if [[ -d "${APP_DIR}/.git" ]]; then
        info "Atualizando repositório existente em ${APP_DIR}..."
        git -C "${APP_DIR}" fetch --all
        git -C "${APP_DIR}" checkout "${BRANCH}"
        git -C "${APP_DIR}" pull origin "${BRANCH}"
    else
        info "Clonando ${REPO_URL} em ${APP_DIR}..."
        mkdir -p "$(dirname "${APP_DIR}")"
        # Preserva .env se já existir
        if [[ -f "${APP_DIR}/.env" ]]; then
            cp "${APP_DIR}/.env" /tmp/personal-ai.env.backup
        fi
        git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
        # Restaura .env
        if [[ -f /tmp/personal-ai.env.backup ]]; then
            cp /tmp/personal-ai.env.backup "${APP_DIR}/.env"
            rm /tmp/personal-ai.env.backup
        fi
    fi
    COMMIT="$(git -C "${APP_DIR}" rev-parse --short HEAD)"
    log "Repositório pronto: commit ${COMMIT}"

else
    # Fallback: usa o diretório do script
    warn "Nem --no-git nem --repo foram usados. Usando diretório atual como APP_DIR."
    APP_DIR="${SCRIPT_DIR}"
fi

cd "${APP_DIR}"
log "Diretório do app: ${APP_DIR}"

# ── ETAPA 3: Configurar .env ──────────────────────────────────────────────────
step "ETAPA 3: Configurando variáveis de ambiente"

if [[ ! -f "${APP_DIR}/.env" ]]; then
    if [[ -f "${APP_DIR}/.env.example" ]]; then
        info "Criando .env a partir de .env.example..."
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"

        # Gera senhas/segredos automáticos
        SECRET_KEY=$(openssl rand -hex 32)
        POSTGRES_PASS=$(openssl rand -hex 24)
        REDIS_PASS=$(openssl rand -hex 16)
        FLOWER_PASS=$(openssl rand -hex 12)
        PGADMIN_PASS=$(openssl rand -hex 12)

        sed -i "s|SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" "${APP_DIR}/.env"
        sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASS}|" "${APP_DIR}/.env"
        sed -i "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASS}|" "${APP_DIR}/.env"
        sed -i "s|FLOWER_PASSWORD=.*|FLOWER_PASSWORD=${FLOWER_PASS}|" "${APP_DIR}/.env"
        sed -i "s|PGADMIN_PASSWORD=.*|PGADMIN_PASSWORD=${PGADMIN_PASS}|" "${APP_DIR}/.env"
        [[ -n "$DOMAIN" ]] && sed -i "s|DOMAIN=.*|DOMAIN=${DOMAIN}|" "${APP_DIR}/.env"
        [[ -n "$EMAIL" ]] && sed -i "s|PGADMIN_EMAIL=.*|PGADMIN_EMAIL=${EMAIL}|" "${APP_DIR}/.env"

        log ".env gerado com senhas automáticas"
        warn "⚠️  IMPORTANTE: Edite ${APP_DIR}/.env e insira suas API keys antes de continuar!"
        echo ""
        echo -e "${YELLOW}  Campos obrigatórios em ${APP_DIR}/.env:${NC}"
        echo -e "  ${CYAN}OPENAI_API_KEY${NC}    = sk-...      (necessário para IA)"
        echo -e "  ${CYAN}ANTHROPIC_API_KEY${NC} = sk-ant-...  (opcional)"
        echo -e "  ${CYAN}GOOGLE_API_KEY${NC}    = ...         (opcional)"
        echo ""
        echo -e "${YELLOW}Pressione ENTER para abrir o editor, ou CTRL+C para editar manualmente depois.${NC}"
        read -r -t 30 || true
        ${EDITOR:-nano} "${APP_DIR}/.env" || true
    else
        err ".env e .env.example não encontrados em ${APP_DIR}. Verifique o código."
    fi
else
    log ".env já existe — mantendo configuração atual"
fi

# ── ETAPA 4: Executar deploy ────────────────────────────────────────────────────
step "ETAPA 4: Iniciando deploy Docker"

DEPLOY_SCRIPT="${APP_DIR}/deploy/scripts/deploy.sh"

if [[ -f "${DEPLOY_SCRIPT}" ]]; then
    info "Executando ${DEPLOY_SCRIPT} --no-git ..."
    bash "${DEPLOY_SCRIPT}" --no-git
else
    # Fallback: deploy direto com docker compose
    warn "deploy.sh não encontrado — executando docker compose diretamente..."
    COMPOSE_FILE="${APP_DIR}/docker-compose.prod.yml"
    [[ ! -f "$COMPOSE_FILE" ]] && COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
    [[ ! -f "$COMPOSE_FILE" ]] && err "Nenhum arquivo docker-compose encontrado em ${APP_DIR}"

    # Cria diretórios de dados
    mkdir -p \
        "${DATA_DIR}/postgres" "${DATA_DIR}/redis" \
        "${DATA_DIR}/app" "${DATA_DIR}/audio" \
        "/opt/personal-ai/logs"

    set -a; source "${APP_DIR}/.env"; set +a

    docker compose -f "${COMPOSE_FILE}" pull --ignore-pull-failures 2>/dev/null || true
    docker compose -f "${COMPOSE_FILE}" build
    docker compose -f "${COMPOSE_FILE}" up -d
    log "Serviços iniciados"
fi

# ── ETAPA 5: Verificação de saúde ─────────────────────────────────────────────
step "ETAPA 5: Verificando saúde dos serviços"

APP_PORT="${APP_PORT:-8765}"
sleep 10

if curl -sf "http://localhost:${APP_PORT}/health" > /dev/null 2>&1; then
    log "App respondendo na porta ${APP_PORT}"
else
    warn "App ainda não responde em /health — pode levar mais alguns segundos"
    info "Verifique com: docker compose -f ${APP_DIR}/docker-compose.prod.yml ps"
    info "Logs:          docker compose -f ${APP_DIR}/docker-compose.prod.yml logs app --tail=50"
fi

# ── Resumo final ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║   Personal AI Mobile — Instalação Concluída! 🎉  ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}📂 Código:   ${APP_DIR}${NC}"
echo -e "${CYAN}📝 Config:   ${APP_DIR}/.env${NC}"
echo -e "${CYAN}📋 Logs:     docker compose -f ${APP_DIR}/docker-compose.prod.yml logs -f app${NC}"
echo ""
echo -e "${YELLOW}🌐 URLs de acesso:${NC}"
if [[ -n "$DOMAIN" && "$NO_SSL" == "false" ]]; then
    echo -e "  Web:      https://${DOMAIN}"
    echo -e "  API Docs: https://${DOMAIN}/docs"
    echo -e "  Flower:   https://${DOMAIN}/flower"
    echo -e "  PgAdmin:  https://${DOMAIN}/pgadmin"
else
    echo -e "  Web:      http://$(curl -4 -sf ifconfig.me 2>/dev/null || echo 'SEU_IP'):${APP_PORT}"
    echo -e "  API Docs: http://$(curl -4 -sf ifconfig.me 2>/dev/null || echo 'SEU_IP'):${APP_PORT}/docs"
fi
echo ""
echo -e "${YELLOW}🔧 Comandos úteis:${NC}"
echo -e "  Status:    cd ${APP_DIR} && docker compose -f docker-compose.prod.yml ps"
echo -e "  Logs:      cd ${APP_DIR} && docker compose -f docker-compose.prod.yml logs -f app"
echo -e "  Reiniciar: cd ${APP_DIR} && bash deploy/scripts/deploy.sh --no-git"
echo -e "  Atualizar: cd ${APP_DIR} && bash deploy/scripts/deploy.sh"
echo ""
