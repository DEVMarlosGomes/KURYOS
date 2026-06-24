"""
Fragrâncias — Cadastro de Fragrâncias (R08)
============================================
PostgreSQL backend (Fase 2 migration).

Código interno FR-[SEQ5]. Fornecedores como JSONB array.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rbac import require_roles, PD_FULL
import database as pg_db

logger = logging.getLogger(__name__)

fragrancias_router = APIRouter(prefix="/api/cadastros", tags=["fragrancias"])

# MongoDB db — cross-module queries (skus, bom_items) not yet migrated
db = None
_get_current_user = None
_new_id = None
_now_iso = None


def init_fragrancias(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Fragrâncias module initialized (PostgreSQL)")


async def create_fragrancias_indexes():
    pass  # Indexes managed in 002_fase0_fix_schema.sql


# ─── helpers ─────────────────────────────────────────────────────────────────

def _row(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _rows(rows) -> list[dict]:
    return [_row(r) for r in rows]


async def _next_fr_seq(tenant_id: str) -> str:
    from workflow_engine import next_sequence_pg
    seq = await next_sequence_pg(tenant_id, "fr_seq", start=0)
    return f"FR-{str(seq).zfill(5)}"


# ─── schemas ─────────────────────────────────────────────────────────────────

class FornecedorRef(BaseModel):
    fornecedor_id: str = ""
    fornecedor_nome: str
    codigo_fornecedor: str
    status_homologacao: str = "em_avaliacao"
    preco_por_kg: Optional[float] = None
    moeda: str = "BRL"
    lead_time_dias: Optional[int] = None
    moq_kg: Optional[float] = None
    observacoes: str = ""


class FragranciaCreate(BaseModel):
    inspiracao: str
    descricao: str = ""
    fornecedores: List[FornecedorRef] = []
    status: str = "ativa"


class FragranciaUpdate(BaseModel):
    inspiracao: Optional[str] = None
    descricao: Optional[str] = None
    status: Optional[str] = None


class FornecedorRefAdd(BaseModel):
    fornecedor_id: str = ""
    fornecedor_nome: str
    codigo_fornecedor: str
    status_homologacao: str = "em_avaliacao"
    preco_por_kg: Optional[float] = None
    moeda: str = "BRL"
    lead_time_dias: Optional[int] = None
    moq_kg: Optional[float] = None
    observacoes: str = ""


# ─── endpoints ───────────────────────────────────────────────────────────────

@fragrancias_router.get("/fragrancias")
async def list_fragrancias(
    request: Request,
    search: Optional[str] = None,
    status: Optional[str] = None,
):
    user = await _get_current_user(request)
    tid = user["tenant_id"]

    if search and status:
        rows = await pg_db.fetch_all(
            """
            SELECT * FROM fragrancias
            WHERE tenant_id=$1 AND status=$2
              AND (codigo_interno ILIKE $3 OR inspiracao ILIKE $3
                   OR fornecedores::text ILIKE $3)
            ORDER BY codigo_interno
            """,
            tid, status, f"%{search}%",
        )
    elif search:
        rows = await pg_db.fetch_all(
            """
            SELECT * FROM fragrancias
            WHERE tenant_id=$1
              AND (codigo_interno ILIKE $2 OR inspiracao ILIKE $2
                   OR fornecedores::text ILIKE $2)
            ORDER BY codigo_interno
            """,
            tid, f"%{search}%",
        )
    elif status:
        rows = await pg_db.fetch_all(
            "SELECT * FROM fragrancias WHERE tenant_id=$1 AND status=$2 ORDER BY codigo_interno",
            tid, status,
        )
    else:
        rows = await pg_db.fetch_all(
            "SELECT * FROM fragrancias WHERE tenant_id=$1 ORDER BY codigo_interno",
            tid,
        )
    items = _rows(rows)
    return {"fragrancias": items, "total": len(items)}


@fragrancias_router.get("/fragrancias/{codigo_interno}")
async def get_fragrancia(codigo_interno: str, request: Request):
    user = await _get_current_user(request)
    row = await pg_db.fetch_one(
        "SELECT * FROM fragrancias WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Fragrância {codigo_interno} não encontrada")
    return _row(row)


@fragrancias_router.post("/fragrancias", status_code=201)
async def create_fragrancia(data: FragranciaCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    if not data.inspiracao.strip():
        raise HTTPException(status_code=400, detail="Inspiração é obrigatória")

    codigo = await _next_fr_seq(user["tenant_id"])

    fornecedores = []
    for f in data.fornecedores:
        entry = f.model_dump()
        entry["adicionado_em"] = datetime.utcnow().isoformat()
        entry["codigo_fornecedor"] = entry["codigo_fornecedor"].strip()
        fornecedores.append(entry)

    new_id = _new_id()
    await pg_db.execute(
        """
        INSERT INTO fragrancias(
          id, tenant_id, nome, codigo,
          codigo_interno, inspiracao, descricao, status,
          fornecedores, created_by, created_by_name,
          created_at, updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW(),NOW())
        """,
        new_id, user["tenant_id"],
        data.inspiracao.strip(), codigo,
        codigo, data.inspiracao.strip(),
        data.descricao.strip(), data.status,
        fornecedores,
        user["id"], user.get("name", ""),
    )
    doc = _row(await pg_db.fetch_one("SELECT * FROM fragrancias WHERE id=$1", new_id))
    logger.info(f"Fragrância criada: {codigo} — {data.inspiracao}")
    return doc


@fragrancias_router.patch("/fragrancias/{codigo_interno}")
async def update_fragrancia(codigo_interno: str, data: FragranciaUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    existing = await pg_db.fetch_one(
        "SELECT id FROM fragrancias WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Fragrância {codigo_interno} não encontrada")

    sets = ["updated_at=NOW()"]
    params: list = []
    idx = 1

    if data.inspiracao is not None:
        sets.append(f"inspiracao=${idx}, nome=${idx}")
        params.append(data.inspiracao.strip())
        idx += 1
    if data.descricao is not None:
        sets.append(f"descricao=${idx}")
        params.append(data.descricao.strip())
        idx += 1
    if data.status is not None:
        sets.append(f"status=${idx}")
        params.append(data.status)
        idx += 1

    params += [user["tenant_id"], codigo_interno.upper()]
    await pg_db.execute(
        f"UPDATE fragrancias SET {', '.join(sets)} WHERE tenant_id=${idx} AND codigo_interno=${idx+1}",
        *params,
    )
    return _row(await pg_db.fetch_one(
        "SELECT * FROM fragrancias WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    ))


@fragrancias_router.post("/fragrancias/{codigo_interno}/fornecedores")
async def add_fornecedor(codigo_interno: str, data: FornecedorRefAdd, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    row = await pg_db.fetch_one(
        "SELECT id, fornecedores FROM fragrancias WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Fragrância {codigo_interno} não encontrada")

    novo = data.model_dump()
    novo["codigo_fornecedor"] = novo["codigo_fornecedor"].strip()
    fornecedores = list(row["fornecedores"] or [])

    replaced = False
    for i, f in enumerate(fornecedores):
        if f.get("codigo_fornecedor") == novo["codigo_fornecedor"]:
            novo["adicionado_em"] = f.get("adicionado_em", datetime.utcnow().isoformat())
            fornecedores[i] = novo
            replaced = True
            break
    if not replaced:
        novo["adicionado_em"] = datetime.utcnow().isoformat()
        fornecedores.append(novo)

    await pg_db.execute(
        "UPDATE fragrancias SET fornecedores=$1, updated_at=NOW() WHERE tenant_id=$2 AND codigo_interno=$3",
        fornecedores, user["tenant_id"], codigo_interno.upper(),
    )
    return {"msg": "Fornecedor atualizado", "codigo_interno": codigo_interno.upper(), "fornecedores": fornecedores}


@fragrancias_router.get("/fragrancias/by-sku/{sku_id}")
async def fragrancias_by_sku(sku_id: str, request: Request):
    """Consulta fragrâncias usadas por um SKU (via BOM)."""
    user = await _get_current_user(request)
    sku_row = await pg_db.fetch_one(
        "SELECT id, produto_pai_id FROM skus WHERE id=$1 AND tenant_id=$2",
        sku_id, user["tenant_id"],
    )
    if not sku_row:
        raise HTTPException(status_code=404, detail="SKU não encontrado")
    sku = dict(sku_row)
    produto_pai_id = sku.get("produto_pai_id")
    if not produto_pai_id:
        return {"fragrancias": [], "msg": "SKU sem produto-pai vinculado"}

    bom_rows = await pg_db.fetch_all(
        "SELECT * FROM bom_items WHERE tenant_id=$1 AND produto_pai_id=$2 AND tipo='FR'",
        user["tenant_id"], produto_pai_id,
    )
    bom_items = [dict(r) for r in bom_rows]

    fr_codes = [item["codigo_material"] for item in bom_items if item.get("codigo_material")]
    fragrancias = []
    for code in fr_codes:
        row = await pg_db.fetch_one(
            "SELECT * FROM fragrancias WHERE tenant_id=$1 AND codigo_interno=$2",
            user["tenant_id"], code,
        )
        if row:
            fragrancias.append(_row(row))

    return {"fragrancias": fragrancias}
