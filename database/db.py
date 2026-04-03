"""
database/db.py — Gerenciador SQLite com aiosqlite, migrações e FTS5
"""
import logging
import aiosqlite
from config import settings

logger = logging.getLogger(__name__)
_db_conn: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = await aiosqlite.connect(settings.db_path)
        _db_conn.row_factory = aiosqlite.Row
        await _db_conn.execute("PRAGMA journal_mode=WAL")
        await _db_conn.execute("PRAGMA foreign_keys=ON")
        await _db_conn.execute("PRAGMA cache_size=10000")
    return _db_conn


async def close_db():
    global _db_conn
    if _db_conn:
        await _db_conn.close()
        _db_conn = None


# ─── Schema Migrations ───────────────────────────────────────────────────────
SCHEMA_SQL = """
-- ═══ CONVERSATIONS ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    platform    TEXT DEFAULT 'mobile',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    tokens          INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta            TEXT DEFAULT '{}'
);

-- ═══ MEMORY ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    content     TEXT NOT NULL,
    importance  REAL DEFAULT 0.5,
    source      TEXT,
    tags        TEXT DEFAULT '[]',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME,
    meta        TEXT DEFAULT '{}'
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content, tags, tokenize='porter');

-- ═══ CALENDAR ═════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS calendar_events (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT,
    start_datetime  DATETIME NOT NULL,
    end_datetime    DATETIME,
    location        TEXT,
    all_day         INTEGER DEFAULT 0,
    recurrence      TEXT,
    reminder_min    INTEGER DEFAULT 15,
    source          TEXT DEFAULT 'local',
    external_id     TEXT,
    status          TEXT DEFAULT 'confirmed',
    platform        TEXT DEFAULT 'local',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta            TEXT DEFAULT '{}'
);

-- ═══ ROUTINES ═════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS routines (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    cron_expr   TEXT NOT NULL,
    actions     TEXT DEFAULT '[]',
    enabled     INTEGER DEFAULT 1,
    last_run    DATETIME,
    next_run    DATETIME,
    run_count   INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS routine_history (
    id          TEXT PRIMARY KEY,
    routine_id  TEXT REFERENCES routines(id),
    status      TEXT,
    output      TEXT,
    error       TEXT,
    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══ JOBS ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    priority        INTEGER DEFAULT 5,
    payload         TEXT DEFAULT '{}',
    result          TEXT,
    error           TEXT,
    attempts        INTEGER DEFAULT 0,
    max_attempts    INTEGER DEFAULT 3,
    depends_on      TEXT,
    scheduled_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at      DATETIME,
    completed_at    DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══ ACTIONS ═════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS action_logs (
    id          TEXT PRIMARY KEY,
    action_name TEXT NOT NULL,
    params      TEXT DEFAULT '{}',
    result      TEXT,
    success     INTEGER DEFAULT 1,
    duration_ms INTEGER DEFAULT 0,
    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta        TEXT DEFAULT '{}'
);

-- ═══ SYNC QUEUE ══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS sync_queue (
    id          TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    operation   TEXT NOT NULL,
    payload     TEXT DEFAULT '{}',
    synced      INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    synced_at   DATETIME
);

-- ═══ BLUETOOTH DEVICES ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS bluetooth_devices (
    mac_address TEXT PRIMARY KEY,
    name        TEXT,
    device_type TEXT DEFAULT 'unknown',
    trusted     INTEGER DEFAULT 0,
    last_seen   DATETIME,
    last_conn   DATETIME,
    meta        TEXT DEFAULT '{}'
);

-- ═══ VOICE PROFILES ══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS voice_profiles (
    id          TEXT PRIMARY KEY DEFAULT 'default',
    voice_name  TEXT,
    language    TEXT DEFAULT 'pt-BR',
    speed       REAL DEFAULT 1.0,
    pitch       REAL DEFAULT 1.0,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══ SELF-MONITORING METRICS ════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS monitoring_metrics (
    id          TEXT PRIMARY KEY,
    metric_name TEXT NOT NULL,
    value       REAL,
    unit        TEXT,
    tags        TEXT DEFAULT '{}',
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══ SELF-IMPROVEMENT PATCHES ═══════════════════════════════════════════
CREATE TABLE IF NOT EXISTS improvement_patches (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT,
    patch_type      TEXT DEFAULT 'feature',
    status          TEXT DEFAULT 'proposed',
    file_path       TEXT,
    generated_code  TEXT,
    test_code       TEXT,
    ai_provider     TEXT,
    applied_at      DATETIME,
    test_result     TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta            TEXT DEFAULT '{}'
);

-- ═══ AUTONOMY / GOALS ════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS goals (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    status      TEXT DEFAULT 'active',
    progress    REAL DEFAULT 0.0,
    due_date    DATETIME,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta        TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS autonomous_actions (
    id          TEXT PRIMARY KEY,
    trigger     TEXT,
    action      TEXT NOT NULL,
    result      TEXT,
    feedback    TEXT,
    rating      INTEGER,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══ CONTACTS ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS contacts (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    phone       TEXT,
    email       TEXT,
    platform    TEXT DEFAULT 'local',
    external_id TEXT,
    tags        TEXT DEFAULT '[]',
    notes       TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    meta        TEXT DEFAULT '{}'
);

-- ═══ PHONE CALLS ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS call_logs (
    id          TEXT PRIMARY KEY,
    direction   TEXT NOT NULL,
    number      TEXT,
    contact_id  TEXT REFERENCES contacts(id),
    duration_s  INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'completed',
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at    DATETIME,
    meta        TEXT DEFAULT '{}'
);

-- ═══ PROVIDER USAGE ══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS provider_usage (
    id          TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0.0,
    latency_ms  INTEGER DEFAULT 0,
    success     INTEGER DEFAULT 1,
    task_type   TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ═══ SETTINGS KV ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS settings_kv (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_sync_queue_synced ON sync_queue(synced, created_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_name ON monitoring_metrics(metric_name, recorded_at);
CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_datetime);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type, importance);
"""


async def init_db():
    """Inicializa o banco de dados com todas as tabelas."""
    db = await get_db()
    for stmt in SCHEMA_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                await db.execute(stmt)
            except Exception as e:
                logger.debug(f"Schema stmt warning: {e}")
    await db.commit()
    logger.info(f"✅ Database inicializado: {settings.db_path}")
