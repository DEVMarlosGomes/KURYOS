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
from datetime import datetime, date
import logging
from workflow_engine import next_lote_per_day, format_lote_numero

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
TIPOS_SLOT = ["producao", "setup", "almoco"]
TIPOS_SETUP = ["assepsia", "troca_volume", "troca_maquina", "geral"]
LOTE_STATUSES = ["planejado", "em_preparo", "em_envase", "concluido", "cancelado"]
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def _week_key(data_iso: str) -> str:
    """Return ISO week string YYYY-WW for a given date."""
    d = datetime.fromisoformat(data_iso[:10])
    iso = d.isocalendar()
    return f"{iso[0]}-{str(iso[1]).zfill(2)}"


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
    op_id: str = ""
    linha_id: str
    # Hour-by-hour fields (spec 3.4 / 4)
    data: Optional[str] = None          # YYYY-MM-DD single day
    hora_inicio: Optional[str] = None   # "HH:MM"
    hora_fim: Optional[str] = None      # "HH:MM"
    # Slot type
    tipo: str = "producao"              # producao | setup | almoco
    setup_tempo_min: Optional[int] = None
    setup_tipo: str = "assepsia"
    # Lote link
    lote_id: Optional[str] = None
    # Legacy date range (kept for compat)
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    turno: str = "integral"
    qtd_planejada: float = 0.0
    observacoes: str = ""


class SlotUpdate(BaseModel):
    status: Optional[str] = None
    linha_id: Optional[str] = None
    data: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fim: Optional[str] = None
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    turno: Optional[str] = None
    tipo: Optional[str] = None
    setup_tempo_min: Optional[int] = None
    lote_id: Optional[str] = None
    qtd_planejada: Optional[float] = None
    qtd_produzida: Optional[float] = None
    observacoes: Optional[str] = None


class LoteCreate(BaseModel):
    op_id: str
    data_manipulacao: str       # YYYY-MM-DD
    data_envase: Optional[str] = None
    qtd_planejada: int = 0
    observacoes: str = ""


class LoteUpdate(BaseModel):
    data_manipulacao: Optional[str] = None
    data_envase: Optional[str] = None
    qtd_planejada: Optional[int] = None
    observacoes: Optional[str] = None
    status: Optional[str] = None


class CalendarioDiaConfig(BaseModel):
    habilitado: bool = True
    hora_inicio: str = "07:00"
    hora_fim: str = "18:00"
    pausa_almoco: bool = True
    almoco_inicio: str = "12:00"
    almoco_fim: str = "13:00"
    horas_extras: int = 0


class CalendarioCreate(BaseModel):
    semana: str        # YYYY-WW
    linha_id: str
    seg: Optional[CalendarioDiaConfig] = None
    ter: Optional[CalendarioDiaConfig] = None
    qua: Optional[CalendarioDiaConfig] = None
    qui: Optional[CalendarioDiaConfig] = None
    sex: Optional[CalendarioDiaConfig] = None
    sab: Optional[CalendarioDiaConfig] = None
    dom: Optional[CalendarioDiaConfig] = None


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

    # Validate OP (required for producao slots only)
    op = None
    if data.op_id:
        op = await db.ops.find_one({"id": data.op_id, "tenant_id": tid}, {"_id": 0})
        if not op:
            raise HTTPException(status_code=404, detail="OP não encontrada")
    elif data.tipo == "producao":
        raise HTTPException(status_code=400, detail="op_id obrigatório para slots de produção")

    # Validate linha
    linha = await db.pcp_linhas.find_one({"id": data.linha_id, "tenant_id": tid}, {"_id": 0})
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")
    if linha.get("status") != "ativa":
        raise HTTPException(status_code=400, detail="Linha não está ativa")

    if data.turno not in TURNOS:
        raise HTTPException(status_code=400, detail=f"Turno inválido. Permitidos: {TURNOS}")
    if data.tipo not in TIPOS_SLOT:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Permitidos: {TIPOS_SLOT}")

    # Resolve anchor date for calendar check
    anchor_date = data.data or data.data_inicio
    if not anchor_date:
        raise HTTPException(status_code=400, detail="data ou data_inicio obrigatório")

    # RN-PCP-03: calendar must be configured for this week before scheduling
    semana = _week_key(anchor_date)
    calendar_exists = await db.pcp_calendario.find_one(
        {"tenant_id": tid, "semana": semana, "linha_id": data.linha_id}, {"_id": 0}
    )
    if not calendar_exists:
        raise HTTPException(
            status_code=422,
            detail=f"Calendário não configurado para a semana {semana} na linha '{linha['nome']}' (RN-PCP-03). Configure o calendário antes de programar."
        )

    numero_prog = await _next_prog_numero(tid)
    now = _now()

    # Resolve product/order info from OP (may be None for setup/almoco slots)
    op_items = op.get("items", []) if op else []
    produto_nome = ""
    if op_items:
        produto_nome = op_items[0].get("item", "") or op_items[0].get("produto", "")

    # Normalize hora fields
    hora_inicio = data.hora_inicio or calendar_exists.get("seg", {}).get("hora_inicio", "07:00") if calendar_exists else "07:00"
    hora_fim = data.hora_fim or calendar_exists.get("seg", {}).get("hora_fim", "18:00") if calendar_exists else "18:00"

    slot = {
        "id": _new_id(),
        "tenant_id": tid,
        "numero_prog": numero_prog,
        "op_id": data.op_id,
        "op_numero": op.get("numero_op", "") if op else "",
        "pedido_id": op.get("pedido_id", "") if op else "",
        "pedido_numero": op.get("pedido_numero", "") if op else "",
        "cliente_nome": op.get("cliente_nome", "") if op else "",
        "produto_nome": produto_nome,
        "sku": op_items[0].get("codigo_kuryos", "") if op_items else "",
        "linha_id": data.linha_id,
        "linha_nome": linha["nome"],
        "linha_tipo": linha.get("tipo", "geral"),
        # Hour-by-hour fields
        "data": data.data or data.data_inicio,
        "hora_inicio": hora_inicio,
        "hora_fim": hora_fim,
        "tipo": data.tipo,
        "setup_tempo_min": data.setup_tempo_min,
        "setup_tipo": data.setup_tipo if data.tipo == "setup" else None,
        "lote_id": data.lote_id,
        # Legacy
        "data_inicio": data.data_inicio or data.data,
        "data_fim": data.data_fim or data.data or data.data_inicio,
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

    lotes_ativos = await db.pcp_lotes.count_documents({"tenant_id": tid, "status": {"$in": ["planejado", "em_preparo", "em_envase"]}})
    semana_atual = _week_key(_now()[:10])
    calendarios_semana = await db.pcp_calendario.count_documents({"tenant_id": tid, "semana": semana_atual})

    return {
        "linhas_ativas": linhas_ativas,
        "planejados": planejados,
        "em_execucao": em_execucao,
        "concluidos_hoje": concluidos_hoje,
        "ops_sem_pcp": ops_sem_pcp,
        "lotes_ativos": lotes_ativos,
        "calendarios_semana_atual": calendarios_semana,
    }


# ========== LOTES ==========
@pcp_router.get("/lotes")
async def list_lotes(
    request: Request,
    status: Optional[str] = None,
    op_id: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if op_id:
        query["op_id"] = op_id
    if data_inicio:
        query["data_manipulacao"] = {"$gte": data_inicio}
    if data_fim:
        existing = query.get("data_manipulacao", {})
        if isinstance(existing, dict):
            existing["$lte"] = data_fim
        else:
            query["data_manipulacao"] = {"$lte": data_fim}
    lotes = await db.pcp_lotes.find(query, {"_id": 0}).sort("data_manipulacao", -1).to_list(500)
    return lotes


@pcp_router.post("/lotes")
async def create_lote(data: LoteCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    # Validate OP
    op = await db.ops.find_one({"id": data.op_id, "tenant_id": tid}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")

    # RN-PCP-01: insumos must be checked before creating lote
    op_items = op.get("items", [])
    checklist = op.get("checklist_insumos", {})
    insumos_pendentes = []
    for item in op_items:
        cat = item.get("categoria", "")
        entry = checklist.get(cat, {})
        if entry.get("aplica", False) and entry.get("status") not in ("disponivel", "ok"):
            insumos_pendentes.append(cat)
    if insumos_pendentes:
        raise HTTPException(
            status_code=422,
            detail=f"Insumos pendentes de confirmação (RN-PCP-01): {', '.join(insumos_pendentes)}. Verifique o checklist antes de criar o lote."
        )

    # RN-PCP-02: auto-number lote
    seq = await next_lote_per_day(tid, data.data_manipulacao)
    numero_lote = format_lote_numero(data.data_manipulacao, seq)

    now = _now()
    op_items = op.get("items", [])
    produto_nome = op_items[0].get("item", "") if op_items else ""

    lote = {
        "id": _new_id(),
        "tenant_id": tid,
        "numero_lote": numero_lote,
        "op_id": data.op_id,
        "op_numero": op.get("numero_op", ""),
        "pedido_id": op.get("pedido_id", ""),
        "pedido_numero": op.get("pedido_numero", ""),
        "cliente_nome": op.get("cliente_nome", ""),
        "produto_nome": produto_nome,
        "sku": op_items[0].get("codigo_kuryos", "") if op_items else "",
        "data_manipulacao": data.data_manipulacao,
        "data_envase": data.data_envase,
        "qtd_planejada": data.qtd_planejada or (op_items[0].get("qtd_planejada", 0) if op_items else 0),
        "qtd_produzida": 0,
        "status": "planejado",
        "historico": [{"de": None, "para": "planejado", "por": user["name"], "em": now}],
        "observacoes": data.observacoes,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.pcp_lotes.insert_one(lote)
    lote.pop("_id", None)

    # Link lote to OP
    await db.ops.update_one(
        {"id": data.op_id, "tenant_id": tid},
        {"$push": {"lote_ids": lote["id"]}, "$set": {"updated_at": now}}
    )

    logger.info(f"Lote {numero_lote} criado para OP {op.get('numero_op')} por {user['name']}")
    return lote


@pcp_router.get("/lotes/{lote_id}")
async def get_lote(lote_id: str, request: Request):
    user = await get_current_user(request)
    lote = await db.pcp_lotes.find_one({"id": lote_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    return lote


@pcp_router.put("/lotes/{lote_id}")
async def update_lote(lote_id: str, data: LoteUpdate, request: Request):
    user = await get_current_user(request)
    lote = await db.pcp_lotes.find_one({"id": lote_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    LOTE_TRANSITIONS = {
        "planejado":    ["em_preparo", "cancelado"],
        "em_preparo":   ["em_envase", "cancelado"],
        "em_envase":    ["concluido", "cancelado"],
        "concluido":    [],
        "cancelado":    [],
    }

    now = _now()
    payload = data.model_dump(exclude_unset=True)
    updates: Dict[str, Any] = {"updated_at": now}
    historico = list(lote.get("historico", []))

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in LOTE_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = LOTE_TRANSITIONS.get(lote["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {lote['status']} → {novo_status} não permitida"
            )
        historico.append({"de": lote["status"], "para": novo_status, "por": user["name"], "em": now})
        updates["status"] = novo_status
        updates["historico"] = historico

    for field in ("data_manipulacao", "data_envase", "qtd_planejada", "observacoes"):
        if field in payload and payload[field] is not None:
            updates[field] = payload[field]

    await db.pcp_lotes.update_one({"id": lote_id}, {"$set": updates})
    return await db.pcp_lotes.find_one({"id": lote_id}, {"_id": 0})


@pcp_router.delete("/lotes/{lote_id}")
async def delete_lote_blocked(lote_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de lotes não é permitida. Cancele o lote.")


# ========== CALENDÁRIO ==========
@pcp_router.get("/calendario")
async def list_calendario(
    request: Request,
    semana: Optional[str] = None,
    linha_id: Optional[str] = None,
):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if semana:
        query["semana"] = semana
    if linha_id:
        query["linha_id"] = linha_id
    calendarios = await db.pcp_calendario.find(query, {"_id": 0}).sort("semana", -1).to_list(200)
    return calendarios


@pcp_router.post("/calendario")
async def create_calendario(data: CalendarioCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    # Validate semana format YYYY-WW
    if not data.semana or len(data.semana) != 7 or data.semana[4] != "-":
        raise HTTPException(status_code=400, detail="Formato de semana inválido. Use YYYY-WW (ex: 2026-24)")

    # Validate linha
    linha = await db.pcp_linhas.find_one({"id": data.linha_id, "tenant_id": tid}, {"_id": 0})
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")

    # Upsert: one calendario per (tenant, semana, linha)
    existing = await db.pcp_calendario.find_one(
        {"tenant_id": tid, "semana": data.semana, "linha_id": data.linha_id}, {"_id": 0}
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Calendário já existe para a semana {data.semana} / linha {linha['nome']}. Use PUT para atualizar."
        )

    now = _now()
    default_dia = CalendarioDiaConfig()

    cal = {
        "id": _new_id(),
        "tenant_id": tid,
        "semana": data.semana,
        "linha_id": data.linha_id,
        "linha_nome": linha["nome"],
        "seg": (data.seg or default_dia).model_dump(),
        "ter": (data.ter or default_dia).model_dump(),
        "qua": (data.qua or default_dia).model_dump(),
        "qui": (data.qui or default_dia).model_dump(),
        "sex": (data.sex or default_dia).model_dump(),
        "sab": (data.sab or CalendarioDiaConfig(habilitado=False)).model_dump(),
        "dom": (data.dom or CalendarioDiaConfig(habilitado=False)).model_dump(),
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.pcp_calendario.insert_one(cal)
    cal.pop("_id", None)
    logger.info(f"Calendário {data.semana}/{data.linha_id} criado por {user['name']}")
    return cal


@pcp_router.get("/calendario/{semana}/{linha_id}")
async def get_calendario(semana: str, linha_id: str, request: Request):
    user = await get_current_user(request)
    cal = await db.pcp_calendario.find_one(
        {"tenant_id": user["tenant_id"], "semana": semana, "linha_id": linha_id}, {"_id": 0}
    )
    if not cal:
        raise HTTPException(status_code=404, detail="Calendário não encontrado para esta semana/linha")
    return cal


@pcp_router.put("/calendario/{semana}/{linha_id}")
async def update_calendario(semana: str, linha_id: str, data: CalendarioCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    cal = await db.pcp_calendario.find_one(
        {"tenant_id": tid, "semana": semana, "linha_id": linha_id}, {"_id": 0}
    )
    if not cal:
        raise HTTPException(status_code=404, detail="Calendário não encontrado. Use POST para criar.")

    payload = data.model_dump(exclude_unset=True)
    updates: Dict[str, Any] = {"updated_at": _now()}
    for dia in DIAS_SEMANA:
        if dia in payload and payload[dia] is not None:
            updates[dia] = payload[dia]

    await db.pcp_calendario.update_one(
        {"tenant_id": tid, "semana": semana, "linha_id": linha_id}, {"$set": updates}
    )
    return await db.pcp_calendario.find_one(
        {"tenant_id": tid, "semana": semana, "linha_id": linha_id}, {"_id": 0}
    )


# ========== SETUP SUGESTÃO ==========
@pcp_router.get("/setup-sugestao")
async def setup_sugestao(
    request: Request,
    linha_id: str,
    data: str,
    hora: str,
):
    """Return suggested setup block between two different products (RN-PCP-10)."""
    user = await get_current_user(request)
    tid = user["tenant_id"]

    linha = await db.pcp_linhas.find_one({"id": linha_id, "tenant_id": tid}, {"_id": 0})
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")

    # Find previous slot on same line+day to determine if setup is needed
    slots_do_dia = await db.pcp_programacao.find(
        {"tenant_id": tid, "linha_id": linha_id, "data": data, "tipo": "producao", "status": {"$nin": ["cancelado"]}},
        {"_id": 0}
    ).sort("hora_inicio", -1).to_list(50)

    setup_minutos = linha.get("setup_minutos", 30)
    anterior = None
    for s in slots_do_dia:
        if s.get("hora_fim", "") <= hora:
            anterior = s
            break

    return {
        "linha_id": linha_id,
        "linha_nome": linha["nome"],
        "data": data,
        "hora_referencia": hora,
        "slot_anterior": anterior,
        "setup_sugerido": {
            "tipo": "setup",
            "setup_tipo": "assepsia",
            "setup_tempo_min": setup_minutos,
            "hora_inicio": hora,
            "hora_fim": _add_minutes_to_hora(hora, setup_minutos),
        } if anterior else None,
        "setup_necessario": anterior is not None,
        "motivo": f"Produto anterior: {anterior['produto_nome']} (RN-PCP-10)" if anterior else "Nenhum slot anterior — setup opcional",
    }


def _add_minutes_to_hora(hora: str, minutos: int) -> str:
    h, m = map(int, hora.split(":"))
    total = h * 60 + m + minutos
    return f"{total // 60:02d}:{total % 60:02d}"
