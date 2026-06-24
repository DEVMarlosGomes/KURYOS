"""
Fase 2 — Backfill MongoDB FASE 0 → PostgreSQL

Copia: categorias, fragrancias, material_tipos, materiais, graneis
Seed:  contadores (counters) para FR, MP, EP, ES, RT, BK

Uso:
    cd backend
    python ../migrations/migrate_fase0.py

Idempotente: ON CONFLICT DO NOTHING em todos os inserts.
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env", override=False)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

import database as pg_db
from motor.motor_asyncio import AsyncIOMotorClient


def _dt(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


async def backfill_categorias(mongo_db, stats: dict):
    docs = await mongo_db.categorias.find({}, {"_id": 0}).to_list(10000)
    logger.info(f"  categorias: {len(docs)} documentos")
    for d in docs:
        try:
            await pg_db.execute(
                """
                INSERT INTO categorias(
                  id, tenant_id, cat3, nome, status,
                  solicitado_por, solicitado_por_id, solicitado_em,
                  aprovado_por, aprovado_por_id, aprovado_em,
                  justificativa, justificativa_aprovacao,
                  created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                ON CONFLICT(id) DO NOTHING
                """,
                d["id"], d["tenant_id"], d.get("cat3"), d.get("nome", ""),
                d.get("status", "pendente"),
                d.get("solicitado_por"), d.get("solicitado_por_id"),
                _dt(d.get("solicitado_em")),
                d.get("aprovado_por"), d.get("aprovado_por_id"),
                _dt(d.get("aprovado_em")),
                d.get("justificativa"), d.get("justificativa_aprovacao"),
                _dt(d.get("created_at")), _dt(d.get("updated_at")),
            )
            stats["categorias"] += 1
        except Exception as e:
            logger.warning(f"    SKIP categoria {d.get('cat3')}: {e}")


async def backfill_fragrancias(mongo_db, stats: dict):
    docs = await mongo_db.fragrancias.find({}, {"_id": 0}).to_list(10000)
    logger.info(f"  fragrancias: {len(docs)} documentos")
    for d in docs:
        try:
            fornecedores = d.get("fornecedores", [])
            await pg_db.execute(
                """
                INSERT INTO fragrancias(
                  id, tenant_id, nome, codigo,
                  codigo_interno, inspiracao, descricao, status,
                  fornecedores, created_by, created_by_name,
                  created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT(id) DO NOTHING
                """,
                d["id"], d["tenant_id"],
                d.get("inspiracao", ""), d.get("codigo_interno", ""),
                d.get("codigo_interno"), d.get("inspiracao"),
                d.get("descricao", ""), d.get("status", "ativa"),
                json.dumps(fornecedores),
                d.get("created_by"), d.get("created_by_name"),
                _dt(d.get("created_at")), _dt(d.get("updated_at")),
            )
            stats["fragrancias"] += 1
        except Exception as e:
            logger.warning(f"    SKIP fragrância {d.get('codigo_interno')}: {e}")


async def backfill_material_tipos(mongo_db, stats: dict):
    docs = await mongo_db.material_tipos.find({}, {"_id": 0}).to_list(1000)
    logger.info(f"  material_tipos: {len(docs)} documentos")
    for d in docs:
        try:
            await pg_db.execute(
                """
                INSERT INTO material_tipos(
                  id, tenant_id, nome, descricao,
                  tipo2, subtipos, justificativa, criado_por, criado_por_id,
                  created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT(id) DO NOTHING
                """,
                d["id"], d["tenant_id"],
                d.get("descricao", ""), d.get("descricao", ""),
                d.get("tipo2"), json.dumps(d.get("subtipos", [])),
                d.get("justificativa"), d.get("criado_por"), d.get("criado_por_id"),
                _dt(d.get("created_at")),
            )
            stats["material_tipos"] += 1
        except Exception as e:
            logger.warning(f"    SKIP material_tipo {d.get('tipo2')}: {e}")


async def backfill_materiais(mongo_db, stats: dict):
    docs = await mongo_db.materiais.find({}, {"_id": 0}).to_list(10000)
    logger.info(f"  materiais: {len(docs)} documentos")
    for d in docs:
        try:
            await pg_db.execute(
                """
                INSERT INTO materiais(
                  id, tenant_id, nome, codigo,
                  codigo_interno, tipo2, subtipo, descricao,
                  unidade_estoque, unidade, unidade_compra, fator_conversao,
                  atributos, fornecedores, status,
                  created_by, created_by_name,
                  created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                ON CONFLICT(id) DO NOTHING
                """,
                d["id"], d["tenant_id"],
                d.get("nome", ""), d.get("codigo_interno", ""),
                d.get("codigo_interno"), d.get("tipo2"),
                d.get("subtipo"), d.get("descricao", ""),
                d.get("unidade_estoque", "kg"), d.get("unidade_estoque", "kg"),
                d.get("unidade_compra", "kg"), d.get("fator_conversao", 1.0),
                json.dumps(d.get("atributos", {})),
                json.dumps(d.get("fornecedores", [])),
                d.get("status", "ativo"),
                d.get("created_by"), d.get("created_by_name"),
                _dt(d.get("created_at")), _dt(d.get("updated_at")),
            )
            stats["materiais"] += 1
        except Exception as e:
            logger.warning(f"    SKIP material {d.get('codigo_interno')}: {e}")


async def backfill_graneis(mongo_db, stats: dict):
    docs = await mongo_db.graneis.find({}, {"_id": 0}).to_list(10000)
    logger.info(f"  graneis: {len(docs)} documentos")
    for d in docs:
        try:
            await pg_db.execute(
                """
                INSERT INTO graneis(
                  id, tenant_id, nome, codigo,
                  codigo_interno, descricao, produto_pai_id,
                  unidade_estoque, standalone, status,
                  created_by, created_by_name,
                  created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                ON CONFLICT(id) DO NOTHING
                """,
                d["id"], d["tenant_id"],
                d.get("nome", ""), d.get("codigo_interno", ""),
                d.get("codigo_interno"), d.get("descricao", ""),
                d.get("produto_pai_id"),
                d.get("unidade_estoque", "kg"),
                d.get("standalone", True),
                d.get("status", "ativo"),
                d.get("created_by"), d.get("created_by_name"),
                _dt(d.get("created_at")), _dt(d.get("updated_at")),
            )
            stats["graneis"] += 1
        except Exception as e:
            logger.warning(f"    SKIP granel {d.get('codigo_interno')}: {e}")


async def seed_counters(mongo_db, tenant_id: str):
    """Seed PG counters from MongoDB values so sequence codes don't collide."""
    counter_keys = [
        "fr_seq",
        "mat_MP_seq", "mat_EP_seq", "mat_ES_seq", "mat_RT_seq", "mat_BK_seq",
    ]
    logger.info("  Seeding counters...")
    for name in counter_keys:
        mongo_key = f"{name}:{tenant_id}"
        doc = await mongo_db.counters.find_one({"_id": mongo_key})
        current_seq = (doc or {}).get("seq", 0)
        if current_seq <= 0:
            logger.info(f"    {name}: sem dados no MongoDB, ignorando")
            continue
        pg_key = mongo_key
        try:
            await pg_db.execute(
                """
                INSERT INTO counters(id, tenant_id, seq, updated_at)
                VALUES($1, $2, $3, NOW())
                ON CONFLICT(id) DO UPDATE SET
                    seq = GREATEST(counters.seq, EXCLUDED.seq),
                    updated_at = NOW()
                """,
                pg_key, tenant_id, current_seq,
            )
            logger.info(f"    {name}: seq={current_seq}")
        except Exception as e:
            logger.warning(f"    SKIP counter {name}: {e}")


async def migrate():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
    db_name = os.environ.get("DB_NAME", "kuryos_crm")

    mongo_client = AsyncIOMotorClient(mongo_url)
    mongo_db = mongo_client[db_name]

    try:
        await pg_db.init_db()
    except Exception as e:
        logger.error(f"PostgreSQL indisponível: {e}")
        mongo_client.close()
        return

    logger.info("Iniciando backfill FASE 0...")

    stats = {
        "categorias": 0, "fragrancias": 0,
        "material_tipos": 0, "materiais": 0, "graneis": 0,
    }

    await backfill_categorias(mongo_db, stats)
    await backfill_fragrancias(mongo_db, stats)
    await backfill_material_tipos(mongo_db, stats)
    await backfill_materiais(mongo_db, stats)
    await backfill_graneis(mongo_db, stats)

    # Seed counters para o único tenant existente
    tenants = await mongo_db.tenants.find({}, {"_id": 0, "id": 1}).to_list(100)
    for t in tenants:
        await seed_counters(mongo_db, t["id"])

    logger.info("\n=== Resultado ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v} registros migrados")

    await pg_db.close_db()
    mongo_client.close()


if __name__ == "__main__":
    asyncio.run(migrate())
