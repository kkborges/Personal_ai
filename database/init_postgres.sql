-- ═══════════════════════════════════════════════════════════════════════════
-- init_postgres.sql — Script de inicialização do PostgreSQL
-- Executado automaticamente pelo Docker na primeira inicialização
-- ═══════════════════════════════════════════════════════════════════════════

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Configurações de performance
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET work_mem = '4MB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET wal_level = 'replica';
ALTER SYSTEM SET max_connections = 100;
ALTER SYSTEM SET idle_in_transaction_session_timeout = '5min';
ALTER SYSTEM SET statement_timeout = '5min';
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- log queries > 1s

-- Timezone
SET timezone = 'America/Sao_Paulo';
ALTER DATABASE personal_ai SET timezone TO 'America/Sao_Paulo';

-- Recarrega configuração
SELECT pg_reload_conf();

-- Mensagem de confirmação
DO $$
BEGIN
    RAISE NOTICE 'PostgreSQL Personal AI inicializado com sucesso.';
    RAISE NOTICE 'Extensões: uuid-ossp, pg_trgm, unaccent';
    RAISE NOTICE 'Timezone: America/Sao_Paulo';
END;
$$;
