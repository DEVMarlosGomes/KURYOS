"""
Compras Module (Ordens de Compra) - Purchase orders linked to BOM/Kickoff

This module is the implementation of Modulo 4 of the KURYOS ERP specification.
It is intentionally separate from orders_routes.py (which handles Ordens de
Producao - production orders for the factory floor).

Business rules:
- An OC (Ordem de Compra) cannot exist without a Kickoff with status "aprovado"
- An OC must reference a specific BOM item from that Kickoff
- The supplier must be homologado for that MP/insumo
- numero_oc is auto-generated in the format OC-YYYY-NNNN (sequential global per tenant)
- data_necessidade defaults to data_entrega_contratada - lead_time_producao_dias_uteis
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from rbac import require_roles
from workflow_engine import audit_log, next_sequence


compras_router = APIRouter(prefix="/api/compras")

db = None
get_current_user = None
new_id_func = None
now_iso_func = None


def init_compras(database, auth_func, id_func, iso_func):
    global db, get_current_user, new_id_func, now_iso_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id() -> str:
    return new_id_func()


def now_iso() -> str:
    return now_iso_func()


# ============ STATUS ============
OC_STATUSES = {"rascunho", "enviada", "confirmada", "entregue", "cancelada"}
OC_STATUS_LABELS = {
    "rascunho": "Rascunho",
    "enviada": "Enviada",
    "confirmada": "Confirmada",
    "entregue": "Entregue",
    "cancelada": "Cancelada",
}

# Roles allowed to manage purchase orders
COMPRAS_WRITE_ROLES = {"admin", "compras", "engenharia_produto"}
COMPRAS_READ_ROLES = {"admin", "compras", "engenharia_produto", "lider_pd", "qa", "sales_ops"}


# ============ MODELS ============
class OCCreateInput(BaseModel):
    kickoff_id: str
    bom_item_id: str  # codigo_interno of the BOM line, or generated id
    fornecedor_id: str
    quantidade: float
    unidade: str
    preco_unitario_rs: float
    data_necessidade: Optional[str] = None  # ISO date; auto-calculated if omitted
    observacoes: Optional[str] = ""


class OCUpdateInput(BaseModel):
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    preco_unitario_rs: Optional[float] = None
    data_necessidade: Optional[str] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None
    fornecedor_id: Optional[str] = None


# ============ HELPERS ============
def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _add_business_days(start: datetime, days: int) -> datetime:
    """Subtract `days` business days from `start`, skipping Sat/Sun."""
    if days <= 0:
        return start
    cursor = start
    remaining = days
    while remaining > 0:
        cursor = cursor - timedelta(days=1)
        if cursor.weekday() < 5:  # Mon-Fri = 0-4
            remaining -= 1
    return cursor


async def _get_kickoff_or_404(kickoff_id: str, tenant_id: str) -> dict:
    kickoff = await db.kickoffs.find_one({"id": kickoff_id, "tenant_id": tenant_id}, {"_id": 0})
    if not kickoff:
        raise HTTPException(status_code=404, detail="Kickoff nao encontrado.")
    return kickoff


async def _ensure_kickoff_aprovado(kickoff_id: str, tenant_id: str) -> dict:
    kickoff = await _get_kickoff_or_404(kickoff_id, tenant_id)
    if kickoff.get("status") != "aprovado":
        raise HTTPException(
            status_code=400,
            detail=f"Ordem de Compra exige Kickoff aprovado. Status atual: {kickoff.get('status')}.",
        )
    return kickoff


def _find_bom_line(kickoff: dict, bom_item_id: str) -> Optional[Dict[str, Any]]:
    bom = kickoff.get("bom") or []
    for line in bom:
        if line.get("codigo_interno") == bom_item_id or line.get("id") == bom_item_id:
            return line
    return None


async def _ensure_supplier_homologado(fornecedor_id: str, tenant_id: str) -> dict:
    forn = await db.homologacao_fornecedores.find_one(
        {"id": fornecedor_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not forn:
        raise HTTPException(status_code=404, detail="Fornecedor nao encontrado.")
    if forn.get("status") not in {"homologado", "em_avaliacao"}:
        raise HTTPException(
            status_code=400,
            detail=f"Fornecedor com status '{forn.get('status')}' nao pode receber novas Ordens de Compra.",
        )
    return forn


async def _generate_oc_number(tenant_id: str) -> str:
    seq = await next_sequence(tenant_id, "ordem_compra", start=0)
    return f"OC-{datetime.now(timezone.utc).year}-{seq:04d}"


def _calc_data_necessidade(kickoff: dict) -> Optional[str]:
    """Default data_necessidade = data_entrega_contratada - lead_time_producao_dias_uteis."""
    bloco2 = kickoff.get("bloco2") or {}
    entrega_str = bloco2.get("data_entrega_contratada")
    lead = bloco2.get("lead_time_producao_dias_uteis")
    entrega = _parse_iso_date(entrega_str)
    if not entrega or not lead:
        return None
    necessidade = _add_business_days(entrega, int(lead))
    return necessidade.date().isoformat()


def _decorate_oc(oc: dict) -> dict:
    out = dict(oc)
    out["status_label"] = OC_STATUS_LABELS.get(oc.get("status", ""), oc.get("status", ""))
    return out


# ============ ENDPOINTS ============

@compras_router.get("/boms")
async def list_boms_for_compras(request: Request, kickoff_id: Optional[str] = None):
    """List BOMs of approved Kickoffs, available for purchase order creation.

    If kickoff_id is provided, returns only that Kickoff's BOM.
    """
    user = await get_current_user(request)
    require_roles(user, COMPRAS_READ_ROLES)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"], "status": "aprovado"}
    if kickoff_id:
        query["id"] = kickoff_id
    cursor = db.kickoffs.find(query, {"_id": 0}).sort("approved_at", -1)
    docs = await cursor.to_list(500)
    boms = []
    for ko in docs:
        boms.append(
            {
                "kickoff_id": ko["id"],
                "numero_kickoff": ko.get("numero_kickoff"),
                "cliente": ko.get("cliente"),
                "projeto_vinculado": ko.get("projeto_vinculado"),
                "approved_at": ko.get("approved_at"),
                "bom": ko.get("bom") or [],
            }
        )
    return {"boms": boms, "count": len(boms)}


@compras_router.post("/ordens")
async def create_oc(data: OCCreateInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_WRITE_ROLES)
    kickoff = await _ensure_kickoff_aprovado(data.kickoff_id, user["tenant_id"])
    bom_line = _find_bom_line(kickoff, data.bom_item_id)
    if not bom_line:
        raise HTTPException(
            status_code=400,
            detail=f"Item '{data.bom_item_id}' nao encontrado no BOM do Kickoff {kickoff.get('numero_kickoff')}.",
        )
    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero.")
    if data.preco_unitario_rs < 0:
        raise HTTPException(status_code=400, detail="Preco unitario nao pode ser negativo.")
    fornecedor = await _ensure_supplier_homologado(data.fornecedor_id, user["tenant_id"])

    data_necessidade = data.data_necessidade or _calc_data_necessidade(kickoff)
    numero_oc = await _generate_oc_number(user["tenant_id"])

    oc_doc = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "numero_oc": numero_oc,
        "kickoff_id": kickoff["id"],
        "numero_kickoff": kickoff.get("numero_kickoff"),
        "projeto_id": kickoff.get("projeto_id"),
        "bom_item_id": data.bom_item_id,
        "bom_item_descricao": bom_line.get("descricao"),
        "bom_item_tipo": bom_line.get("tipo"),
        "fornecedor_id": fornecedor["id"],
        "fornecedor_nome": fornecedor.get("razao_social", ""),
        "fornecedor_cnpj": fornecedor.get("cnpj", ""),
        "quantidade": float(data.quantidade),
        "unidade": data.unidade,
        "preco_unitario_rs": float(data.preco_unitario_rs),
        "valor_total_rs": float(data.quantidade) * float(data.preco_unitario_rs),
        "data_necessidade": data_necessidade,
        "status": "rascunho",
        "observacoes": data.observacoes or "",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "updated_at": now_iso(),
    }
    await db.ordens_compra.insert_one(oc_doc)
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="oc_created",
        entity_type="ordem_compra",
        entity_id=oc_doc["id"],
        before=None,
        after={"numero_oc": numero_oc, "kickoff_id": kickoff["id"], "fornecedor_id": fornecedor["id"]},
    )
    return _decorate_oc(oc_doc)


@compras_router.get("/ordens")
async def list_ocs(
    request: Request,
    status: Optional[str] = None,
    kickoff_id: Optional[str] = None,
    fornecedor_id: Optional[str] = None,
):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_READ_ROLES)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if kickoff_id:
        query["kickoff_id"] = kickoff_id
    if fornecedor_id:
        query["fornecedor_id"] = fornecedor_id
    cursor = db.ordens_compra.find(query, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(1000)
    return {"ordens": [_decorate_oc(d) for d in docs], "count": len(docs)}


@compras_router.get("/ordens/{oc_id}")
async def get_oc(oc_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_READ_ROLES)
    doc = await db.ordens_compra.find_one({"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Ordem de Compra nao encontrada.")
    return _decorate_oc(doc)


@compras_router.put("/ordens/{oc_id}")
async def update_oc(oc_id: str, data: OCUpdateInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_WRITE_ROLES)
    existing = await db.ordens_compra.find_one(
        {"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Ordem de Compra nao encontrada.")
    if existing.get("status") in {"entregue", "cancelada"}:
        raise HTTPException(
            status_code=400,
            detail=f"Ordem de Compra com status '{existing.get('status')}' nao pode ser editada.",
        )

    update_doc: Dict[str, Any] = {"updated_at": now_iso()}
    payload = data.dict(exclude_unset=True)

    if "status" in payload:
        new_status = payload["status"]
        if new_status not in OC_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status '{new_status}' invalido.")
        update_doc["status"] = new_status
    if "fornecedor_id" in payload and payload["fornecedor_id"]:
        forn = await _ensure_supplier_homologado(payload["fornecedor_id"], user["tenant_id"])
        update_doc["fornecedor_id"] = forn["id"]
        update_doc["fornecedor_nome"] = forn.get("razao_social", "")
        update_doc["fornecedor_cnpj"] = forn.get("cnpj", "")
    for field in ("quantidade", "unidade", "preco_unitario_rs", "data_necessidade", "observacoes"):
        if field in payload:
            update_doc[field] = payload[field]
    # Recalculate valor_total if numbers changed
    if "quantidade" in update_doc or "preco_unitario_rs" in update_doc:
        qtd = update_doc.get("quantidade", existing.get("quantidade", 0))
        preco = update_doc.get("preco_unitario_rs", existing.get("preco_unitario_rs", 0))
        update_doc["valor_total_rs"] = float(qtd) * float(preco)

    await db.ordens_compra.update_one(
        {"id": oc_id, "tenant_id": user["tenant_id"]},
        {"$set": update_doc},
    )
    new_doc = await db.ordens_compra.find_one(
        {"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    )
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="oc_updated",
        entity_type="ordem_compra",
        entity_id=oc_id,
        before={k: existing.get(k) for k in update_doc.keys()},
        after={k: new_doc.get(k) for k in update_doc.keys()},
    )
    return _decorate_oc(new_doc)


@compras_router.delete("/ordens/{oc_id}")
async def delete_oc(oc_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, {"admin"})
    existing = await db.ordens_compra.find_one(
        {"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Ordem de Compra nao encontrada.")
    if existing.get("status") not in {"rascunho", "cancelada"}:
        raise HTTPException(
            status_code=400,
            detail="Apenas Ordens de Compra em rascunho ou canceladas podem ser excluidas.",
        )
    await db.ordens_compra.delete_one({"id": oc_id, "tenant_id": user["tenant_id"]})
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="oc_deleted",
        entity_type="ordem_compra",
        entity_id=oc_id,
        before=existing,
        after=None,
    )
    return {"deleted": True}
