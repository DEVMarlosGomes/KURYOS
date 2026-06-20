"""
requirements_routes.py — R20: Consulta de Necessidades de Material

Endpoints de leitura para os setores de Compras e PCP.
A explosão de BOM é feita em propostas_routes.py quando o pedido é confirmado.
"""

from fastapi import APIRouter, Request
from typing import Optional

requirements_router = APIRouter(prefix="/api", tags=["necessidades"])

db = None
_get_current_user = None


def init_requirements(database, get_current_user_fn):
    global db, _get_current_user
    db = database
    _get_current_user = get_current_user_fn


async def create_requirements_indexes():
    await db.order_material_requirements.create_index(
        [("tenant_id", 1), ("proposta_id", 1)], unique=True
    )
    await db.order_material_requirements.create_index(
        [("tenant_id", 1), ("projeto_id", 1)]
    )
    await db.order_material_requirements.create_index(
        [("tenant_id", 1), ("gerado_em", -1)]
    )


# ── Compras ───────────────────────────────────────────────────────────────────

@requirements_router.get("/compras/necessidades")
async def list_necessidades_compras(
    request: Request,
    status: Optional[str] = None,
    limit: int = 100,
):
    """Lista necessidades de material para o setor de Compras (responsavel=compras)."""
    user = await _get_current_user(request)
    query: dict = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status

    reqs = await db.order_material_requirements.find(
        query, {"_id": 0}
    ).sort("gerado_em", -1).limit(limit).to_list(limit)

    # Filtrar apenas itens de responsabilidade de compras
    result = []
    for req in reqs:
        materiais_compras = [
            m for m in req.get("materiais", [])
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
    query: dict = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status

    reqs = await db.order_material_requirements.find(
        query, {"_id": 0}
    ).sort("gerado_em", -1).limit(limit).to_list(limit)

    result = []
    for req in reqs:
        materiais_pcp = [
            m for m in req.get("materiais", [])
            if m.get("responsavel") == "pcp"
        ]
        if materiais_pcp:
            result.append({**req, "materiais": materiais_pcp})

    return result
