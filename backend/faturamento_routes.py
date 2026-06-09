"""
Faturamento — emissão e controle de Notas Fiscais de saída.
Fluxo:
  1. PI concluído ou EXP expedida → criar NF (rascunho)
  2. Emitir NF → status emitida (número NF-e + chave de acesso registrados)
  3. Acompanhar pagamento: aguardando → pago_parcial → pago | vencido
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

faturamento_router = APIRouter(prefix="/api/faturamento")

db = None
get_current_user = None
new_id_func = None
now_iso_func = None


def init_faturamento(database, auth_func, id_func, iso_func):
    global db, get_current_user, new_id_func, now_iso_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def _new_id():
    return new_id_func()


def _now():
    return now_iso_func()


NF_STATUSES = ["rascunho", "emitida", "cancelada"]
PGTO_STATUSES = ["aguardando", "pago_parcial", "pago", "vencido"]

NF_TRANSITIONS = {
    "rascunho": ["emitida", "cancelada"],
    "emitida":  ["cancelada"],
    "cancelada": [],
}


# ===== MODELS =====
class NFCreate(BaseModel):
    order_id: Optional[str] = None
    order_numero: Optional[str] = None
    exp_id: Optional[str] = None
    exp_numero: Optional[str] = None
    cliente_nome: str
    cliente_id: Optional[str] = None
    cliente_cnpj: str = ""
    valor_produtos: float = 0.0
    valor_frete: float = 0.0
    valor_impostos: float = 0.0
    valor_total: float = 0.0
    forma_pagamento: str = ""         # boleto | pix | transferencia | prazo
    condicao_pagamento: str = ""      # à vista | 30/60/90 | etc.
    data_emissao: Optional[str] = None
    data_vencimento: Optional[str] = None
    observacoes: str = ""


class NFUpdate(BaseModel):
    status: Optional[str] = None
    numero_nfe: Optional[str] = None
    chave_acesso: Optional[str] = None
    valor_total: Optional[float] = None
    valor_frete: Optional[float] = None
    valor_impostos: Optional[float] = None
    forma_pagamento: Optional[str] = None
    condicao_pagamento: Optional[str] = None
    data_vencimento: Optional[str] = None
    status_pagamento: Optional[str] = None
    valor_pago: Optional[float] = None
    data_pagamento: Optional[str] = None
    observacoes: Optional[str] = None


# ===== SEQUENCE =====
async def _next_nf_interno(tenant_id: str) -> str:
    count = await db.faturamento_notas.count_documents({"tenant_id": tenant_id})
    return f"NF-{str(count + 1).zfill(6)}"


# ===== ROUTES =====
@faturamento_router.get("/notas")
async def list_notas(
    request: Request,
    status: Optional[str] = None,
    status_pagamento: Optional[str] = None,
    q: Optional[str] = None,
):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if status_pagamento:
        query["status_pagamento"] = status_pagamento
    if q:
        query["$or"] = [
            {"numero_interno": {"$regex": q, "$options": "i"}},
            {"numero_nfe": {"$regex": q, "$options": "i"}},
            {"cliente_nome": {"$regex": q, "$options": "i"}},
            {"order_numero": {"$regex": q, "$options": "i"}},
        ]
    notas = await db.faturamento_notas.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return notas


@faturamento_router.get("/notas/{nf_id}")
async def get_nota(nf_id: str, request: Request):
    user = await get_current_user(request)
    nf = await db.faturamento_notas.find_one({"id": nf_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not nf:
        raise HTTPException(status_code=404, detail="Nota Fiscal não encontrada")
    return nf


@faturamento_router.post("/notas")
async def create_nota(data: NFCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if not data.cliente_nome.strip():
        raise HTTPException(status_code=400, detail="Nome do cliente obrigatório")

    numero_interno = await _next_nf_interno(tid)
    now = _now()
    nf_id = _new_id()

    # Enrich from order if provided
    pi_ref = {}
    if data.order_id:
        pi = await db.orders.find_one({"id": data.order_id, "tenant_id": tid}, {"_id": 0})
        if pi:
            pi_ref["order_numero"] = pi.get("numero_pedido", data.order_numero or "")
            if not data.valor_total and pi.get("total_pedido"):
                data.valor_total = float(pi["total_pedido"])
                data.valor_produtos = data.valor_total

    # Auto compute total if not provided
    valor_total = data.valor_total or (data.valor_produtos + data.valor_frete + data.valor_impostos)

    nf = {
        "id": nf_id,
        "tenant_id": tid,
        "numero_interno": numero_interno,
        "numero_nfe": None,
        "chave_acesso": None,
        "order_id": data.order_id,
        "order_numero": pi_ref.get("order_numero") or data.order_numero,
        "exp_id": data.exp_id,
        "exp_numero": data.exp_numero,
        "cliente_nome": data.cliente_nome.strip(),
        "cliente_id": data.cliente_id,
        "cliente_cnpj": data.cliente_cnpj,
        "valor_produtos": data.valor_produtos,
        "valor_frete": data.valor_frete,
        "valor_impostos": data.valor_impostos,
        "valor_total": valor_total,
        "forma_pagamento": data.forma_pagamento,
        "condicao_pagamento": data.condicao_pagamento,
        "data_emissao": data.data_emissao or now[:10],
        "data_vencimento": data.data_vencimento,
        "status": "rascunho",
        "status_pagamento": "aguardando",
        "valor_pago": 0.0,
        "data_pagamento": None,
        "observacoes": data.observacoes,
        "historico": [{"de": None, "para": "rascunho", "por": user["name"], "em": now}],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.faturamento_notas.insert_one(nf)
    nf.pop("_id", None)

    # Link NF back to order
    if data.order_id:
        await db.orders.update_one(
            {"id": data.order_id, "tenant_id": tid},
            {"$set": {"nf_id": nf_id, "nf_numero": numero_interno, "updated_at": now}}
        )

    logger.info(f"NF {numero_interno} criada por {user['name']}")
    return nf


@faturamento_router.put("/notas/{nf_id}")
async def update_nota(nf_id: str, data: NFUpdate, request: Request):
    user = await get_current_user(request)
    nf = await db.faturamento_notas.find_one({"id": nf_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not nf:
        raise HTTPException(status_code=404, detail="NF não encontrada")

    now = _now()
    updates: Dict[str, Any] = {"updated_at": now}
    historico = list(nf.get("historico", []))
    payload = data.model_dump(exclude_unset=True)

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in NF_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = NF_TRANSITIONS.get(nf["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {nf['status']} → {novo_status} não permitida"
            )
        historico.append({"de": nf["status"], "para": novo_status, "por": user["name"], "em": now})
        updates["status"] = novo_status
        updates["historico"] = historico

    if "status_pagamento" in payload:
        sp = payload["status_pagamento"]
        if sp not in PGTO_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status de pagamento inválido: {sp}")
        updates["status_pagamento"] = sp

    for field in ("numero_nfe", "chave_acesso", "valor_total", "valor_frete", "valor_impostos",
                  "forma_pagamento", "condicao_pagamento", "data_vencimento",
                  "valor_pago", "data_pagamento", "observacoes"):
        if field in payload and payload[field] is not None:
            updates[field] = payload[field]

    await db.faturamento_notas.update_one({"id": nf_id}, {"$set": updates})
    return await db.faturamento_notas.find_one({"id": nf_id}, {"_id": 0})


@faturamento_router.delete("/notas/{nf_id}")
async def delete_blocked(nf_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de NF não é permitida. Cancele a nota.")


@faturamento_router.get("/dashboard")
async def faturamento_dashboard(request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    emitidas = await db.faturamento_notas.count_documents({"tenant_id": tid, "status": "emitida"})
    aguardando = await db.faturamento_notas.count_documents({"tenant_id": tid, "status_pagamento": "aguardando"})
    vencidas = await db.faturamento_notas.count_documents({"tenant_id": tid, "status_pagamento": "vencido"})
    # Sum total receivable
    pipeline = [
        {"$match": {"tenant_id": tid, "status": "emitida", "status_pagamento": {"$in": ["aguardando", "pago_parcial"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$valor_total"}, "pago": {"$sum": "$valor_pago"}}}
    ]
    agg = await db.faturamento_notas.aggregate(pipeline).to_list(1)
    total_ar = agg[0]["total"] if agg else 0.0
    total_pago = agg[0]["pago"] if agg else 0.0
    return {
        "emitidas": emitidas,
        "aguardando_pagamento": aguardando,
        "vencidas": vencidas,
        "total_a_receber": round(total_ar - total_pago, 2),
    }
