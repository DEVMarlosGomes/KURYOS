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

import database as pg_db

logger = logging.getLogger(__name__)

pcp_router = APIRouter(prefix="/api/pcp")

get_current_user = None
new_id_func = None
now_iso_func = None


def init_pcp(database, auth_func, id_func, iso_func):
    global get_current_user, new_id_func, now_iso_func
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def _new_id():
    return new_id_func()


def _now():
    return now_iso_func()


def _row(r):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} if r else None


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
    data: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fim: Optional[str] = None
    tipo: str = "producao"
    setup_tempo_min: Optional[int] = None
    setup_tipo: str = "assepsia"
    lote_id: Optional[str] = None
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
    data_manipulacao: str
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
    semana: str
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
    count = await pg_db.fetch_val("SELECT COUNT(*) FROM pcp_programacao WHERE tenant_id=$1", tenant_id)
    return f"PCP-{str(count + 1).zfill(5)}"


# ========== LINHAS ==========
@pcp_router.get("/linhas")
async def list_linhas(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    clauses = ["tenant_id=$1"]
    vals = [user["tenant_id"]]
    i = 2
    if status:
        clauses.append(f"status=${i}"); vals.append(status); i += 1
    rows = await pg_db.fetch_all(
        f"SELECT * FROM pcp_linhas WHERE {' AND '.join(clauses)} ORDER BY nome", *vals
    )
    return [_row(r) for r in rows]


@pcp_router.get("/linhas/{linha_id}")
async def get_linha(linha_id: str, request: Request):
    user = await get_current_user(request)
    linha = _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_linhas WHERE id=$1 AND tenant_id=$2", linha_id, user["tenant_id"]
    ))
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
    linha_id = _new_id()
    await pg_db.execute(
        """INSERT INTO pcp_linhas
           (id, tenant_id, nome, codigo, tipo, capacidade_diaria, unidade_capacidade,
            setup_minutos, status, observacoes, created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
        linha_id, tid, data.nome.strip(), data.codigo, data.tipo, data.capacidade_diaria,
        data.unidade_capacidade, data.setup_minutos, "ativa", data.observacoes,
        user["id"], user["name"], now, now,
    )
    logger.info(f"Linha {data.nome} criada por {user['name']}")
    return _row(await pg_db.fetch_one("SELECT * FROM pcp_linhas WHERE id=$1", linha_id))


@pcp_router.put("/linhas/{linha_id}")
async def update_linha(linha_id: str, data: LinhaUpdate, request: Request):
    user = await get_current_user(request)
    linha = _row(await pg_db.fetch_one(
        "SELECT id, status FROM pcp_linhas WHERE id=$1 AND tenant_id=$2", linha_id, user["tenant_id"]
    ))
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")
    payload = data.model_dump(exclude_unset=True)
    if "tipo" in payload and payload["tipo"] not in TIPOS_LINHA:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Permitidos: {TIPOS_LINHA}")
    updates: Dict[str, Any] = {k: v for k, v in payload.items() if v is not None}
    updates["updated_at"] = _now()

    set_clauses = []
    vals = []
    i = 1
    for k, v in updates.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1

    await pg_db.execute(
        f"UPDATE pcp_linhas SET {', '.join(set_clauses)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, linha_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM pcp_linhas WHERE id=$1", linha_id))


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
    clauses = ["tenant_id=$1"]
    vals = [user["tenant_id"]]
    i = 2
    if status:
        clauses.append(f"status=${i}"); vals.append(status); i += 1
    if linha_id:
        clauses.append(f"linha_id=${i}"); vals.append(linha_id); i += 1
    if data_inicio:
        clauses.append(f"data_inicio >= ${i}"); vals.append(data_inicio); i += 1
    if data_fim:
        clauses.append(f"data_inicio <= ${i}"); vals.append(data_fim); i += 1
    if q:
        clauses.append(
            f"(numero_prog ILIKE ${i} OR op_numero ILIKE ${i} OR cliente_nome ILIKE ${i} OR produto_nome ILIKE ${i} OR linha_nome ILIKE ${i})"
        )
        vals.append(f"%{q}%"); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM pcp_programacao WHERE {' AND '.join(clauses)} ORDER BY data_inicio",
        *vals,
    )
    return [_row(r) for r in rows]


@pcp_router.get("/programacao/{slot_id}")
async def get_slot(slot_id: str, request: Request):
    user = await get_current_user(request)
    slot = _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_programacao WHERE id=$1 AND tenant_id=$2", slot_id, user["tenant_id"]
    ))
    if not slot:
        raise HTTPException(status_code=404, detail="Programação não encontrada")
    return slot


@pcp_router.post("/programacao")
async def create_slot(data: SlotCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    op = None
    if data.op_id:
        op = _row(await pg_db.fetch_one(
            "SELECT id, numero_op, pedido_id, pedido_numero, cliente_nome, items FROM ops WHERE id=$1 AND tenant_id=$2",
            data.op_id, tid,
        ))
        if not op:
            raise HTTPException(status_code=404, detail="OP não encontrada")
    elif data.tipo == "producao":
        raise HTTPException(status_code=400, detail="op_id obrigatório para slots de produção")

    linha = _row(await pg_db.fetch_one(
        "SELECT id, nome, tipo, setup_minutos, status FROM pcp_linhas WHERE id=$1 AND tenant_id=$2",
        data.linha_id, tid,
    ))
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")
    if linha.get("status") != "ativa":
        raise HTTPException(status_code=400, detail="Linha não está ativa")

    if data.turno not in TURNOS:
        raise HTTPException(status_code=400, detail=f"Turno inválido. Permitidos: {TURNOS}")
    if data.tipo not in TIPOS_SLOT:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Permitidos: {TIPOS_SLOT}")

    anchor_date = data.data or data.data_inicio
    if not anchor_date:
        raise HTTPException(status_code=400, detail="data ou data_inicio obrigatório")

    semana = _week_key(anchor_date)
    calendar_exists = _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_calendario WHERE tenant_id=$1 AND semana=$2 AND linha_id=$3",
        tid, semana, data.linha_id,
    ))
    if not calendar_exists:
        raise HTTPException(
            status_code=422,
            detail=f"Calendário não configurado para a semana {semana} na linha '{linha['nome']}' (RN-PCP-03). Configure o calendário antes de programar.",
        )

    numero_prog = await _next_prog_numero(tid)
    now = _now()

    op_items = (op.get("items") or []) if op else []
    produto_nome = ""
    if op_items:
        produto_nome = op_items[0].get("item", "") or op_items[0].get("produto", "")

    seg_cal = calendar_exists.get("seg") or {}
    hora_inicio = data.hora_inicio or seg_cal.get("hora_inicio", "07:00")
    hora_fim = data.hora_fim or seg_cal.get("hora_fim", "18:00")

    slot_id = _new_id()
    historico = [{"de": None, "para": "planejado", "por": user["name"], "em": now}]

    await pg_db.execute(
        """INSERT INTO pcp_programacao
           (id, tenant_id, numero_prog, op_id, op_numero, pedido_id, pedido_numero,
            cliente_nome, produto_nome, sku, linha_id, linha_nome, linha_tipo,
            data, hora_inicio, hora_fim, tipo, setup_tempo_min, setup_tipo, lote_id,
            data_inicio, data_fim, turno, qtd_planejada, qtd_produzida,
            status, historico, observacoes, created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                   $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32)""",
        slot_id, tid, numero_prog,
        data.op_id, op.get("numero_op", "") if op else "",
        op.get("pedido_id", "") if op else "", op.get("pedido_numero", "") if op else "",
        op.get("cliente_nome", "") if op else "", produto_nome,
        op_items[0].get("codigo_kuryos", "") if op_items else "",
        data.linha_id, linha["nome"], linha.get("tipo", "geral"),
        data.data or data.data_inicio, hora_inicio, hora_fim,
        data.tipo, data.setup_tempo_min,
        data.setup_tipo if data.tipo == "setup" else None,
        data.lote_id,
        data.data_inicio or data.data,
        data.data_fim or data.data or data.data_inicio,
        data.turno,
        data.qtd_planejada or (op_items[0].get("qtd_planejada", 0) if op_items else 0),
        0.0, "planejado", historico, data.observacoes,
        user["id"], user["name"], now, now,
    )

    if data.op_id:
        await pg_db.execute(
            "UPDATE ops SET pcp_slot_id=$1, pcp_numero=$2, updated_at=$3 WHERE id=$4 AND tenant_id=$5",
            slot_id, numero_prog, now, data.op_id, tid,
        )

    logger.info(f"PCP {numero_prog} criado para OP {op.get('numero_op') if op else '-'} por {user['name']}")
    return _row(await pg_db.fetch_one("SELECT * FROM pcp_programacao WHERE id=$1", slot_id))


@pcp_router.put("/programacao/{slot_id}")
async def update_slot(slot_id: str, data: SlotUpdate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    slot = _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_programacao WHERE id=$1 AND tenant_id=$2", slot_id, tid
    ))
    if not slot:
        raise HTTPException(status_code=404, detail="Programação não encontrada")

    now = _now()
    updates: Dict[str, Any] = {"updated_at": now}
    historico = list(slot.get("historico") or [])
    payload = data.model_dump(exclude_unset=True)

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in SLOT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = SLOT_TRANSITIONS.get(slot["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {slot['status']} → {novo_status} não permitida",
            )
        historico.append({"de": slot["status"], "para": novo_status, "por": user["name"], "em": now})
        updates["status"] = novo_status
        updates["historico"] = historico

        if novo_status == "em_execucao" and slot.get("op_id"):
            await pg_db.execute(
                "UPDATE ops SET status='em_processo', updated_at=$1 WHERE id=$2 AND tenant_id=$3",
                now, slot["op_id"], tid,
            )
        elif novo_status == "concluido" and slot.get("op_id"):
            await pg_db.execute(
                "UPDATE ops SET status='concluida', updated_at=$1 WHERE id=$2 AND tenant_id=$3",
                now, slot["op_id"], tid,
            )

    if "linha_id" in payload and payload["linha_id"]:
        linha = _row(await pg_db.fetch_one(
            "SELECT id, nome, tipo FROM pcp_linhas WHERE id=$1 AND tenant_id=$2",
            payload["linha_id"], tid,
        ))
        if linha:
            updates["linha_id"] = payload["linha_id"]
            updates["linha_nome"] = linha["nome"]
            updates["linha_tipo"] = linha.get("tipo", "geral")

    for field in ("data_inicio", "data_fim", "turno", "qtd_planejada", "qtd_produzida", "observacoes"):
        if field in payload and payload[field] is not None:
            if field == "turno" and payload[field] not in TURNOS:
                raise HTTPException(status_code=400, detail=f"Turno inválido: {payload[field]}")
            updates[field] = payload[field]

    set_clauses = []
    vals = []
    i = 1
    for k, v in updates.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1

    await pg_db.execute(
        f"UPDATE pcp_programacao SET {', '.join(set_clauses)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, slot_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM pcp_programacao WHERE id=$1", slot_id))


@pcp_router.delete("/programacao/{slot_id}")
async def delete_blocked(slot_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de programações não é permitida. Cancele o slot.")


# ========== DASHBOARD ==========
@pcp_router.get("/dashboard")
async def pcp_dashboard(request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    linhas_ativas = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM pcp_linhas WHERE tenant_id=$1 AND status='ativa'", tid
    )
    prog_row = _row(await pg_db.fetch_one(
        """SELECT
               COUNT(*) FILTER (WHERE status='planejado') AS planejados,
               COUNT(*) FILTER (WHERE status='em_execucao') AS em_execucao,
               COUNT(*) FILTER (WHERE status='concluido' AND updated_at >= CURRENT_DATE::timestamptz) AS concluidos_hoje
           FROM pcp_programacao WHERE tenant_id=$1""",
        tid,
    ))
    ops_sem_pcp = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM ops WHERE tenant_id=$1 AND status='aberta' AND pcp_slot_id IS NULL", tid
    )
    lotes_ativos = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM pcp_lotes WHERE tenant_id=$1 AND status IN ('planejado','em_preparo','em_envase')", tid
    )
    semana_atual = _week_key(_now()[:10])
    calendarios_semana = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM pcp_calendario WHERE tenant_id=$1 AND semana=$2", tid, semana_atual
    )

    return {
        "linhas_ativas": linhas_ativas,
        "planejados": prog_row["planejados"],
        "em_execucao": prog_row["em_execucao"],
        "concluidos_hoje": prog_row["concluidos_hoje"],
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
    clauses = ["tenant_id=$1"]
    vals = [user["tenant_id"]]
    i = 2
    if status:
        clauses.append(f"status=${i}"); vals.append(status); i += 1
    if op_id:
        clauses.append(f"op_id=${i}"); vals.append(op_id); i += 1
    if data_inicio:
        clauses.append(f"data_manipulacao >= ${i}"); vals.append(data_inicio); i += 1
    if data_fim:
        clauses.append(f"data_manipulacao <= ${i}"); vals.append(data_fim); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM pcp_lotes WHERE {' AND '.join(clauses)} ORDER BY data_manipulacao DESC",
        *vals,
    )
    return [_row(r) for r in rows]


@pcp_router.post("/lotes")
async def create_lote(data: LoteCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    op = _row(await pg_db.fetch_one(
        "SELECT id, numero_op, pedido_id, pedido_numero, cliente_nome, items, checklist_insumos FROM ops WHERE id=$1 AND tenant_id=$2",
        data.op_id, tid,
    ))
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")

    op_items = op.get("items") or []
    checklist = op.get("checklist_insumos") or {}
    insumos_pendentes = []
    for item in op_items:
        cat = item.get("categoria", "")
        entry = checklist.get(cat, {})
        if entry.get("aplica", False) and entry.get("status") not in ("disponivel", "ok"):
            insumos_pendentes.append(cat)
    if insumos_pendentes:
        raise HTTPException(
            status_code=422,
            detail=f"Insumos pendentes de confirmação (RN-PCP-01): {', '.join(insumos_pendentes)}. Verifique o checklist antes de criar o lote.",
        )

    seq = await next_lote_per_day(tid, data.data_manipulacao)
    numero_lote = format_lote_numero(data.data_manipulacao, seq)

    now = _now()
    produto_nome = op_items[0].get("item", "") if op_items else ""
    lote_id = _new_id()
    historico = [{"de": None, "para": "planejado", "por": user["name"], "em": now}]

    await pg_db.execute(
        """INSERT INTO pcp_lotes
           (id, tenant_id, numero_lote, op_id, op_numero, pedido_id, pedido_numero,
            cliente_nome, produto_nome, sku, data_manipulacao, data_envase,
            qtd_planejada, qtd_produzida, status, historico, observacoes,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)""",
        lote_id, tid, numero_lote,
        data.op_id, op.get("numero_op", ""),
        op.get("pedido_id", ""), op.get("pedido_numero", ""),
        op.get("cliente_nome", ""), produto_nome,
        op_items[0].get("codigo_kuryos", "") if op_items else "",
        data.data_manipulacao, data.data_envase,
        data.qtd_planejada or (op_items[0].get("qtd_planejada", 0) if op_items else 0),
        0, "planejado", historico, data.observacoes,
        user["id"], user["name"], now, now,
    )

    await pg_db.execute(
        "UPDATE ops SET lote_ids = lote_ids || $1::jsonb, updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        [lote_id], now, data.op_id, tid,
    )

    logger.info(f"Lote {numero_lote} criado para OP {op.get('numero_op')} por {user['name']}")
    return _row(await pg_db.fetch_one("SELECT * FROM pcp_lotes WHERE id=$1", lote_id))


@pcp_router.get("/lotes/{lote_id}")
async def get_lote(lote_id: str, request: Request):
    user = await get_current_user(request)
    lote = _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_lotes WHERE id=$1 AND tenant_id=$2", lote_id, user["tenant_id"]
    ))
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    return lote


@pcp_router.put("/lotes/{lote_id}")
async def update_lote(lote_id: str, data: LoteUpdate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    lote = _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_lotes WHERE id=$1 AND tenant_id=$2", lote_id, tid
    ))
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
    historico = list(lote.get("historico") or [])

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in LOTE_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = LOTE_TRANSITIONS.get(lote["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {lote['status']} → {novo_status} não permitida",
            )
        historico.append({"de": lote["status"], "para": novo_status, "por": user["name"], "em": now})
        updates["status"] = novo_status
        updates["historico"] = historico

    for field in ("data_manipulacao", "data_envase", "qtd_planejada", "observacoes"):
        if field in payload and payload[field] is not None:
            updates[field] = payload[field]

    set_clauses = []
    vals = []
    i = 1
    for k, v in updates.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1

    await pg_db.execute(
        f"UPDATE pcp_lotes SET {', '.join(set_clauses)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, lote_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM pcp_lotes WHERE id=$1", lote_id))


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
    clauses = ["tenant_id=$1"]
    vals = [user["tenant_id"]]
    i = 2
    if semana:
        clauses.append(f"semana=${i}"); vals.append(semana); i += 1
    if linha_id:
        clauses.append(f"linha_id=${i}"); vals.append(linha_id); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM pcp_calendario WHERE {' AND '.join(clauses)} ORDER BY semana DESC",
        *vals,
    )
    return [_row(r) for r in rows]


@pcp_router.post("/calendario")
async def create_calendario(data: CalendarioCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if not data.semana or len(data.semana) != 7 or data.semana[4] != "-":
        raise HTTPException(status_code=400, detail="Formato de semana inválido. Use YYYY-WW (ex: 2026-24)")

    linha = _row(await pg_db.fetch_one(
        "SELECT id, nome FROM pcp_linhas WHERE id=$1 AND tenant_id=$2", data.linha_id, tid
    ))
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")

    existing = _row(await pg_db.fetch_one(
        "SELECT id FROM pcp_calendario WHERE tenant_id=$1 AND semana=$2 AND linha_id=$3",
        tid, data.semana, data.linha_id,
    ))
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Calendário já existe para a semana {data.semana} / linha {linha['nome']}. Use PUT para atualizar.",
        )

    now = _now()
    default_dia = CalendarioDiaConfig()
    default_sab = CalendarioDiaConfig(habilitado=False)

    cal_id = _new_id()
    await pg_db.execute(
        """INSERT INTO pcp_calendario
           (id, tenant_id, semana, linha_id, linha_nome,
            seg, ter, qua, qui, sex, sab, dom,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)""",
        cal_id, tid, data.semana, data.linha_id, linha["nome"],
        (data.seg or default_dia).model_dump(),
        (data.ter or default_dia).model_dump(),
        (data.qua or default_dia).model_dump(),
        (data.qui or default_dia).model_dump(),
        (data.sex or default_dia).model_dump(),
        (data.sab or default_sab).model_dump(),
        (data.dom or default_sab).model_dump(),
        user["id"], user.get("name", ""), now, now,
    )
    logger.info(f"Calendário {data.semana}/{data.linha_id} criado por {user['name']}")
    return _row(await pg_db.fetch_one("SELECT * FROM pcp_calendario WHERE id=$1", cal_id))


@pcp_router.get("/calendario/{semana}/{linha_id}")
async def get_calendario(semana: str, linha_id: str, request: Request):
    user = await get_current_user(request)
    cal = _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_calendario WHERE tenant_id=$1 AND semana=$2 AND linha_id=$3",
        user["tenant_id"], semana, linha_id,
    ))
    if not cal:
        raise HTTPException(status_code=404, detail="Calendário não encontrado para esta semana/linha")
    return cal


@pcp_router.put("/calendario/{semana}/{linha_id}")
async def update_calendario(semana: str, linha_id: str, data: CalendarioCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    cal = _row(await pg_db.fetch_one(
        "SELECT id FROM pcp_calendario WHERE tenant_id=$1 AND semana=$2 AND linha_id=$3",
        tid, semana, linha_id,
    ))
    if not cal:
        raise HTTPException(status_code=404, detail="Calendário não encontrado. Use POST para criar.")

    payload = data.model_dump(exclude_unset=True)
    updates: Dict[str, Any] = {"updated_at": _now()}
    for dia in DIAS_SEMANA:
        if dia in payload and payload[dia] is not None:
            updates[dia] = payload[dia]

    set_clauses = []
    vals = []
    i = 1
    for k, v in updates.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1

    await pg_db.execute(
        f"UPDATE pcp_calendario SET {', '.join(set_clauses)} WHERE tenant_id=${i} AND semana=${i+1} AND linha_id=${i+2}",
        *vals, tid, semana, linha_id,
    )
    return _row(await pg_db.fetch_one(
        "SELECT * FROM pcp_calendario WHERE tenant_id=$1 AND semana=$2 AND linha_id=$3",
        tid, semana, linha_id,
    ))


# ========== SETUP SUGESTÃO ==========
@pcp_router.get("/setup-sugestao")
async def setup_sugestao(
    request: Request,
    linha_id: str,
    data: str,
    hora: str,
):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    linha = _row(await pg_db.fetch_one(
        "SELECT id, nome, setup_minutos FROM pcp_linhas WHERE id=$1 AND tenant_id=$2", linha_id, tid
    ))
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada")

    slots_do_dia = [_row(r) for r in await pg_db.fetch_all(
        """SELECT * FROM pcp_programacao
           WHERE tenant_id=$1 AND linha_id=$2 AND data=$3 AND tipo='producao' AND status != 'cancelado'
           ORDER BY hora_inicio DESC""",
        tid, linha_id, data,
    )]

    setup_minutos = linha.get("setup_minutos") or 30
    anterior = None
    for s in slots_do_dia:
        if (s.get("hora_fim") or "") <= hora:
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
