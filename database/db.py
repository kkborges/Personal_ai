"""
database/db.py — Gerenciador de Banco de Dados Unificado
=========================================================
Detecta automaticamente SQLite vs PostgreSQL pela DATABASE_URL.
- SQLite  → usa aiosqlite diretamente (dev/local)
- PostgreSQL → usa asyncpg com connection pool (produção)
"""
import logging
import json
from typing import Any, Optional
from config import settings

logger = logging.getLogger(__name__)

# ─── Interface pública ────────────────────────────────────────────────────────

async def init_db():
    """Inicializa banco de dados conforme o backend configurado."""
    if settings.is_postgres:
        from database.db_postgres import init_postgres
        await init_postgres()
        logger.info("✅ PostgreSQL inicializado")
    else:
        await _init_sqlite()
        logger.info("✅ SQLite inicializado")


async def close_db():
    if settings.is_postgres:
        from database.db_postgres import close_postgres
        await close_postgres()
    else:
        await _close_sqlite()


async def db_execute(query: str, params: tuple = ()) -> Any:
    """Executa INSERT/UPDATE/DELETE."""
    if settings.is_postgres:
        from database.db_postgres import execute as pg_execute
        # asyncpg usa $1, $2... — converte se necessário
        q, p = _adapt_query(query, params)
        return await pg_execute(q, *p)
    else:
        db = await _get_sqlite()
        cur = await db.execute(query, params)
        await db.commit()
        return cur


async def db_fetch(query: str, params: tuple = ()) -> list[dict]:
    """Retorna lista de dicts."""
    if settings.is_postgres:
        from database.db_postgres import fetch as pg_fetch
        q, p = _adapt_query(query, params)
        rows = await pg_fetch(q, *p)
        return [dict(r) for r in rows]
    else:
        db = await _get_sqlite()
        cur = await db.execute(query, params)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def db_fetchrow(query: str, params: tuple = ()) -> Optional[dict]:
    """Retorna um único dict ou None."""
    if settings.is_postgres:
        from database.db_postgres import fetchrow as pg_fetchrow
        q, p = _adapt_query(query, params)
        row = await pg_fetchrow(q, *p)
        return dict(row) if row else None
    else:
        db = await _get_sqlite()
        cur = await db.execute(query, params)
        row = await cur.fetchone()
        return dict(row) if row else None


async def db_fetchval(query: str, params: tuple = ()) -> Any:
    """Retorna um único valor escalar."""
    if settings.is_postgres:
        from database.db_postgres import fetchval as pg_fetchval
        q, p = _adapt_query(query, params)
        return await pg_fetchval(q, *p)
    else:
        db = await _get_sqlite()
        cur = await db.execute(query, params)
        row = await cur.fetchone()
        return row[0] if row else None


# ─── Helpers de compatibilidade SQLite ↔ PostgreSQL ──────────────────────────

def _adapt_query(query: str, params: tuple) -> tuple[str, tuple]:
    """
    Converte placeholders SQLite (?) para PostgreSQL ($1, $2...).
    Também serializa dicts/lists para JSON string.
    """
    if not params:
        return query, params
    new_params = []
    for p in params:
        if isinstance(p, (dict, list)):
            new_params.append(json.dumps(p, ensure_ascii=False))
        else:
            new_params.append(p)
    # Substitui ? por $1, $2...
    adapted = query
    counter = 0
    result = []
    i = 0
    while i < len(adapted):
        if adapted[i] == "?" and (i == 0 or adapted[i-1] != "'"):
            counter += 1
            result.append(f"${counter}")
        else:
            result.append(adapted[i])
        i += 1
    return "".join(result), tuple(new_params)


# ─── SQLite backend (dev) ─────────────────────────────────────────────────────
import aiosqlite
_db_conn: Optional[aiosqlite.Connection] = None

async def _get_sqlite() -> aiosqlite.Connection:
    global _db_conn
    if _db_conn is None:
        _db_conn = await aiosqlite.connect(settings.db_path)
        _db_conn.row_factory = aiosqlite.Row
        await _db_conn.execute("PRAGMA journal_mode=WAL")
        await _db_conn.execute("PRAGMA foreign_keys=ON")
        await _db_conn.execute("PRAGMA cache_size=10000")
    return _db_conn


async def _close_sqlite():
    global _db_conn
    if _db_conn:
        await _db_conn.close()
        _db_conn = None


# ─── Schema SQLite ────────────────────────────────────────────────────────────
SCHEMA_SQL = """
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
CREATE TABLE IF NOT EXISTS bluetooth_devices (
    mac_address TEXT PRIMARY KEY,
    name        TEXT,
    device_type TEXT DEFAULT 'unknown',
    trusted     INTEGER DEFAULT 0,
    last_seen   DATETIME,
    last_conn   DATETIME,
    meta        TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS voice_profiles (
    id          TEXT PRIMARY KEY DEFAULT 'default',
    voice_name  TEXT,
    language    TEXT DEFAULT 'pt-BR',
    speed       REAL DEFAULT 1.0,
    pitch       REAL DEFAULT 1.0,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS monitoring_metrics (
    id          TEXT PRIMARY KEY,
    metric_name TEXT NOT NULL,
    value       REAL,
    unit        TEXT,
    tags        TEXT DEFAULT '{}',
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
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
CREATE TABLE IF NOT EXISTS settings_kv (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_sync_queue_synced ON sync_queue(synced, created_at);
CREATE INDEX IF NOT EXISTS idx_monitoring_name ON monitoring_metrics(metric_name, recorded_at);
CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_datetime);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type, importance);
"""

async def _init_sqlite():
    db = await _get_sqlite()
    for stmt in SCHEMA_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                await db.execute(stmt)
            except Exception as e:
                logger.debug(f"SQLite schema warning: {e}")
    await db.commit()
    logger.info(f"✅ SQLite inicializado: {settings.db_path}")


# ─── Alias para compatibilidade com código legado ─────────────────────────────
async def get_db():
    """Compatibilidade retroativa — retorna conexão SQLite."""
    return await _get_sqlite()
