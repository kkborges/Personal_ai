#!/usr/bin/env python3
"""
Personal AI Mobile — Migração SQLite → PostgreSQL
===================================================
Script para migrar dados do banco SQLite local para PostgreSQL.

Uso:
    python database/migrate_sqlite_to_postgres.py \
        --sqlite data/mobile_ai.db \
        --postgres "postgresql://user:pass@localhost:5432/personal_ai"

Opções:
    --dry-run     Apenas lê e mostra o que seria migrado
    --tables      Tabelas específicas (padrão: todas)
    --batch-size  Quantidade de linhas por lote (padrão: 500)
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, List
import json
from datetime import datetime

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# Mapeamento de tipos SQLite → PostgreSQL
TYPE_MAP = {
    "INTEGER": "BIGINT",
    "TEXT": "TEXT",
    "REAL": "NUMERIC",
    "BLOB": "BYTEA",
    "BOOLEAN": "BOOLEAN",
    "DATETIME": "TIMESTAMPTZ",
    "JSON": "JSONB",
}

# Tabelas para migrar (em ordem para respeitar FK)
TABLES_ORDER = [
    "conversations",
    "messages",
    "memories",
    "calendar_events",
    "jobs",
    "routines",
    "routine_history",
    "monitoring_metrics",
    "sync_queue",
    "system_config",
]


async def migrate(
    sqlite_path: str,
    postgres_url: str,
    dry_run: bool = False,
    tables: Optional[List[str]] = None,
    batch_size: int = 500,
):
    """Executa a migração completa."""
    
    try:
        import aiosqlite
        import asyncpg
    except ImportError:
        logger.error("Instale: pip install aiosqlite asyncpg")
        sys.exit(1)

    if not Path(sqlite_path).exists():
        logger.error(f"SQLite não encontrado: {sqlite_path}")
        sys.exit(1)

    target_tables = tables or TABLES_ORDER
    stats = {"migrated": {}, "skipped": [], "errors": []}

    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}Iniciando migração: {sqlite_path} → PostgreSQL")

    async with aiosqlite.connect(sqlite_path) as sqlite:
        sqlite.row_factory = aiosqlite.Row
        
        # Verifica quais tabelas existem no SQLite
        cursor = await sqlite.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        existing_tables = {row[0] for row in await cursor.fetchall()}
        logger.info(f"Tabelas encontradas no SQLite: {existing_tables}")

        # Conecta ao PostgreSQL
        if not dry_run:
            pg_conn = await asyncpg.connect(postgres_url)
        else:
            pg_conn = None

        try:
            for table in target_tables:
                if table not in existing_tables:
                    logger.info(f"  ⏭ Tabela '{table}' não existe no SQLite, pulando...")
                    stats["skipped"].append(table)
                    continue

                # Conta registros
                cnt_cur = await sqlite.execute(f"SELECT COUNT(*) FROM {table}")
                total = (await cnt_cur.fetchone())[0]
                logger.info(f"  📦 Migrando '{table}' ({total} registros)...")

                if dry_run:
                    stats["migrated"][table] = total
                    continue

                # Busca colunas
                col_cur = await sqlite.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in await col_cur.fetchall()]
                
                migrated = 0
                offset = 0

                while True:
                    rows = await (await sqlite.execute(
                        f"SELECT * FROM {table} LIMIT {batch_size} OFFSET {offset}"
                    )).fetchall()
                    
                    if not rows:
                        break

                    # Converte linhas para lista de dicts
                    records = []
                    for row in rows:
                        record = {}
                        for i, col in enumerate(columns):
                            val = row[i]
                            # Tenta parsear JSON strings
                            if isinstance(val, str) and val.startswith(("{", "[")):
                                try:
                                    val = json.loads(val)
                                except:
                                    pass
                            record[col] = val
                        records.append(record)

                    # Insere no PostgreSQL (ON CONFLICT DO NOTHING para idempotência)
                    placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
                    cols = ", ".join(columns)
                    query = f"""
                        INSERT INTO {table} ({cols})
                        VALUES ({placeholders})
                        ON CONFLICT DO NOTHING
                    """
                    
                    await pg_conn.executemany(query, [list(r.values()) for r in records])
                    
                    migrated += len(records)
                    offset += batch_size
                    
                    if total > 0:
                        pct = migrated / total * 100
                        logger.info(f"    {migrated}/{total} ({pct:.0f}%)")

                stats["migrated"][table] = migrated
                logger.info(f"  ✅ '{table}': {migrated} registros migrados")

        except Exception as e:
            logger.error(f"Erro na migração: {e}", exc_info=True)
            stats["errors"].append(str(e))
        finally:
            if pg_conn:
                await pg_conn.close()

    # Relatório final
    print("\n" + "="*60)
    print("RELATÓRIO DE MIGRAÇÃO")
    print("="*60)
    for table, count in stats["migrated"].items():
        print(f"  ✅ {table}: {count} registros")
    for table in stats["skipped"]:
        print(f"  ⏭ {table}: não existia no SQLite")
    for err in stats["errors"]:
        print(f"  ❌ ERRO: {err}")
    
    total_migrated = sum(stats["migrated"].values())
    print(f"\nTotal migrado: {total_migrated} registros")
    print(f"{'[DRY-RUN — nenhum dado foi escrito]' if dry_run else 'Migração concluída!'}")
    print("="*60)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migração SQLite → PostgreSQL")
    parser.add_argument("--sqlite", default="data/mobile_ai.db",
                        help="Caminho do arquivo SQLite (padrão: data/mobile_ai.db)")
    parser.add_argument("--postgres",
                        default="postgresql://personal_ai:personal_ai_secret@localhost:5432/personal_ai",
                        help="URL de conexão PostgreSQL")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apenas simula, não escreve dados")
    parser.add_argument("--tables", nargs="+",
                        help="Tabelas específicas para migrar")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="Registros por lote (padrão: 500)")

    args = parser.parse_args()

    asyncio.run(migrate(
        sqlite_path=args.sqlite,
        postgres_url=args.postgres,
        dry_run=args.dry_run,
        tables=args.tables,
        batch_size=args.batch_size,
    ))


if __name__ == "__main__":
    main()
