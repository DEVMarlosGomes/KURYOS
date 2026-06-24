"""
PostgreSQL connection pool via asyncpg.
Replaces Motor/MongoDB — used during and after the Supabase migration.
"""
import json
import os
import asyncpg
from typing import Any, Optional
from urllib.parse import urlparse, quote


def _safe_dsn(url: str) -> str:
    """URL-encodes a password that may contain special characters (@, #, !, etc.)."""
    p = urlparse(url)
    if not p.password:
        return url
    encoded = quote(p.password, safe="")
    return url.replace(f":{p.password}@", f":{encoded}@", 1)


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codec so Python dicts/lists are handled automatically."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


_pool: Optional[asyncpg.Pool] = None


async def init_db() -> None:
    global _pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida no ambiente")
    # statement_cache_size=0 required for Supabase pgbouncer (transaction mode)
    _pool = await asyncpg.create_pool(
        _safe_dsn(url),
        min_size=2,
        max_size=10,
        command_timeout=30,
        ssl="require",
        statement_cache_size=0,
        init=_init_connection,
        server_settings={"application_name": "kuryos-api"},
    )


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool PostgreSQL não inicializado. Chame init_db() primeiro.")
    return _pool


# ─── Query helpers ───────────────────────────────────────────────────────────

async def fetch_one(query: str, *args) -> Optional[dict]:
    """Retorna uma linha como dict ou None."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def fetch_all(query: str, *args) -> list[dict]:
    """Retorna todas as linhas como lista de dicts."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


async def fetch_val(query: str, *args) -> Any:
    """Retorna um único valor escalar."""
    async with get_pool().acquire() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args) -> str:
    """Executa INSERT/UPDATE/DELETE, retorna status (ex: 'UPDATE 1')."""
    async with get_pool().acquire() as conn:
        return await conn.execute(query, *args)


async def execute_many(query: str, args_list: list) -> None:
    """Executa o mesmo statement para múltiplos conjuntos de parâmetros."""
    async with get_pool().acquire() as conn:
        await conn.executemany(query, args_list)


async def execute_in_transaction(queries: list[tuple[str, list]]) -> None:
    """Executa múltiplos statements em uma única transação."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            for query, args in queries:
                await conn.execute(query, *args)
