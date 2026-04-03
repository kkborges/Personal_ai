"""
database/db_postgres.py — Gerenciador PostgreSQL com asyncpg
=============================================================
Substitui aiosqlite em ambiente de produção.
Suporta connection pooling, migrações, e FTS via pg_trgm/to_tsvector.
"""
import logging
import asyncpg
from typing import Optional, Any
from config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        await init_postgres()
    return _pool


async def init_postgres():
    global _pool
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=settings.db_pool_size,
        command_timeout=60,
        server_settings={"application_name": "personal-ai-mobile"},
    )
    logger.info("✅ Pool PostgreSQL criado")
    await _run_migrations()


async def close_postgres():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("🔒 Pool PostgreSQL fechado")


async def execute(query: str, *args) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args) -> Any:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)


# ─── Migrações SQL ────────────────────────────────────────────────────────────

MIGRATIONS = [
    # 001 — Schema inicial
    """
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "pg_trgm";
    CREATE EXTENSION IF NOT EXISTS "unaccent";

    CREATE TABLE IF NOT EXISTS schema_migrations (
        version     INTEGER PRIMARY KEY,
        applied_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS conversations (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        title       TEXT,
        platform    TEXT DEFAULT 'mobile',
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        meta        JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS messages (
        id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
        role            TEXT NOT NULL,
        content         TEXT NOT NULL,
        tokens          INTEGER DEFAULT 0,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        meta            JSONB DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);

    CREATE TABLE IF NOT EXISTS memories (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        type        TEXT NOT NULL,
        content     TEXT NOT NULL,
        importance  REAL DEFAULT 0.5,
        source      TEXT,
        tags        JSONB DEFAULT '[]',
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        expires_at  TIMESTAMPTZ,
        meta        JSONB DEFAULT '{}',
        search_vec  TSVECTOR GENERATED ALWAYS AS (to_tsvector('portuguese', coalesce(content,''))) STORED
    );
    CREATE INDEX IF NOT EXISTS idx_memories_search ON memories USING GIN(search_vec);
    CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type, importance);
    CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories USING GIN(tags);

    CREATE TABLE IF NOT EXISTS calendar_events (
        id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        title           TEXT NOT NULL,
        description     TEXT,
        start_datetime  TIMESTAMPTZ NOT NULL,
        end_datetime    TIMESTAMPTZ,
        location        TEXT,
        all_day         BOOLEAN DEFAULT FALSE,
        recurrence      TEXT,
        reminder_min    INTEGER DEFAULT 15,
        source          TEXT DEFAULT 'local',
        external_id     TEXT,
        status          TEXT DEFAULT 'confirmed',
        platform        TEXT DEFAULT 'local',
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW(),
        meta            JSONB DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_calendar_start ON calendar_events(start_datetime);

    CREATE TABLE IF NOT EXISTS routines (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        name        TEXT NOT NULL,
        description TEXT,
        cron_expr   TEXT NOT NULL,
        actions     JSONB DEFAULT '[]',
        enabled     BOOLEAN DEFAULT TRUE,
        last_run    TIMESTAMPTZ,
        next_run    TIMESTAMPTZ,
        run_count   INTEGER DEFAULT 0,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        meta        JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS routine_history (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        routine_id  TEXT REFERENCES routines(id) ON DELETE CASCADE,
        status      TEXT,
        output      TEXT,
        error       TEXT,
        executed_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        type            TEXT NOT NULL,
        status          TEXT DEFAULT 'pending',
        priority        INTEGER DEFAULT 5,
        payload         JSONB DEFAULT '{}',
        result          JSONB,
        error           TEXT,
        attempts        INTEGER DEFAULT 0,
        max_attempts    INTEGER DEFAULT 3,
        depends_on      TEXT,
        scheduled_at    TIMESTAMPTZ DEFAULT NOW(),
        started_at      TIMESTAMPTZ,
        completed_at    TIMESTAMPTZ,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, scheduled_at);
    CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC, scheduled_at ASC) WHERE status = 'pending';

    CREATE TABLE IF NOT EXISTS action_logs (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        action_name TEXT NOT NULL,
        params      JSONB DEFAULT '{}',
        result      JSONB,
        success     BOOLEAN DEFAULT TRUE,
        duration_ms INTEGER DEFAULT 0,
        executed_at TIMESTAMPTZ DEFAULT NOW(),
        meta        JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS sync_queue (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        entity_type TEXT NOT NULL,
        entity_id   TEXT NOT NULL,
        operation   TEXT NOT NULL,
        payload     JSONB DEFAULT '{}',
        synced      BOOLEAN DEFAULT FALSE,
        retry_count INTEGER DEFAULT 0,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        synced_at   TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_sync_queue_pending ON sync_queue(synced, created_at) WHERE synced = FALSE;

    CREATE TABLE IF NOT EXISTS bluetooth_devices (
        mac_address TEXT PRIMARY KEY,
        name        TEXT,
        device_type TEXT DEFAULT 'unknown',
        trusted     BOOLEAN DEFAULT FALSE,
        last_seen   TIMESTAMPTZ,
        last_conn   TIMESTAMPTZ,
        meta        JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS voice_profiles (
        id          TEXT PRIMARY KEY DEFAULT 'default',
        voice_name  TEXT,
        language    TEXT DEFAULT 'pt-BR',
        speed       REAL DEFAULT 1.0,
        pitch       REAL DEFAULT 1.0,
        updated_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS monitoring_metrics (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        metric_name TEXT NOT NULL,
        value       REAL,
        unit        TEXT,
        tags        JSONB DEFAULT '{}',
        recorded_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_monitoring_name ON monitoring_metrics(metric_name, recorded_at DESC);

    CREATE TABLE IF NOT EXISTS improvement_patches (
        id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        title           TEXT NOT NULL,
        description     TEXT,
        patch_type      TEXT DEFAULT 'feature',
        status          TEXT DEFAULT 'proposed',
        file_path       TEXT,
        generated_code  TEXT,
        test_code       TEXT,
        ai_provider     TEXT,
        applied_at      TIMESTAMPTZ,
        test_result     TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        meta            JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS goals (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        title       TEXT NOT NULL,
        description TEXT,
        status      TEXT DEFAULT 'active',
        progress    REAL DEFAULT 0.0,
        due_date    TIMESTAMPTZ,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        meta        JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS autonomous_actions (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        trigger     TEXT,
        action      TEXT NOT NULL,
        result      TEXT,
        feedback    TEXT,
        rating      INTEGER,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS contacts (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        name        TEXT NOT NULL,
        phone       TEXT,
        email       TEXT,
        platform    TEXT DEFAULT 'local',
        external_id TEXT,
        tags        JSONB DEFAULT '[]',
        notes       TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW(),
        meta        JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS call_logs (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        direction   TEXT NOT NULL,
        number      TEXT,
        contact_id  TEXT REFERENCES contacts(id) ON DELETE SET NULL,
        duration_s  INTEGER DEFAULT 0,
        status      TEXT DEFAULT 'completed',
        started_at  TIMESTAMPTZ DEFAULT NOW(),
        ended_at    TIMESTAMPTZ,
        meta        JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS provider_usage (
        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
        provider    TEXT NOT NULL,
        model       TEXT NOT NULL,
        tokens_in   INTEGER DEFAULT 0,
        tokens_out  INTEGER DEFAULT 0,
        cost_usd    REAL DEFAULT 0.0,
        latency_ms  INTEGER DEFAULT 0,
        success     BOOLEAN DEFAULT TRUE,
        task_type   TEXT,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_provider_usage_created ON provider_usage(created_at DESC);

    CREATE TABLE IF NOT EXISTS settings_kv (
        key         TEXT PRIMARY KEY,
        value       TEXT,
        updated_at  TIMESTAMPTZ DEFAULT NOW()
    );

    INSERT INTO schema_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
    """,
]


async def _run_migrations():
    """Aplica migrações pendentes."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Garante tabela de controle
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                applied_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        applied = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        for i, migration in enumerate(MIGRATIONS, start=1):
            if i not in applied:
                logger.info(f"Aplicando migração {i}...")
                async with conn.transaction():
                    for stmt in migration.strip().split(";"):
                        stmt = stmt.strip()
                        if stmt:
                            try:
                                await conn.execute(stmt)
                            except Exception as e:
                                logger.warning(f"Migration {i} stmt warning: {e}")
                logger.info(f"✅ Migração {i} aplicada")
        logger.info("✅ Todas as migrações aplicadas")
