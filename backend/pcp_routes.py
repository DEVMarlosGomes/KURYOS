"""
PCP — Programação e Controle da Produção.
Fluxo:
  1. OP aberta → Criar slot de programação (linha + data + turno)
  2. Slot planejado → em_execucao   (atualiza OP para em_processo)
  3. Slot em_execucao → concluido   (atualiza OP para concluida)
  4. Qualquer ativo → cancelado
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

pcp_router = APIRouter(prefix="/api/pcp")

db = None
get_current_user = None
new_id_func = None
now_iso_func = None


def init_pcp(database, auth_func, id_func, iso_func):
    global db, get_current_user, new_id_func, now_iso_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def _new_id():
    return new_id_func()


def _now():
    return now_iso_func()


SLOT_STATUSES = ["planejado", "em_execucao", "concluido", "cancelado"]
SLOT_TRANSITIONS = {
    "planejado":    ["em_execucao", "cancelado"],
    "em_execucao":  ["concluido", "cancelado"],
    "concluido":    [],
    "cancelado":    [],
}

TURNOS = ["manha", "tarde", "noite", "integral"]
TIPOS_LINHA = ["manipulacao", "embalagem", "rotulagem", "envase", "geral"]


# ===== MODELS =====
class LinhaCreate(BaseModel):
    nome: str
    codigo: str = ""
    tipo: str = "geral"
    capacidade_diaria: float = 0.0
    unidade_capacidade: str = "kg"
    setup_minutos: int = 30
    observacoes: str = ""


class LinhaUpdate(BaseModel):
    nome: Optional[str] = None
    codigo: Optional[str] = None
    tipo: Optional[str] = None
    capacidade_diaria: Optional[float] = None
    unidade_capacidade: Optional[str] = None
    setup_minutos: Optional[int] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None


class SlotCreate(BaseModel):
    op_id: str
    linha_id: str
    data_inicio: str          # YYYY-MM-DD
    data_fim: Optional[str] = None   # YYYY-MM-DD (defaults to data_inicio)
    turno: str = "integral"
    qtd_planejada: float = 0.0
    observacoes: str = ""


class SlotUpdate(BaseModel):
    status: Optional[str] = None
    linha_id: Optional[str] = None
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    turno: Optional[str] = None
    qtd_planejada: Optional[float] = None
    qtd_produzida: Optional[float] = None
    observacoes: Optional[str] = None


# ===== SEQUENCES =====
async def _next_prog_numero(tenant_id: str) -> str:
    count = await db.pcp_programacao.count_documents({"tenant_id": tenant_id})
    return f"PCP-{str(count + 1).zfill(5)}"


# ========== LINHAS ==========
@pcp_router.get("/linhas")
async def list_linhas(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    linhas = await db.pcp_linhas.find(query, {"_id": 0}).sort("nome", 1).to_list(100)
    return linhas


@pcp_router.get("/linhas/{linha_id}")
async def get_linha(linha_id: str, request: Request):
    user = await get_current_user(request)
    linha = await db.pcp_linhas.find_one({"id": linha_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")
    return linha


@pcp_router.post("/linhas")
async def create_linha(data: LinhaCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    if not data.nome.strip():
        raise HTTPException(status_code=400, detail="Nome da linha obrigatório")
    if data.tipo not in TIPOS_LINHA:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Permitidos: {TIPOS_LINHA}")
    now = _now()
    linha = {
        "id": _new_id(),
        "tenant_id": tid,
        "nome": data.nome.strip(),
        "codigo": data.codigo,
        "tipo": data.tipo,
        "capacidade_diaria": data.capacidade_diaria,
        "unidade_capacidade": data.unidade_capacidade,
        "setup_minutos": data.setup_minutos,
        "status": "ativa",
        "observacoes": data.observacoes,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.pcp_linhas.insert_one(linha)
    linha.pop("_id", None)
    logger.info(f"Linha {data.nome} criada por {user['name']}")
    return linha


@pcp_router.put("/linhas/{linha_id}")
async def update_linha(linha_id: str, data: LinhaUpdate, request: Request):
    user = await get_current_user(request)
    linha = await db.pcp_linhas.find_one({"id": linha_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")
    payload = data.model_dump(exclude_unset=True)
    if "tipo" in payload and payload["tipo"] not in TIPOS_LINHA:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Permitidos: {TIPOS_LINHA}")
    updates: Dict[str, Any] = {k: v for k, v in payload.items() if v is not None}
    updates["updated_at"] = _now()
    await db.pcp_linhas.update_one({"id": linha_id}, {"$set": updates})
    return await db.pcp_linhas.find_one({"id": linha_id}, {"_id": 0})


@pcp_router.delete("/linhas/{linha_id}")
async def delete_linha_blocked(linha_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de linhas não é permitida. Inative a linha.")


# ========== PROGRAMAÇÃO (SLOTS) ==========
@pcp_router.get("/programacao")
async def list_programacao(
    request: Request,
    status: Optional[str] = None,
    linha_id: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    q: Optional[str] = None,
):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if linha_id:
        query["linha_id"] = linha_id
    if data_inicio:
        query["data_inicio"] = {"$gte": data_inicio}
    if data_fim:
        existing = query.get("data_inicio", {})
        if isinstance(existing, dict):
            existing["$lte"] = data_fim
            query["data_inicio"] = existing
        else:
            query["data_inicio"] = {"$lte": data_fim}
    if q:
        query["$or"] = [
            {"numero_prog": {"$regex": q, "$options": "i"}},
            {"op_numero": {"$regex": q, "$options": "i"}},
            {"cliente_nome": {"$regex": q, "$options": "i"}},
            {"produto_nome": {"$regex": q, "$options": "i"}},
            {"linha_nome": {"$regex": q, "$options": "i"}},
        ]
    slots = await db.pcp_programacao.find(query, {"_id": 0}).sort("data_inicio", 1).to_list(1000)
    return slots


@pcp_router.get("/programacao/{slot_id}")
async def get_slot(slot_id: str, request: Request):
    user = await get_current_user(request)
    slot = await db.pcp_programacao.find_one({"id": slot_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not slot:
        raise HTTPException(status_code=404, detail="Programação não encontrada")
    return slot


@pcp_router.post("/programacao")
async def create_slot(data: SlotCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    # Validate OP
    op = await db.ops.find_one({"id": data.op_id, "tenant_id": tid}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")

    # Validate linha
    linha = await db.pcp_linhas.find_one({"id": data.linha_id, "tenant_id": tid}, {"_id": 0})
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")
    if linha.get("status") != "ativa":
        raise HTTPException(status_code=400, detail="Linha não está ativa")

    if data.turno not in TURNOS:
        raise HTTPException(status_code=400, detail=f"Turno inválido. Permitidos: {TURNOS}")

    numero_prog = await _next_prog_numero(tid)
    now = _now()

    # Resolve product name from OP items
    produto_nome = ""
    op_items = op.get("items", [])
    if op_items:
        produto_nome = op_items[0].get("item", "") or op_items[0].get("produto", "")

    slot = {
        "id": _new_id(),
        "tenant_id": tid,
        "numero_prog": numero_prog,
        "op_id": data.op_id,
        "op_numero": op.get("numero_op", ""),
        "pedido_id": op.get("pedido_id", ""),
        "pedido_numero": op.get("pedido_numero", ""),
        "cliente_nome": op.get("cliente_nome", ""),
        "produto_nome": produto_nome,
        "sku": op_items[0].get("codigo_kuryos", "") if op_items else "",
        "linha_id": data.linha_id,
        "linha_nome": linha["nome"],
        "linha_tipo": linha.get("tipo", "geral"),
        "data_inicio": data.data_inicio,
        "data_fim": data.data_fim or data.data_inicio,
        "turno": data.turno,
        "qtd_planejada": data.qtd_planejada or (op_items[0].get("qtd_planejada", 0) if op_items else 0),
        "qtd_produzida": 0.0,
        "status": "planejado",
        "historico": [{"de": None, "para": "planejado", "por": user["name"], "em": now}],
        "observacoes": data.observacoes,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.pcp_programacao.insert_one(slot)
    slot.pop("_id", None)

    # Link slot back to OP
    await db.ops.update_one(
        {"id": data.op_id, "tenant_id": tid},
        {"$set": {"pcp_slot_id": slot["id"], "pcp_numero": numero_prog, "updated_at": now}}
    )

    logger.info(f"PCP {numero_prog} criado para OP {op.get('numero_op')} por {user['name']}")
    return slot


@pcp_router.put("/programacao/{slot_id}")
async def update_slot(slot_id: str, data: SlotUpdate, request: Request):
    user = await get_current_user(request)
    slot = await db.pcp_programacao.find_one({"id": slot_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not slot:
        raise HTTPException(status_code=404, detail="Programação não encontrada")

    now = _now()
    updates: Dict[str, Any] = {"updated_at": now}
    historico = list(slot.get("historico", []))
    payload = data.model_dump(exclude_unset=True)

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in SLOT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = SLOT_TRANSITIONS.get(slot["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {slot['status']} → {novo_status} não permitida"
            )
        historico.append({"de": slot["status"], "para": novo_status, "por": user["name"], "em": now})
        updates["status"] = novo_status
        updates["historico"] = historico

        # Sync OP status
        tid = user["tenant_id"]
        if novo_status == "em_execucao":
            await db.ops.update_one(
                {"id": slot["op_id"], "tenant_id": tid},
                {"$set": {"status": "em_processo", "updated_at": now}}
            )
        elif novo_status == "concluido":
            await db.ops.update_one(
                {"id": slot["op_id"], "tenant_id": tid},
                {"$set": {"status": "concluida", "updated_at": now}}
            )

    if "linha_id" in payload and payload["linha_id"]:
        linha = await db.pcp_linhas.find_one(
            {"id": payload["linha_id"], "tenant_id": user["tenant_id"]}, {"_id": 0}
        )
        if linha:
            updates["linha_id"] = payload["linha_id"]
            updates["linha_nome"] = linha["nome"]
            updates["linha_tipo"] = linha.get("tipo", "geral")

    for field in ("data_inicio", "data_fim", "turno", "qtd_planejada", "qtd_produzida", "observacoes"):
        if field in payload and payload[field] is not None:
            if field == "turno" and payload[field] not in TURNOS:
                raise HTTPException(status_code=400, detail=f"Turno inválido: {payload[field]}")
            updates[field] = payload[field]

    await db.pcp_programacao.update_one({"id": slot_id}, {"$set": updates})
    return await db.pcp_programacao.find_one({"id": slot_id}, {"_id": 0})


@pcp_router.delete("/programacao/{slot_id}")
async def delete_blocked(slot_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de programações não é permitida. Cancele o slot.")


# ========== DASHBOARD ==========
@pcp_router.get("/dashboard")
async def pcp_dashboard(request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    linhas_ativas = await db.pcp_linhas.count_documents({"tenant_id": tid, "status": "ativa"})
    planejados = await db.pcp_programacao.count_documents({"tenant_id": tid, "status": "planejado"})
    em_execucao = await db.pcp_programacao.count_documents({"tenant_id": tid, "status": "em_execucao"})
    concluidos_hoje = await db.pcp_programacao.count_documents({
        "tenant_id": tid,
        "status": "concluido",
        "updated_at": {"$gte": _now()[:10]},
    })
    ops_sem_pcp = await db.ops.count_documents({
        "tenant_id": tid,
        "status": "aberta",
        "pcp_slot_id": {"$exists": False},
    })

    return {
        "linhas_ativas": linhas_ativas,
        "planejados": planejados,
        "em_execucao": em_execucao,
        "concluidos_hoje": concluidos_hoje,
        "ops_sem_pcp": ops_sem_pcp,
    }
