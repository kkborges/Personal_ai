-- ═══════════════════════════════════════════════════════════════════════════
-- Personal AI Mobile — Schema PostgreSQL
-- Compatível com SQLite (via aiosqlite) e PostgreSQL (via asyncpg)
-- ═══════════════════════════════════════════════════════════════════════════

-- Extensões úteis (PostgreSQL apenas)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- Busca por similaridade (memória semântica)

-- ── Conversas (chat history) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform    VARCHAR(50) DEFAULT 'mobile',
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at DESC);

-- ── Mensagens ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL CHECK (role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    provider_used   VARCHAR(50),
    model_used      VARCHAR(100),
    tokens_used     INTEGER DEFAULT 0,
    cost_usd        NUMERIC(10,6) DEFAULT 0,
    audio_url       TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);

-- ── Memórias ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memories (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type            VARCHAR(20) DEFAULT 'fact' CHECK (type IN ('fact','preference','event','skill','context')),
    content         TEXT NOT NULL,
    importance      NUMERIC(3,2) DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
    tags            TEXT[] DEFAULT '{}',
    source          VARCHAR(100),
    conversation_id UUID,
    access_count    INTEGER DEFAULT 0,
    last_accessed   TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    embedding       FLOAT[],  -- Para busca semântica com pgvector (opcional)
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Índice de busca full-text em português
CREATE INDEX IF NOT EXISTS idx_memories_fts 
    ON memories USING GIN(to_tsvector('portuguese', content));
-- Busca por similaridade de trigrams
CREATE INDEX IF NOT EXISTS idx_memories_trgm 
    ON memories USING GIN(content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);

-- ── Eventos de calendário ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calendar_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    description     TEXT,
    location        TEXT,
    start_datetime  TIMESTAMPTZ NOT NULL,
    end_datetime    TIMESTAMPTZ,
    all_day         BOOLEAN DEFAULT FALSE,
    recurrence      VARCHAR(50),
    reminder_min    INTEGER DEFAULT 15,
    ical_uid        TEXT UNIQUE,
    status          VARCHAR(20) DEFAULT 'confirmed',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_datetime);
CREATE INDEX IF NOT EXISTS idx_calendar_status ON calendar_events(status);

-- ── Jobs / Fila de tarefas ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type            VARCHAR(100) NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending' 
                    CHECK (status IN ('pending','running','completed','failed','cancelled','dead_letter')),
    priority        INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    payload         JSONB DEFAULT '{}',
    result          JSONB,
    error           TEXT,
    retries         INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    celery_task_id  TEXT,  -- ID da tarefa Celery correspondente
    scheduled_at    TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_scheduled ON jobs(scheduled_at) WHERE status = 'pending';

-- ── Rotinas ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS routines (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    description     TEXT,
    cron_expression TEXT NOT NULL,
    actions         JSONB DEFAULT '[]',
    enabled         BOOLEAN DEFAULT TRUE,
    last_run        TIMESTAMPTZ,
    next_run        TIMESTAMPTZ,
    run_count       INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Histórico de execução de rotinas ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS routine_history (
    id              BIGSERIAL PRIMARY KEY,
    routine_id      UUID REFERENCES routines(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    success         BOOLEAN,
    output          TEXT,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_routine_history_routine ON routine_history(routine_id, started_at DESC);

-- ── Métricas de monitoramento ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monitoring_metrics (
    id              BIGSERIAL PRIMARY KEY,
    cpu_percent     NUMERIC(5,2),
    memory_percent  NUMERIC(5,2),
    disk_percent    NUMERIC(5,2),
    health_score    NUMERIC(5,2),
    active_jobs     INTEGER DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Particionamento por data (PostgreSQL 10+) para performance em alta escala
-- (descomente se tiver muitas métricas)
-- CREATE TABLE monitoring_metrics_y2025m01 PARTITION OF monitoring_metrics
--     FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE INDEX IF NOT EXISTS idx_metrics_created ON monitoring_metrics(created_at DESC);

-- ── Fila de sincronização ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_queue (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_type       VARCHAR(50) NOT NULL,
    item_id         TEXT NOT NULL,
    action          VARCHAR(20) DEFAULT 'upsert',
    payload         JSONB DEFAULT '{}',
    status          VARCHAR(20) DEFAULT 'pending',
    error           TEXT,
    retry_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    synced_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_queue(status, created_at);

-- ── Configuração do sistema ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_config (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Configurações padrão
INSERT INTO system_config (key, value) VALUES
    ('language', 'pt-BR'),
    ('tts_backend', 'edge-tts'),
    ('tts_voice', 'pt-BR-FranciscaNeural'),
    ('wake_word', 'LAS'),
    ('always_listen', 'false'),
    ('autonomy_level', 'balanced'),
    ('default_provider', 'openai'),
    ('sync_enabled', 'true'),
    ('bluetooth_enabled', 'true'),
    ('telephony_enabled', 'true')
ON CONFLICT (key) DO NOTHING;

-- ── Função para atualizar updated_at automaticamente ─────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers de auto-update
CREATE OR REPLACE TRIGGER trg_conversations_updated
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER trg_memories_updated
    BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER trg_calendar_updated
    BEFORE UPDATE ON calendar_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Views úteis ────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_recent_conversations AS
    SELECT c.id, c.title, c.platform, c.created_at,
           COUNT(m.id) as message_count,
           MAX(m.created_at) as last_message_at,
           SUM(m.tokens_used) as total_tokens,
           SUM(m.cost_usd) as total_cost
    FROM conversations c
    LEFT JOIN messages m ON m.conversation_id = c.id
    GROUP BY c.id
    ORDER BY last_message_at DESC NULLS LAST;

CREATE OR REPLACE VIEW v_pending_jobs AS
    SELECT * FROM jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, created_at ASC;

CREATE OR REPLACE VIEW v_system_health AS
    SELECT 
        AVG(cpu_percent) FILTER (WHERE created_at > NOW() - INTERVAL '5 minutes') as avg_cpu_5m,
        AVG(memory_percent) FILTER (WHERE created_at > NOW() - INTERVAL '5 minutes') as avg_mem_5m,
        AVG(health_score) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as avg_health_1h,
        COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as metrics_1h
    FROM monitoring_metrics;

COMMENT ON TABLE memories IS 'Memórias de curto e longo prazo do assistente';
COMMENT ON TABLE calendar_events IS 'Eventos do calendário pessoal';
COMMENT ON TABLE jobs IS 'Fila de jobs assíncronos (integra com Celery)';
COMMENT ON TABLE sync_queue IS 'Fila de itens para sincronizar com servidor pai (modo offline)';
