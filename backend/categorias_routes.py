"""
Categorias — Cadastro de Categorias de Produto (R22)
=====================================================
PostgreSQL backend (Fase 2 migration).

Fluxo: P&D / Comercial solicita → admin aprova.
CAT3 duplicado bloqueado citando categoria existente.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rbac import require_roles, ADMIN_ONLY, PD_FULL, COMERCIAL_FULL
import database as pg_db

logger = logging.getLogger(__name__)

categorias_router = APIRouter(prefix="/api/cadastros", tags=["categorias"])

# MongoDB db — cross-module only (e.g. SKU count guard, not yet migrated)
db = None
_get_current_user = None
_new_id = None
_now_iso = None

_SOLICITAR_ROLES = PD_FULL | COMERCIAL_FULL
_APROVAR_ROLES = ADMIN_ONLY


def init_categorias(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Categorias module initialized (PostgreSQL)")


async def create_categorias_indexes():
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


def _validate_cat3(cat3: str) -> str:
    cat3 = cat3.upper().strip()
    if not re.match(r"^[A-Z]{3}$", cat3):
        raise HTTPException(
            status_code=400,
            detail="CAT3 deve ter exatamente 3 letras maiúsculas (ex: CAP, BSP)",
        )
    return cat3


# ─── schemas ─────────────────────────────────────────────────────────────────

class CategoriaRequest(BaseModel):
    cat3: str
    nome: str
    justificativa: str


class CategoriaApprove(BaseModel):
    justificativa: Optional[str] = ""


# ─── endpoints ───────────────────────────────────────────────────────────────

@categorias_router.get("/categorias")
async def list_categorias(request: Request, status: Optional[str] = None):
    user = await _get_current_user(request)
    if status:
        rows = await pg_db.fetch_all(
            "SELECT * FROM categorias WHERE tenant_id=$1 AND status=$2 ORDER BY cat3",
            user["tenant_id"], status,
        )
    else:
        rows = await pg_db.fetch_all(
            "SELECT * FROM categorias WHERE tenant_id=$1 ORDER BY cat3",
            user["tenant_id"],
        )
    items = _rows(rows)
    return {"categorias": items, "total": len(items)}


@categorias_router.get("/categorias/{cat3}")
async def get_categoria(cat3: str, request: Request):
    user = await _get_current_user(request)
    cat3 = _validate_cat3(cat3)
    row = await pg_db.fetch_one(
        "SELECT * FROM categorias WHERE tenant_id=$1 AND cat3=$2",
        user["tenant_id"], cat3,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Categoria {cat3} não encontrada")
    return _row(row)


@categorias_router.post("/categorias", status_code=201)
async def request_categoria(data: CategoriaRequest, request: Request):
    user = await _get_current_user(request)
    require_roles(user, _SOLICITAR_ROLES)

    cat3 = _validate_cat3(data.cat3)
    nome = data.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome da categoria é obrigatório")
    if not data.justificativa.strip():
        raise HTTPException(status_code=400, detail="Justificativa é obrigatória")

    existing = await pg_db.fetch_one(
        "SELECT nome, status FROM categorias WHERE tenant_id=$1 AND cat3=$2",
        user["tenant_id"], cat3,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"CAT3 '{cat3}' já está em uso pela categoria '{existing['nome']}' (status: {existing['status']})",
        )

    new_id = _new_id()
    await pg_db.execute(
        """
        INSERT INTO categorias(
          id, tenant_id, cat3, nome, status,
          solicitado_por, solicitado_por_id, solicitado_em,
          justificativa, created_at, updated_at
        ) VALUES($1,$2,$3,$4,'pendente',$5,$6,NOW(),$7,NOW(),NOW())
        """,
        new_id, user["tenant_id"], cat3, nome,
        user.get("name", ""), user["id"], data.justificativa.strip(),
    )
    doc = _row(await pg_db.fetch_one("SELECT * FROM categorias WHERE id=$1", new_id))
    logger.info(f"Categoria {cat3} solicitada por {user.get('name')} — aguardando aprovação")
    return {
        "categoria": doc,
        "msg": f"Categoria {cat3} criada com status 'pendente'. Aguardando aprovação do administrador.",
    }


@categorias_router.post("/categorias/{cat3}/approve")
async def approve_categoria(cat3: str, data: CategoriaApprove, request: Request):
    user = await _get_current_user(request)
    require_roles(user, _APROVAR_ROLES)

    cat3 = _validate_cat3(cat3)
    row = await pg_db.fetch_one(
        "SELECT * FROM categorias WHERE tenant_id=$1 AND cat3=$2",
        user["tenant_id"], cat3,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Categoria {cat3} não encontrada")
    doc = _row(row)

    if doc["status"] == "ativa":
        raise HTTPException(status_code=409, detail=f"Categoria {cat3} já está ativa")
    if doc["status"] != "pendente":
        raise HTTPException(
            status_code=409,
            detail=f"Categoria {cat3} está com status '{doc['status']}' — apenas 'pendente' pode ser aprovada",
        )

    await pg_db.execute(
        """
        UPDATE categorias SET
            status='ativa', aprovado_por=$1, aprovado_por_id=$2,
            aprovado_em=NOW(), justificativa_aprovacao=$3, updated_at=NOW()
        WHERE tenant_id=$4 AND cat3=$5
        """,
        user.get("name", ""), user["id"], (data.justificativa or "").strip(),
        user["tenant_id"], cat3,
    )
    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM categorias WHERE tenant_id=$1 AND cat3=$2",
        user["tenant_id"], cat3,
    ))
    logger.info(f"Categoria {cat3} aprovada por {user.get('name')}")
    return {"categoria": updated, "msg": f"Categoria {cat3} aprovada e ativa."}


@categorias_router.post("/categorias/{cat3}/inactivate")
async def inactivate_categoria(cat3: str, request: Request):
    user = await _get_current_user(request)
    require_roles(user, _APROVAR_ROLES)

    cat3 = _validate_cat3(cat3)
    row = await pg_db.fetch_one(
        "SELECT status FROM categorias WHERE tenant_id=$1 AND cat3=$2",
        user["tenant_id"], cat3,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Categoria {cat3} não encontrada")
    if dict(row)["status"] != "ativa":
        raise HTTPException(status_code=409, detail="Apenas categorias ativas podem ser inativadas")

    sku_count = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM skus WHERE tenant_id=$1 AND cat3=$2 AND status='ativo'",
        user["tenant_id"], cat3,
    )
    if sku_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Categoria {cat3} possui {sku_count} SKU(s) ativos — inative os SKUs antes de inativar a categoria",
        )

    await pg_db.execute(
        "UPDATE categorias SET status='inativa', updated_at=NOW() WHERE tenant_id=$1 AND cat3=$2",
        user["tenant_id"], cat3,
    )
    return {"msg": f"Categoria {cat3} inativada. SKUs existentes não foram alterados."}
