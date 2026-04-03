# 🤖 Personal AI Mobile

Sistema de Inteligência Artificial Pessoal Mobile — versão avançada com suporte completo a voz, Bluetooth, telefonia, integrações com plataformas populares e auto-melhoria autônoma.

---

## 🌐 URLs Principais

| Recurso | URL |
|---|---|
| Interface Mobile | `http://localhost:8765/` |
| Documentação API | `http://localhost:8765/docs` |
| API Alternativa | `http://localhost:8765/redoc` |
| Health Check | `http://localhost:8765/health` |
| WebSocket | `ws://localhost:8765/ws` |

---

## ✅ Funcionalidades Implementadas

### 🎙️ Voz Total (100%)
- **Escuta contínua** com wake word configurável (padrão: **"LAS"**)
- **Ativação por comando** — diga "LAS" + seu pedido
- **TTS multimodo**: edge-tts (grátis), OpenAI TTS, Piper (local)
- **STT**: Whisper API (online), Google STT (online), Sphinx (offline)
- **Respostas em áudio** automáticas para comandos de voz
- Toggle de escuta contínua via UI ou API

### 📡 Bluetooth Completo
- **Escaneamento** de dispositivos próximos (BLE real via `bleak`)
- **Classificação automática**: caixa de som, fone, TV, carro, multimídia, celular
- **Pareamento e conexão** via `bluetoothctl`
- **Roteamento de áudio** para dispositivos BT (PulseAudio)
- **Roteamento de chamadas** para fone/caixa BT
- Banco de dados local de dispositivos conhecidos/confiáveis

### 📞 Telefonia
- **Discagem por voz**: "LAS, ligue para João"
- **Atendimento** e **desligamento** automático
- Suporte a **SIP/VoIP** (pjsua)
- Suporte a **modem GSM** (comandos AT via serial)
- Histórico de chamadas no SQLite
- Resolução de contatos por nome

### 🧠 IA Multi-Provedor
- **OpenAI** (GPT-4o, GPT-4o-mini)
- **Anthropic** (Claude 3 Haiku, Sonnet, Opus)
- **Google Gemini** (Gemini 1.5 Flash, Pro)
- **GenSpark** (via API compatível OpenAI)
- **Ollama** (local, offline — llama3.2, mistral, etc.)
- **Fallback automático**: se um provedor falha, tenta o próximo
- **Rate limiting** por provedor
- **Tracking de custos** em USD por requisição

### 🔗 Integrações de Plataforma

#### Alexa
- Skill webhook (`POST /api/platforms/alexa`)
- Intents: Chat, Calendário, Lembrete, Controle de Dispositivos

#### Google Assistant
- Actions webhook (`POST /api/platforms/google`)
- Suporte a Dialogflow fulfillment

#### WhatsApp Business
- Webhook de mensagens recebidas
- Envio de mensagens via API oficial

#### Microsoft Outlook + Teams
- Leitura de e-mails (Graph API)
- Envio de e-mails
- Calendário Outlook
- Mensagens Teams via Webhook

#### Spotify
- Autenticação OAuth2
- Controle: play, pause, próxima, anterior, volume, busca
- "Tocar músico agora"

#### Apps de Streaming
- Netflix, Disney+, Amazon Prime Video
- Paramount+, GloboPlay, YouTube
- Lançamento por nome: `POST /api/apps/launch`
- Busca de conteúdo dentro do app

#### Produtividade
- Outlook, Teams, WhatsApp — todos com deep links e APIs

### 📅 Calendário
- CRUD completo de eventos
- **Linguagem natural**: "Reunião com João amanhã às 14h"
- Exportação/importação iCal
- Agenda diária em texto para TTS
- Detecção de conflitos
- Eventos recorrentes (cron-like)
- Integração com Microsoft Outlook

### 🧩 Memória
- Curto prazo: contexto de conversa (janela deslizante)
- Longo prazo: SQLite + FTS5 (full-text search)
- Busca semântica: TF-IDF offline
- Tipos: fato, preferência, evento, pessoa, nota, contexto
- **Auto-extração**: extrai informações importantes da conversa automaticamente

### 📋 Rotinas Automáticas
- APScheduler com cron expressions
- Templates: Briefing Matinal (7h), Resumo Noturno (21h), Revisão Semanal (seg 9h)
- Rotina de Monitoramento (a cada minuto)
- Rotina de Sync (a cada 30 min)
- Histórico de execuções

### 🔄 Modo Offline + Sync
- Detecta conectividade via DNS
- Fila local de operações (sync_queue no SQLite)
- Reenvio automático ao voltar online
- Pull de dados do servidor pai
- Compatível com a versão web (Personal AI Web API)

### 🧠 Auto-Monitoramento e Auto-Melhoria
- Coleta métricas: CPU, RAM, Disco, Jobs, Threads
- Cálculo de **Health Score** (0-100)
- Detecção de anomalias (CPU alto, memory leak, job failures)
- **Geração automática de código** de melhoria via IA
- Execução de testes (`pytest`) nas melhorias geradas
- Aplicação de patches (manual ou automática via `AUTO_DEPLOY_PATCHES=true`)
- Relatório detalhado de 24h com recomendações

### 📦 Job Queue
- Fila assíncrona com prioridades
- Tipos: TTS, Sync, Reminder, Monitoring, Improvement
- Retry com backoff exponencial
- Dead letter queue
- Dependências entre jobs

### 📊 Web UI Mobile-First
- SPA responsiva para mobile
- PWA (Progressive Web App) — instalável no celular
- WebSocket para atualizações em tempo real
- Dark/Light mode
- Páginas: Chat, Calendário, Bluetooth, Apps, Sistema
- Service Worker para offline básico

---

## 🚀 Como Instalar e Executar

### Pré-requisitos
```bash
Python 3.10+
pip
```

### Instalação
```bash
git clone <repositório>
cd personal-ai-mobile

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Edite .env e adicione suas chaves de API

# Iniciar
bash start.sh
```

### Via Script
```bash
chmod +x start.sh
./start.sh
```

### Via PM2 (produção)
```bash
pm2 start ecosystem.config.cjs
pm2 logs personal-ai-mobile
```

---

## ⚙️ Configuração (.env)

```env
# IA Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GENSPARK_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434  # IA local offline

# Voz
TTS_BACKEND=edge-tts    # edge-tts | openai | piper
TTS_VOICE=pt-BR-FranciscaNeural
ALWAYS_LISTEN=false
WAKE_WORD=LAS

# Autonomia
AUTONOMY_LEVEL=balanced  # passive | balanced | proactive

# Sync com Personal AI Web
PARENT_API_URL=http://localhost:8000
SYNC_ENABLED=true

# Plataformas
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
OUTLOOK_CLIENT_ID=...
OUTLOOK_TENANT_ID=...
WHATSAPP_API_KEY=...
TEAMS_WEBHOOK_URL=https://...

# Telefonia
SIP_SERVER=sip.exemplo.com
SIP_USER=usuario
SIP_PASSWORD=senha
GSM_MODEM_PORT=/dev/ttyUSB0

# Auto-melhoria
AUTO_DEPLOY_PATCHES=false  # true = aplica patches automaticamente
```

---

## 📡 API Reference

### Chat
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/chat` | Enviar mensagem e receber resposta |
| GET | `/api/chat/stream` | Streaming de resposta (SSE) |
| GET | `/api/chat/conversations` | Listar conversas |

### Voz
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/voice/tts` | Texto para Fala |
| POST | `/api/voice/stt` | Fala para Texto |
| POST | `/api/voice/listen/start` | Ativar escuta contínua |
| POST | `/api/voice/listen/stop` | Desativar escuta |
| GET | `/api/voice/voices` | Listar vozes disponíveis |

### Bluetooth
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/bluetooth/scan` | Escanear dispositivos |
| POST | `/api/bluetooth/connect/{mac}` | Conectar dispositivo |
| POST | `/api/bluetooth/pair/{mac}` | Parear dispositivo |
| POST | `/api/bluetooth/audio/{mac}` | Rotear áudio |

### Telefonia
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/phone/call` | Fazer ligação |
| POST | `/api/phone/answer` | Atender chamada |
| POST | `/api/phone/hangup` | Desligar chamada |

### Calendário
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/calendar/events` | Criar evento |
| GET | `/api/calendar/agenda` | Agenda do dia |
| POST | `/api/calendar/natural` | Criar via texto natural |
| GET | `/api/calendar/export.ical` | Exportar iCal |

### Auto-Melhoria
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/monitoring/metrics` | Métricas atuais + health |
| GET | `/api/monitoring/report` | Relatório 24h |
| POST | `/api/monitoring/improve` | Gerar melhoria com IA |
| POST | `/api/monitoring/patches/{id}/test` | Testar patch |
| POST | `/api/monitoring/patches/{id}/apply` | Aplicar patch |

### Plataformas
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/platforms/alexa` | Webhook Alexa Skill |
| POST | `/api/platforms/google` | Webhook Google Actions |
| POST | `/api/platforms/spotify/control` | Controlar Spotify |
| GET | `/api/platforms/outlook/emails` | Ler e-mails |
| POST | `/api/apps/launch` | Lançar aplicativo |

---

## 🏗️ Arquitetura

```
personal-ai-mobile/
├── main.py                     # FastAPI + WebSocket + Lifespan
├── config.py                   # Configurações centrais
├── requirements.txt
├── start.sh                    # Script de inicialização
├── ecosystem.config.cjs        # PM2 config
│
├── database/
│   └── db.py                   # SQLite + aiosqlite + schema
│
├── models/
│   └── schemas.py              # Pydantic v2 models
│
├── services/
│   ├── provider_router.py      # Multi-provedor IA com fallback
│   ├── chat_service.py         # Chat + contexto + memória
│   ├── memory_service.py       # Memória TF-IDF + FTS5
│   ├── calendar_service.py     # Calendário + iCal + NL
│   ├── voice_service.py        # TTS/STT + wake word
│   ├── bluetooth_service.py    # BLE scan/connect/pair
│   ├── telephony_service.py    # SIP/GSM + histórico
│   ├── platform_integrations.py # Alexa/Google/Spotify/WhatsApp/Outlook
│   ├── sync_service.py         # Offline queue + sync
│   ├── job_queue_service.py    # Fila async + retry
│   ├── routine_service.py      # APScheduler + templates
│   └── self_monitoring.py      # Métricas + auto-melhoria
│
├── api/
│   └── routes.py               # Todas as rotas FastAPI
│
├── web/                        # PWA Mobile UI
│   ├── index.html              # SPA principal
│   ├── css/style.css           # CSS Mobile-First
│   └── js/app.js               # JavaScript completo
│
├── data/                       # SQLite + áudios gerados
├── logs/                       # Logs da aplicação
└── self_improvement/           # Patches e código gerado
    ├── patches/                # Patches aplicados
    ├── generated/              # Código gerado pela IA
    └── tests/                  # Testes gerados
```

---

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| Framework | FastAPI + Uvicorn |
| Banco de Dados | SQLite + aiosqlite + FTS5 |
| Tempo Real | WebSocket nativo |
| Scheduling | APScheduler |
| TTS | edge-tts / OpenAI TTS / Piper |
| STT | Whisper API / Google STT |
| Bluetooth | bleak (BLE) |
| NLP/Busca | TF-IDF via scikit-learn |
| HTTP Async | httpx |
| Validação | Pydantic v2 |
| Monitoramento | psutil |
| Frontend | Vanilla HTML/CSS/JS (sem build) |
| Deploy | PM2 + Python |

---

## 📈 Roadmap

- [ ] App nativo Android (Kotlin/Compose)
- [ ] App nativo iOS (Swift)
- [ ] Integração com Google Home / Smart Home
- [ ] Reconhecimento de voz totalmente offline (Vosk/Coqui)
- [ ] Modelo de linguagem local (LlamaFile)
- [ ] Dashboard de análise de produtividade
- [ ] Integração com wearables (smartwatch)
- [ ] Modo automóvel com comandos de direção

---

## 📄 Licença

MIT License — Use e modifique livremente.

---

**Desenvolvido com ❤️ usando FastAPI, Python e IA**  
*Personal AI Mobile v2.0.0*
