"""
Retrabalho — rework de lotes reprovados pelo CQ.
Categorias:
  RT-1: Retrabalho Interno — reprocessamento no próprio lote (lote + sufixo R)
  RT-2: Retrabalho com Substituição — novo lote criado
  RT-3: Devolução ao Fornecedor — exige comprovante de devolução física

Fluxo:
  RNC com decisão "retrabalho" → criar Ordem de Retrabalho (RT) vinculada à RNC
  Produção executa → em_retrabalho → concluido
  Ao concluir, nova RA é criada automaticamente para re-inspeção CQ

Regras de Negócio:
  RN-RT-01: Toda RT exige RNC vinculada (sem RNC = bloqueio)
  RN-RT-02: Métricas por categoria (RT-1, RT-2, RT-3) separadas
  RN-RT-03: Saldo do pedido mostra "X un em retrabalho"
  RN-RT-04: RT-3 exige devolucao_id (comprovante físico) antes de RNC
  RN-RT-05: Custo acumulado por pedido
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

retrabalho_router = APIRouter(prefix="/api/retrabalho")

db = None
get_current_user = None
new_id_func = None
now_iso_func = None


def init_retrabalho(database, auth_func, id_func, iso_func):
    global db, get_current_user, new_id_func, now_iso_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id():
    return new_id_func()


def now_iso():
    return now_iso_func()


RT_STATUSES = ["pendente", "em_retrabalho", "concluido", "reprovado", "cancelado"]
RT_CATEGORIAS = ["RT-1", "RT-2", "RT-3"]

STATUS_TRANSITIONS = {
    "pendente":      ["em_retrabalho", "cancelado"],
    "em_retrabalho": ["concluido", "reprovado", "cancelado"],
    "concluido":     [],
    "reprovado":     [],
    "cancelado":     [],
}


# ===== MODELS =====
class RTCreate(BaseModel):
    categoria: str = "RT-1"              # "RT-1" | "RT-2" | "RT-3"
    rnc_id: str                          # Obrigatório — RN-RT-01
    op_id: Optional[str] = None          # OP original vinculada (PCP)
    lote_id: Optional[str] = None
    lote_numero: Optional[str] = None
    produto_nome: str
    problema_descrito: str
    instrucoes_retrabalho: str = ""
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = None
    data_limite: Optional[str] = None    # YYYY-MM-DD
    custo_estimado: float = 0.0
    devolucao_id: Optional[str] = None   # RT-3: comprovante de devolução física
    observacoes: str = ""


class RTUpdate(BaseModel):
    instrucoes_retrabalho: Optional[str] = None
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = None
    data_limite: Optional[str] = None
    custo_estimado: Optional[float] = None
    observacoes: Optional[str] = None
    status: Optional[str] = None


class RTConcluir(BaseModel):
    observacoes_conclusao: str = ""
    criar_ra: bool = True


# ===== HELPERS =====
async def _next_rt_numero(tenant_id: str) -> str:
    count = await db.retrabalho_ordens.count_documents({"tenant_id": tenant_id})
    return f"RT-{str(count + 1).zfill(5)}"


# ===== ROUTES =====
@retrabalho_router.get("/ordens")
async def list_ordens(
    request: Request,
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    q: Optional[str] = None,
):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if categoria:
        query["categoria"] = categoria
    if q:
        query["$or"] = [
            {"numero_rt": {"$regex": q, "$options": "i"}},
            {"produto_nome": {"$regex": q, "$options": "i"}},
            {"lote_numero": {"$regex": q, "$options": "i"}},
            {"rnc_numero": {"$regex": q, "$options": "i"}},
        ]
    ordens = await db.retrabalho_ordens.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return ordens


@retrabalho_router.get("/ordens/{rt_id}")
async def get_ordem(rt_id: str, request: Request):
    user = await get_current_user(request)
    rt = await db.retrabalho_ordens.find_one({"id": rt_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not rt:
        raise HTTPException(status_code=404, detail="Ordem de Retrabalho não encontrada")
    return rt


@retrabalho_router.post("/ordens")
async def create_ordem(data: RTCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if data.categoria not in RT_CATEGORIAS:
        raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {', '.join(RT_CATEGORIAS)}")
    if not data.produto_nome.strip():
        raise HTTPException(status_code=400, detail="Nome do produto obrigatório")
    if not data.problema_descrito.strip():
        raise HTTPException(status_code=400, detail="Descreva o problema identificado")

    # RN-RT-01: RNC is mandatory for every RT
    rnc = await db.cq_rncs.find_one({"id": data.rnc_id, "tenant_id": tid}, {"_id": 0})
    if not rnc:
        raise HTTPException(
            status_code=400,
            detail="RNC não encontrada. Toda Ordem de Retrabalho exige RNC vinculada (RN-RT-01)"
        )

    # RN-RT-04: RT-3 requires physical return proof before creating the RT
    if data.categoria == "RT-3" and not data.devolucao_id:
        raise HTTPException(
            status_code=400,
            detail="RT-3 (Devolução ao Fornecedor) exige comprovante de devolução física antes de criar a RT (RN-RT-04)"
        )

    # Lote numbering: RT-1 keeps original lote + 'R' suffix
    lote_numero = data.lote_numero
    if data.categoria == "RT-1" and lote_numero and not lote_numero.endswith("R"):
        lote_numero = f"{lote_numero}R"

    # Resolve OP context for saldo tracking (RN-RT-03)
    op_ref = {}
    if data.op_id:
        op = await db.ops.find_one({"id": data.op_id, "tenant_id": tid}, {"_id": 0})
        if op:
            op_ref = {
                "op_numero": op.get("numero_op", ""),
                "pedido_id": op.get("pedido_id", ""),
                "pedido_numero": op.get("pedido_numero", ""),
            }

    numero_rt = await _next_rt_numero(tid)
    now = now_iso()
    rt_id = new_id()

    rt = {
        "id": rt_id,
        "tenant_id": tid,
        "numero_rt": numero_rt,
        "categoria": data.categoria,
        "rnc_id": data.rnc_id,
        "rnc_numero": rnc.get("numero_rnc", ""),
        "op_id": data.op_id,
        **op_ref,
        "lote_id": data.lote_id,
        "lote_numero": lote_numero,
        "produto_nome": data.produto_nome.strip(),
        "problema_descrito": data.problema_descrito.strip(),
        "instrucoes_retrabalho": data.instrucoes_retrabalho,
        "responsavel_id": data.responsavel_id or user["id"],
        "responsavel_nome": data.responsavel_nome or user["name"],
        "data_limite": data.data_limite,
        "custo_estimado": data.custo_estimado,
        "devolucao_id": data.devolucao_id,
        "status": "pendente",
        "nova_ra_id": None,
        "nova_ra_numero": None,
        "observacoes": data.observacoes,
        "historico": [{"de": None, "para": "pendente", "por": user["name"], "em": now}],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.retrabalho_ordens.insert_one(rt)
    rt.pop("_id", None)
    logger.info(f"RT {numero_rt} ({data.categoria}) criada por {user['name']} — RNC: {rnc.get('numero_rnc', '')}")
    return rt


@retrabalho_router.put("/ordens/{rt_id}")
async def update_ordem(rt_id: str, data: RTUpdate, request: Request):
    user = await get_current_user(request)
    rt = await db.retrabalho_ordens.find_one({"id": rt_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not rt:
        raise HTTPException(status_code=404, detail="RT não encontrada")

    now = now_iso()
    updates: Dict[str, Any] = {"updated_at": now}
    historico = list(rt.get("historico", []))

    payload = data.model_dump(exclude_unset=True)

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in RT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = STATUS_TRANSITIONS.get(rt["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {rt['status']} → {novo_status} não permitida"
            )
        historico.append({"de": rt["status"], "para": novo_status, "por": user["name"], "em": now})
        updates["status"] = novo_status
        updates["historico"] = historico

    for field in ("instrucoes_retrabalho", "responsavel_id", "responsavel_nome",
                  "data_limite", "custo_estimado", "observacoes"):
        if field in payload and payload[field] is not None:
            updates[field] = payload[field]

    await db.retrabalho_ordens.update_one({"id": rt_id}, {"$set": updates})
    return await db.retrabalho_ordens.find_one({"id": rt_id}, {"_id": 0})


@retrabalho_router.post("/ordens/{rt_id}/concluir")
async def concluir_ordem(rt_id: str, data: RTConcluir, request: Request):
    """Marca RT como concluída e cria nova RA para re-inspeção CQ."""
    user = await get_current_user(request)
    tid = user["tenant_id"]
    rt = await db.retrabalho_ordens.find_one({"id": rt_id, "tenant_id": tid}, {"_id": 0})
    if not rt:
        raise HTTPException(status_code=404, detail="RT não encontrada")
    if rt["status"] not in ("pendente", "em_retrabalho"):
        raise HTTPException(status_code=422, detail=f"RT já está em status '{rt['status']}'")

    now = now_iso()
    historico = list(rt.get("historico", []))
    historico.append({"de": rt["status"], "para": "concluido", "por": user["name"], "em": now})

    nova_ra_id = None
    nova_ra_numero = None

    if data.criar_ra:
        count = await db.cq_registros_analise.count_documents({"tenant_id": tid})
        nova_ra_numero = f"RA-{str(count + 1).zfill(5)}"
        nova_ra_id = new_id()
        nova_ra = {
            "id": nova_ra_id,
            "tenant_id": tid,
            "numero_ra": nova_ra_numero,
            "lote_id": rt.get("lote_id") or new_id(),
            "lote_numero": rt.get("lote_numero", ""),
            "tipo": "reinspecao_retrabalho",
            "status": "rascunho",
            "origem_rt_id": rt_id,
            "origem_rt_numero": rt.get("numero_rt", ""),
            "categoria_rt": rt.get("categoria", ""),
            "produto_nome": rt.get("produto_nome", ""),
            "parametros": [],
            "created_by": user["id"],
            "created_by_name": user["name"],
            "created_at": now,
            "updated_at": now,
        }
        await db.cq_registros_analise.insert_one(nova_ra)
        logger.info(f"Nova RA {nova_ra_numero} criada para re-inspeção RT {rt['numero_rt']}")

    updates = {
        "status": "concluido",
        "historico": historico,
        "nova_ra_id": nova_ra_id,
        "nova_ra_numero": nova_ra_numero,
        "observacoes_conclusao": data.observacoes_conclusao,
        "updated_at": now,
    }
    await db.retrabalho_ordens.update_one({"id": rt_id}, {"$set": updates})
    return await db.retrabalho_ordens.find_one({"id": rt_id}, {"_id": 0})


@retrabalho_router.delete("/ordens/{rt_id}")
async def delete_blocked(rt_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de Ordens de Retrabalho não é permitida. Cancele a ordem.")


@retrabalho_router.get("/metricas")
async def retrabalho_metricas(request: Request):
    """RN-RT-02: Métricas separadas por categoria RT-1/RT-2/RT-3."""
    user = await get_current_user(request)
    tid = user["tenant_id"]

    result = {}
    for cat in RT_CATEGORIAS:
        agg = await db.retrabalho_ordens.aggregate([
            {"$match": {"tenant_id": tid, "categoria": cat}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "custo": {"$sum": "$custo_estimado"},
            }},
        ]).to_list(20)

        status_counts = {a["_id"]: a["count"] for a in agg}
        custo_total = sum(a["custo"] for a in agg)
        result[cat] = {
            "total": sum(a["count"] for a in agg),
            "em_aberto": status_counts.get("pendente", 0) + status_counts.get("em_retrabalho", 0),
            "pendente": status_counts.get("pendente", 0),
            "em_retrabalho": status_counts.get("em_retrabalho", 0),
            "concluido": status_counts.get("concluido", 0),
            "reprovado": status_counts.get("reprovado", 0),
            "custo_total": round(custo_total, 2),
        }
    return result


@retrabalho_router.get("/dashboard")
async def retrabalho_dashboard(request: Request):
    """Summary counts for CQ Dashboard integration."""
    user = await get_current_user(request)
    tid = user["tenant_id"]
    pendente = await db.retrabalho_ordens.count_documents({"tenant_id": tid, "status": "pendente"})
    em_retrabalho = await db.retrabalho_ordens.count_documents({"tenant_id": tid, "status": "em_retrabalho"})
    concluido = await db.retrabalho_ordens.count_documents({"tenant_id": tid, "status": "concluido"})
    reprovado = await db.retrabalho_ordens.count_documents({"tenant_id": tid, "status": "reprovado"})

    agg = await db.retrabalho_ordens.aggregate([
        {"$match": {"tenant_id": tid}},
        {"$group": {"_id": None, "custo_total": {"$sum": "$custo_estimado"}}},
    ]).to_list(1)
    custo_total = round(agg[0]["custo_total"] if agg else 0.0, 2)

    return {
        "pendente": pendente,
        "em_retrabalho": em_retrabalho,
        "aguardando_cq": concluido,
        "reprovado": reprovado,
        "total_ativos": pendente + em_retrabalho,
        "custo_total": custo_total,
    }
