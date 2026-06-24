"""
requirements_routes.py — R20: Consulta de Necessidades de Material

Endpoints de leitura para os setores de Compras e PCP.
A explosão de BOM é feita em propostas_routes.py quando o pedido é confirmado.
"""

from datetime import datetime
from fastapi import APIRouter, Request
from typing import Optional

import database as pg_db

requirements_router = APIRouter(prefix="/api", tags=["necessidades"])

_get_current_user = None


def init_requirements(database, get_current_user_fn):
    global _get_current_user
    _get_current_user = get_current_user_fn


async def create_requirements_indexes():
    pass  # Indexes managed via migrations/007_fase7_schema.sql


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


# ── Compras ───────────────────────────────────────────────────────────────────

@requirements_router.get("/compras/necessidades")
async def list_necessidades_compras(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100,
):
    """Lista necessidades de material para o setor de Compras (responsavel=compras)."""
    user = await _get_current_user(request)
    if status:
        reqs = _rows(await pg_db.fetch_all(
            "SELECT * FROM order_material_requirements WHERE tenant_id=$1 AND status=$2 ORDER BY gerado_em DESC LIMIT $3",
            user["tenant_id"], status, limit,
        ))
    else:
        reqs = _rows(await pg_db.fetch_all(
            "SELECT * FROM order_material_requirements WHERE tenant_id=$1 ORDER BY gerado_em DESC LIMIT $2",
            user["tenant_id"], limit,
        ))

    result = []
    for req in reqs:
        materiais_compras = [
            m for m in (req.get("materiais") or [])
            if m.get("responsavel") == "compras"
        ]
        if materiais_compras:
            result.append({**req, "materiais": materiais_compras})
    return result


# ── PCP ───────────────────────────────────────────────────────────────────────

@requirements_router.get("/pcp/necessidades")
async def list_necessidades_pcp(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100,
):
    """Lista necessidades de material para o setor de PCP (responsavel=pcp)."""
    user = await _get_current_user(request)
    if status:
        reqs = _rows(await pg_db.fetch_all(
            "SELECT * FROM order_material_requirements WHERE tenant_id=$1 AND status=$2 ORDER BY gerado_em DESC LIMIT $3",
            user["tenant_id"], status, limit,
        ))
    else:
        reqs = _rows(await pg_db.fetch_all(
            "SELECT * FROM order_material_requirements WHERE tenant_id=$1 ORDER BY gerado_em DESC LIMIT $2",
            user["tenant_id"], limit,
        ))

    result = []
    for req in reqs:
        materiais_pcp = [
            m for m in (req.get("materiais") or [])
            if m.get("responsavel") == "pcp"
        ]
        if materiais_pcp:
            result.append({**req, "materiais": materiais_pcp})
    return result
