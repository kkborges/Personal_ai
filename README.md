# 🤖 Personal AI Mobile — Sistema de IA Pessoal Completo

> **v2.0.0** | FastAPI + PostgreSQL + Redis + Celery + React Native/Expo

Sistema de IA pessoal com voz, Bluetooth, autonomia, auto-melhoria e suporte offline completo.

---

## 🗂️ Documentação

| Documento                 | Conteúdo                                  |
|---------------------------|-------------------------------------------|
| [DEPLOY_BACKEND.md](./DEPLOY_BACKEND.md) | Deploy em Linux com PostgreSQL, Docker, Nginx, SSL |
| [DEPLOY_MOBILE.md](./DEPLOY_MOBILE.md)  | Build e publicação do app React Native/Expo        |

---

## 🏗️ Arquitetura

```
                        ┌─────────────────────────────────────┐
                        │          CLIENTE MOBILE              │
                        │  React Native + Expo SDK 52          │
                        │  ┌────────┐  ┌────────┐  ┌──────┐   │
                        │  │  Chat  │  │  Voz   │  │  BT  │   │
                        │  │  WS    │  │  TTS   │  │ Apps │   │
                        │  └────────┘  └────────┘  └──────┘   │
                        │      SQLite offline + sync queue      │
                        └──────────────┬──────────────────────┘
                                       │ HTTPS/WSS
                        ┌──────────────▼──────────────────────┐
                        │            NGINX                      │
                        │   SSL/TLS + Rate Limiting + Proxy     │
                        └──────────────┬──────────────────────┘
                                       │
              ┌─────────────────────────▼───────────────────────┐
              │              FastAPI App (Gunicorn)               │
              │          Personal AI Mobile Backend               │
              │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
              │  │   Chat   │  │  Voice   │  │   Autonomy   │  │
              │  │  Service │  │  Service │  │   Service    │  │
              │  └──────────┘  └──────────┘  └──────────────┘  │
              │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
              │  │ Bluetooth│  │Telephony │  │Self-Monitor  │  │
              │  │  Service │  │  Service │  │  + Improve   │  │
              │  └──────────┘  └──────────┘  └──────────────┘  │
              │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
              │  │ Provider │  │ Calendar │  │   Platform   │  │
              │  │  Router  │  │  Service │  │ Integrations │  │
              │  └──────────┘  └──────────┘  └──────────────┘  │
              └────────────────────┬────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
   ┌──────▼──────┐        ┌────────▼───────┐       ┌───────▼──────┐
   │ PostgreSQL  │        │    Redis 7     │       │   Celery     │
   │    16       │        │ Cache+Broker   │       │  Workers     │
   │ Full-text   │        │ Pub/Sub WS     │       │  ai, voice   │
   │ search      │        │ Job queue      │       │  sync, etc.  │
   └─────────────┘        └───────────────┘       └──────────────┘
```

---

## ✅ Funcionalidades Implementadas

### Backend (FastAPI + Python)
- **Chat & IA**: Conversas com contexto, histórico, multi-provider (OpenAI, Claude, Gemini, Ollama)
- **Memória**: Short-term (sessão) + long-term (SQLite FTS5 / PostgreSQL pg_trgm), busca semântica TF-IDF
- **Voz**: TTS via edge-tts/OpenAI/Piper; STT via Whisper/Google/Sphinx; wake word "LAS"
- **Bluetooth**: Scan, pair, connect, roteamento de áudio para speakers/TV/carro/headphones
- **Telefonia**: Discagem por voz, atender, encerrar; SIP/VoIP + modem GSM; histórico de chamadas
- **Calendário**: CRUD completo, importação/exportação iCal, integração Outlook/Google Calendar
- **Rotinas**: Agendamento cron via APScheduler (dev) / Celery Beat (prod); briefing matinal, resumo noturno
- **Autonomia**: Rastreamento de metas, sugestões proativas, ações autônomas configuráveis
- **Auto-Melhoria**: Coleta métricas, detecta anomalias, gera código Python + testes via IA, aplica patches
- **Modo Offline**: Fila SQLite local, fallback para Ollama, sync automático ao reconectar
- **Integrações**: Alexa (webhook), Google Assistant, WhatsApp Business, Outlook/Graph API, Teams, Spotify
- **Streaming Apps**: Netflix, Disney+, Amazon Prime, Globoplay, Paramount+ (deep links + launchers)
- **Job Queue**: Prioridade, retries, timeouts, monitoramento em tempo real
- **WebSocket**: Atualizações em tempo real (métricas, chat, sync, comandos de voz)

### App Mobile (React Native + Expo)
- **Chat em tempo real**: Via HTTP API + WebSocket (fallback offline)
- **Interface de voz**: Gravação + transcrição + TTS (nativo + servidor)
- **Dashboard**: Status do sistema, métricas em tempo real
- **Memória**: Browse, busca, adição e exclusão de memórias
- **Calendário**: Semana scrollável, CRUD de eventos
- **Bluetooth**: Scan, conexão, dispositivos confiáveis
- **Apps**: Launcher de streaming e integrações com deep links
- **Monitor**: Gráficos de CPU/RAM, patches de auto-melhoria
- **Configurações**: URL servidor, tema, voz, wake word
- **PWA**: Funciona como PWA no browser (service worker, manifest)
- **Modo Offline**: SQLite local + fila de sincronização automática

---

## 🚀 Deploy Rápido

### Backend (5 minutos)
```bash
git clone https://github.com/SEU_USUARIO/personal-ai-mobile.git
cd personal-ai-mobile
sudo bash deploy/scripts/setup.sh --domain seu-dominio.com --email admin@email.com
cp .env.example .env && nano .env
bash deploy/scripts/deploy.sh
```

### App Mobile (desenvolvimento)
```bash
cd mobile/
npm install
echo "EXPO_PUBLIC_API_URL=https://seu-dominio.com" > .env.local
npx expo start
```

---

## 📁 Estrutura do Projeto

```
personal-ai-mobile/
├── api/                    # Rotas FastAPI
│   └── routes.py           # Todos os endpoints REST
├── database/               
│   ├── db.py               # Gerenciador unificado SQLite/PostgreSQL
│   ├── db_postgres.py      # asyncpg + migrações + FTS
│   └── init_postgres.sql   # Script init Docker
├── services/               # Serviços de negócio
│   ├── chat_service.py     # Chat + contexto
│   ├── memory_service.py   # Memória + TF-IDF
│   ├── voice_service.py    # TTS/STT/Wake word
│   ├── bluetooth_service.py # BT scan/connect
│   ├── telephony_service.py # VoIP/GSM
│   ├── calendar_service.py  # Calendário + iCal
│   ├── routine_service.py   # Agendamento cron
│   ├── job_queue_service.py # Fila de jobs
│   ├── sync_service.py      # Offline sync
│   ├── platform_integrations.py # Alexa/WhatsApp/Spotify...
│   ├── provider_router.py   # Router multi-provider IA
│   └── self_monitoring.py   # Monitor + auto-melhoria
├── workers/                
│   └── celery_app.py        # Celery tasks para produção
├── models/                 
│   └── schemas.py           # Pydantic schemas
├── web/                    # Web UI single-page
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── mobile/                 # App React Native/Expo
│   ├── app/                # Expo Router
│   ├── src/
│   │   ├── screens/        # 9 telas completas
│   │   ├── services/api.ts # Client API + offline
│   │   ├── store/          # Zustand state
│   │   └── hooks/          # useVoice
│   ├── package.json
│   ├── app.json
│   └── eas.json
├── deploy/                 # Infraestrutura
│   ├── nginx/nginx.conf     # Reverse proxy + SSL
│   └── scripts/
│       ├── setup.sh         # Provisionamento servidor
│       └── deploy.sh        # Deploy/atualização
├── .github/workflows/
│   └── ci-cd.yml           # CI/CD GitHub Actions
├── docker-compose.prod.yml  # Produção completa
├── Dockerfile               # Multi-stage build
├── requirements.prod.txt    # Deps produção
├── .env.example             # Template de configuração
├── DEPLOY_BACKEND.md        # Guia deploy backend
└── DEPLOY_MOBILE.md         # Guia deploy mobile
```

---

## 🔗 URLs da API

| Endpoint              | Método | Descrição                    |
|-----------------------|--------|------------------------------|
| `/health`             | GET    | Status do serviço            |
| `/api/status`         | GET    | Métricas e versão            |
| `/api/chat`           | POST   | Enviar mensagem              |
| `/api/conversations`  | GET    | Listar conversas             |
| `/api/memory`         | GET/POST | Memórias                   |
| `/api/calendar/events`| CRUD   | Eventos de calendário        |
| `/api/routines`       | GET/PUT| Rotinas agendadas            |
| `/api/voice/tts`      | POST   | Text-to-Speech               |
| `/api/voice/stt`      | POST   | Speech-to-Text               |
| `/api/bluetooth/scan` | POST   | Scan Bluetooth               |
| `/api/bluetooth/connect/{mac}`| POST | Conectar dispositivo  |
| `/api/telephony/dial` | POST   | Fazer chamada                |
| `/api/apps/list`      | GET    | Lista de apps integrados     |
| `/api/monitoring/metrics`| GET | Métricas do sistema          |
| `/api/improvements/list`| GET  | Patches propostos            |
| `/api/jobs/stats`     | GET    | Estatísticas da fila         |
| `/api/sync/status`    | GET    | Status de sincronização      |
| `/ws`                 | WS     | WebSocket em tempo real      |
| `/docs`               | GET    | Swagger UI (OpenAPI)         |

---

## 🔧 Stack Técnica

| Componente   | Tecnologia                              |
|--------------|-----------------------------------------|
| Backend      | Python 3.12, FastAPI, Pydantic v2       |
| DB Produção  | PostgreSQL 16, asyncpg, FTS pg_trgm     |
| DB Dev       | SQLite, aiosqlite, FTS5                 |
| Cache/Queue  | Redis 7, Celery 5, Kombu                |
| Workers      | Celery Beat + Workers (5 filas)         |
| Proxy        | Nginx 1.27, SSL/TLS Let's Encrypt       |
| IA           | OpenAI, Anthropic, Gemini, Ollama       |
| Voz TTS      | edge-tts, OpenAI TTS, Piper             |
| Voz STT      | OpenAI Whisper, Google STT, Sphinx      |
| Mobile       | React Native 0.76, Expo SDK 52          |
| Build Mobile | EAS Build, Expo Router v4               |
| State Mobile | Zustand + AsyncStorage (persist)        |
| CI/CD        | GitHub Actions (test, build, deploy)    |

---

## 📄 Licença

MIT License — Uso pessoal e comercial permitidos.
