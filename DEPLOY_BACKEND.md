# 🚀 Personal AI Mobile — Guia de Deploy Backend (Linux + PostgreSQL)

> Versão 2.0.0 | Ubuntu 22.04/24.04 LTS | Docker Compose

---

## 📋 Pré-requisitos do Servidor

| Requisito         | Mínimo       | Recomendado  |
|-------------------|--------------|--------------|
| OS                | Ubuntu 22.04 | Ubuntu 24.04 |
| CPU               | 2 vCPUs      | 4+ vCPUs     |
| RAM               | 4 GB         | 8+ GB        |
| Disco             | 40 GB SSD    | 100+ GB SSD  |
| Banda             | 10 Mbps      | 100 Mbps     |
| Domínio           | Opcional     | Recomendado  |
| Porta pública     | 80, 443      | 80, 443      |

---

## ⚡ Deploy Rápido (5 minutos)

```bash
# 1. Clone o repositório no servidor
git clone https://github.com/SEU_USUARIO/personal-ai-mobile.git /opt/personal-ai/app
cd /opt/personal-ai/app

# 2. Provisionamento automático do servidor
sudo bash deploy/scripts/setup.sh \
  --domain seu-dominio.com \
  --email admin@seu-dominio.com

# 3. Configure o ambiente
cp .env.example .env
nano .env   # Preencha as variáveis (veja seção abaixo)

# 4. Deploy completo
bash deploy/scripts/deploy.sh
```

---

## 🔧 Configuração do Arquivo .env

```bash
# ── App ────────────────────────────────────────────────────────────────
APP_ENV=production
SECRET_KEY=<gere com: openssl rand -hex 32>
DOMAIN=seu-dominio.com
CORS_ORIGINS=https://seu-dominio.com

# ── PostgreSQL ─────────────────────────────────────────────────────────
POSTGRES_DB=personal_ai
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=<senha-forte-aqui>
DATA_DIR=/opt/personal-ai/data

# ── Redis ──────────────────────────────────────────────────────────────
REDIS_PASSWORD=<senha-redis>

# ── AI Providers (configure pelo menos um) ────────────────────────────
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
GENSPARK_API_KEY=...

# ── Ollama (LLM local para fallback offline) ────────────────────────────
# Habilite o perfil ollama para usar: --profile ollama
OLLAMA_HOST=http://ollama:11434
DEFAULT_PROVIDER=openai
FALLBACK_PROVIDER=ollama

# ── Voz ───────────────────────────────────────────────────────────────
TTS_BACKEND=edge-tts
TTS_VOICE=pt-BR-FranciscaNeural
STT_BACKEND=whisper
LANGUAGE=pt-BR

# ── Workers Celery ────────────────────────────────────────────────────
UVICORN_WORKERS=4
CELERY_CONCURRENCY=4

# ── Monitoramento ─────────────────────────────────────────────────────
FLOWER_USER=admin
FLOWER_PASSWORD=<senha-flower>
PGADMIN_EMAIL=admin@seu-dominio.com
PGADMIN_PASSWORD=<senha-pgadmin>

# ── Integrações (opcionais) ───────────────────────────────────────────
TELEGRAM_TOKEN=
WHATSAPP_API_KEY=
WHATSAPP_PHONE_ID=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
OUTLOOK_CLIENT_ID=
OUTLOOK_CLIENT_SECRET=
OUTLOOK_TENANT_ID=
TEAMS_WEBHOOK_URL=
ALEXA_SKILL_ID=
GOOGLE_ASSISTANT_PROJECT_ID=
```

---

## 🐳 Comandos Docker Compose

### Deploy básico (app + PostgreSQL + Redis + Nginx)
```bash
docker compose -f docker-compose.prod.yml up -d
```

### Com monitoramento (+ Flower + PgAdmin)
```bash
docker compose -f docker-compose.prod.yml --profile monitoring up -d
```

### Com Ollama (LLM local)
```bash
docker compose -f docker-compose.prod.yml --profile ollama up -d

# Após subir, baixe um modelo:
docker exec -it ai-ollama ollama pull llama3.2:3b
docker exec -it ai-ollama ollama pull nomic-embed-text
```

### Todos os serviços
```bash
docker compose -f docker-compose.prod.yml \
  --profile monitoring \
  --profile ollama \
  up -d
```

---

## 🗄️ PostgreSQL — Gestão do Banco

### Verificar conexão
```bash
docker exec -it ai-postgres psql -U ai_user -d personal_ai -c "\dt"
```

### Backup manual
```bash
docker exec ai-postgres pg_dump \
  -U ai_user personal_ai \
  > /opt/personal-ai/backups/manual_$(date +%Y%m%d).sql
```

### Restaurar backup
```bash
docker exec -i ai-postgres psql \
  -U ai_user personal_ai \
  < /opt/personal-ai/backups/manual_20240101.sql
```

### Backup automático (cron)
```bash
# Adicione ao crontab: crontab -e
0 2 * * * docker exec ai-postgres pg_dump -U ai_user personal_ai > /opt/personal-ai/backups/auto_$(date +\%Y\%m\%d).sql
0 3 * * * find /opt/personal-ai/backups -name "auto_*.sql" -mtime +30 -delete
```

---

## 📊 Redis — Cache e Filas

### Conectar ao Redis CLI
```bash
docker exec -it ai-redis redis-cli -a REDIS_PASSWORD
```

### Monitorar filas Celery
```bash
docker exec ai-redis redis-cli -a REDIS_PASSWORD llen celery
docker exec ai-redis redis-cli -a REDIS_PASSWORD keys "celery-task-meta-*" | wc -l
```

### Limpar cache
```bash
docker exec ai-redis redis-cli -a REDIS_PASSWORD FLUSHDB
```

---

## 🌐 Nginx + SSL

### Obter certificado SSL (Let's Encrypt)
```bash
# Primeiro, suba apenas Nginx sem SSL para o challenge HTTP:
docker exec ai-nginx nginx -t

# O Certbot renova automaticamente via docker-compose
# Para renovar manualmente:
docker exec ai-certbot certbot renew --webroot -w /var/www/certbot
docker exec ai-nginx nginx -s reload
```

### Gerar senha para Nginx Basic Auth
```bash
docker run --rm httpd:alpine htpasswd -nb admin SENHA >> ./deploy/nginx/.htpasswd
```

---

## ⚙️ Celery Workers

### Verificar status dos workers
```bash
docker compose -f docker-compose.prod.yml logs celery-worker --tail=50

# Via Flower (se habilitado):
# https://seu-dominio.com/flower  (admin/FLOWER_PASSWORD)
```

### Escalar workers horizontalmente
```bash
docker compose -f docker-compose.prod.yml \
  up -d --scale celery-worker=3
```

### Tasks disponíveis
| Task | Fila | Descrição |
|------|------|-----------|
| `task_ai_chat` | ai | Processa chat com IA |
| `task_tts_generate` | voice | Gera áudio TTS |
| `task_stt_process` | voice | Transcreve áudio |
| `task_sync_pending` | sync | Sincroniza dados offline |
| `task_run_routine` | routines | Executa rotinas agendadas |
| `task_collect_metrics` | monitoring | Coleta métricas do sistema |
| `task_self_improvement` | monitoring | Propõe auto-melhorias |

---

## 🔍 Monitoramento e Logs

### Logs da aplicação
```bash
# App principal
docker compose -f docker-compose.prod.yml logs app -f --tail=100

# Celery Worker
docker compose -f docker-compose.prod.yml logs celery-worker -f

# Nginx (acesso)
docker exec ai-nginx cat /var/log/nginx/access.log | tail -50

# Todos os serviços
docker compose -f docker-compose.prod.yml logs -f --tail=30
```

### Status dos serviços
```bash
docker compose -f docker-compose.prod.yml ps
```

### Health check
```bash
curl https://seu-dominio.com/health
curl https://seu-dominio.com/api/status
```

---

## 🔄 Atualizações

### Atualização simples (sem downtime)
```bash
cd /opt/personal-ai/app
bash deploy/scripts/deploy.sh --branch main
```

### Rollback em caso de problemas
```bash
bash deploy/scripts/deploy.sh --rollback
```

---

## 🔒 Segurança em Produção

### 1. Firewall UFW (já configurado pelo setup.sh)
```bash
ufw status numbered
```

### 2. Hardening do Docker
```bash
# Evita que containers acessem o host diretamente
echo '{"userns-remap": "default", "live-restore": true}' > /etc/docker/daemon.json
systemctl restart docker
```

### 3. Rotação de secrets
```bash
# Gere novos secrets periodicamente:
openssl rand -hex 32  # SECRET_KEY
openssl rand -hex 24  # POSTGRES_PASSWORD
```

### 4. Scan de vulnerabilidades
```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image personal-ai-app:latest
```

---

## 🌍 Deploy em Cloud (alternativas)

### Railway.app
```bash
# railway.toml já está configurado
npm i -g @railway/cli
railway login
railway up
```

### Render.com
- Crie um Web Service apontando para o Dockerfile
- Configure as variáveis de ambiente no dashboard
- Use o Render PostgreSQL managed database

### DigitalOcean App Platform
```bash
doctl apps create --spec .do/app.yaml
```

### AWS ECS + RDS
```bash
# Use o Dockerfile + RDS PostgreSQL + ElastiCache Redis
# Terraform em deploy/terraform/ (a ser criado)
```

---

## 📈 Performance

### Otimização PostgreSQL
```sql
-- Execute no PostgreSQL para otimizar:
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET work_mem = '4MB';
ALTER SYSTEM SET max_connections = 100;
SELECT pg_reload_conf();
```

### Otimização Redis
```bash
# Em /etc/sysctl.conf (já configurado pelo setup.sh):
vm.overcommit_memory = 1
net.core.somaxconn = 65535
```

---

## ❓ Troubleshooting

### App não inicia
```bash
docker compose -f docker-compose.prod.yml logs app --tail=50
# Verifique se o .env está correto
# Verifique se PostgreSQL e Redis estão saudáveis
docker compose -f docker-compose.prod.yml ps
```

### PostgreSQL: Connection refused
```bash
docker exec ai-postgres pg_isready -U ai_user
# Verifique DATABASE_URL no .env
```

### Celery: Tasks não processando
```bash
docker compose -f docker-compose.prod.yml restart celery-worker
docker exec ai-redis redis-cli -a REDIS_PASSWORD ping
```

### Nginx: 502 Bad Gateway
```bash
docker exec ai-nginx nginx -t
curl http://localhost:8765/health
docker compose -f docker-compose.prod.yml restart app
```

### SSL: Certificate expired
```bash
docker exec ai-certbot certbot renew --force-renewal
docker exec ai-nginx nginx -s reload
```

---

## 📌 URLs de Acesso

| Serviço    | URL                                      | Auth          |
|------------|------------------------------------------|---------------|
| Web UI     | `https://seu-dominio.com`               | —             |
| API Docs   | `https://seu-dominio.com/docs`          | Basic Auth    |
| Flower     | `https://seu-dominio.com/flower`        | FLOWER_USER   |
| PgAdmin    | `http://servidor:5050`                  | PGADMIN_EMAIL |
| Health     | `https://seu-dominio.com/health`        | —             |
| Status     | `https://seu-dominio.com/api/status`    | —             |
