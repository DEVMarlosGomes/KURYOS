"""
Faturamento — emissão e controle de Notas Fiscais de saída.
Fluxo:
  1. PI concluído ou EXP expedida → criar NF (rascunho)
  2. Emitir NF → status emitida (número NF-e + chave de acesso registrados)
  3. Gerar Duplicatas → Contas a Receber com parcelas por condição de pagamento
  4. Acompanhar pagamento das duplicatas: aberta → paga | vencida | protestada
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import re
from datetime import datetime, timedelta, date

import database as pg_db

logger = logging.getLogger(__name__)

faturamento_router = APIRouter(prefix="/api/faturamento")

get_current_user = None
new_id_func = None
now_iso_func = None


def init_faturamento(database, auth_func, id_func, iso_func):
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


NF_STATUSES = ["rascunho", "emitida", "cancelada"]
PGTO_STATUSES = ["aguardando", "pago_parcial", "pago", "vencido"]
DUP_STATUSES = ["aberta", "paga", "vencida", "protestada", "cancelada"]

NF_TRANSITIONS = {
    "rascunho": ["emitida", "cancelada"],
    "emitida":  ["cancelada"],
    "cancelada": [],
}


# ===== HELPERS =====

def _parse_parcelas(condicao: str, valor_total: float, data_emissao: Optional[str]) -> list:
    cond = (condicao or "").strip().lower()
    try:
        base = datetime.fromisoformat(data_emissao) if data_emissao else datetime.now()
    except Exception:
        base = datetime.now()

    if not cond or cond in ("à vista", "a vista", "avista", "0"):
        return [(base.date().isoformat(), round(valor_total, 2))]

    numbers = [int(x) for x in re.findall(r'\d+', cond) if 1 <= int(x) <= 360]
    if not numbers:
        return [(base.date().isoformat(), round(valor_total, 2))]

    n = len(numbers)
    base_parcel = round(valor_total / n, 2)
    result = []
    for i, days in enumerate(numbers):
        due = (base + timedelta(days=days)).date().isoformat()
        valor = base_parcel if i < n - 1 else round(valor_total - base_parcel * (n - 1), 2)
        result.append((due, valor))
    return result


async def _auto_mark_vencidas(tid: str):
    today = date.today().isoformat()
    await pg_db.execute(
        "UPDATE faturamento_duplicatas SET status='vencida', updated_at=NOW() WHERE tenant_id=$1 AND status='aberta' AND data_vencimento < $2",
        tid, today,
    )


# ===== NF MODELS =====
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
    forma_pagamento: str = ""
    condicao_pagamento: str = ""
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


# ===== DUPLICATA MODELS =====
class DuplicataCreate(BaseModel):
    nf_id: str
    nf_numero: Optional[str] = None
    cliente_nome: str
    cliente_cnpj: str = ""
    cliente_id: Optional[str] = None
    numero_parcela: int = 1
    total_parcelas: int = 1
    valor: float
    data_emissao: Optional[str] = None
    data_vencimento: str
    forma_pagamento: str = ""
    observacoes: str = ""


class DuplicataUpdate(BaseModel):
    status: Optional[str] = None
    valor_pago: Optional[float] = None
    data_pagamento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    data_protesto: Optional[str] = None
    observacoes: Optional[str] = None


# ===== NF SEQUENCE =====
async def _next_nf_interno(tenant_id: str) -> str:
    count = await pg_db.fetch_val("SELECT COUNT(*) FROM faturamento_notas WHERE tenant_id=$1", tenant_id)
    return f"NF-{str(count + 1).zfill(6)}"


# ===== NF ROUTES =====
@faturamento_router.get("/notas")
async def list_notas(
    request: Request,
    status: Optional[str] = None,
    status_pagamento: Optional[str] = None,
    q: Optional[str] = None,
):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    clauses = ["tenant_id=$1"]
    vals = [tid]
    i = 2
    if status:
        clauses.append(f"status=${i}"); vals.append(status); i += 1
    if status_pagamento:
        clauses.append(f"status_pagamento=${i}"); vals.append(status_pagamento); i += 1
    if q:
        clauses.append(
            f"(numero_interno ILIKE ${i} OR numero_nfe ILIKE ${i} OR cliente_nome ILIKE ${i} OR order_numero ILIKE ${i})"
        )
        vals.append(f"%{q}%"); i += 1
    rows = await pg_db.fetch_all(
        f"SELECT * FROM faturamento_notas WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
        *vals,
    )
    return [_row(r) for r in rows]


@faturamento_router.get("/notas/{nf_id}")
async def get_nota(nf_id: str, request: Request):
    user = await get_current_user(request)
    nf = _row(await pg_db.fetch_one(
        "SELECT * FROM faturamento_notas WHERE id=$1 AND tenant_id=$2", nf_id, user["tenant_id"]
    ))
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

    order_numero = data.order_numero
    valor_total = data.valor_total
    valor_produtos = data.valor_produtos

    if data.order_id:
        pi = _row(await pg_db.fetch_one(
            "SELECT numero_pedido, total_pedido FROM orders WHERE id=$1 AND tenant_id=$2",
            data.order_id, tid,
        ))
        if pi:
            order_numero = pi.get("numero_pedido") or order_numero
            if not valor_total and pi.get("total_pedido"):
                valor_total = float(pi["total_pedido"])
                valor_produtos = valor_total

    valor_total = valor_total or (valor_produtos + data.valor_frete + data.valor_impostos)
    historico = [{"de": None, "para": "rascunho", "por": user["name"], "em": now}]

    await pg_db.execute(
        """INSERT INTO faturamento_notas
           (id, tenant_id, numero_interno, numero_nfe, chave_acesso, order_id, order_numero,
            exp_id, exp_numero, cliente_nome, cliente_id, cliente_cnpj,
            valor_produtos, valor_frete, valor_impostos, valor_total,
            forma_pagamento, condicao_pagamento, data_emissao, data_vencimento,
            status, status_pagamento, valor_pago, data_pagamento,
            duplicatas_geradas, total_parcelas, observacoes, historico,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                   $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32)""",
        nf_id, tid, numero_interno, None, None, data.order_id, order_numero,
        data.exp_id, data.exp_numero, data.cliente_nome.strip(), data.cliente_id, data.cliente_cnpj,
        valor_produtos, data.valor_frete, data.valor_impostos, valor_total,
        data.forma_pagamento, data.condicao_pagamento, data.data_emissao or now[:10], data.data_vencimento,
        "rascunho", "aguardando", 0.0, None,
        False, 0, data.observacoes, historico,
        user["id"], user.get("name", ""), now, now,
    )

    if data.order_id:
        await pg_db.execute(
            "UPDATE orders SET nf_id=$1, nf_numero=$2, updated_at=NOW() WHERE id=$3 AND tenant_id=$4",
            nf_id, numero_interno, data.order_id, tid,
        )

    logger.info(f"NF {numero_interno} criada por {user['name']}")
    return _row(await pg_db.fetch_one("SELECT * FROM faturamento_notas WHERE id=$1", nf_id))


@faturamento_router.put("/notas/{nf_id}")
async def update_nota(nf_id: str, data: NFUpdate, request: Request):
    user = await get_current_user(request)
    nf = _row(await pg_db.fetch_one(
        "SELECT * FROM faturamento_notas WHERE id=$1 AND tenant_id=$2", nf_id, user["tenant_id"]
    ))
    if not nf:
        raise HTTPException(status_code=404, detail="NF não encontrada")

    now = _now()
    updates: Dict[str, Any] = {"updated_at": now}
    historico = list(nf.get("historico") or [])
    payload = data.model_dump(exclude_unset=True)

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in NF_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = NF_TRANSITIONS.get(nf["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {nf['status']} → {novo_status} não permitida",
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

    set_clauses = []
    vals = []
    i = 1
    for k, v in updates.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1

    await pg_db.execute(
        f"UPDATE faturamento_notas SET {', '.join(set_clauses)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, nf_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM faturamento_notas WHERE id=$1", nf_id))


@faturamento_router.delete("/notas/{nf_id}")
async def delete_blocked(nf_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de NF não é permitida. Cancele a nota.")


@faturamento_router.post("/notas/{nf_id}/gerar-duplicatas")
async def gerar_duplicatas(nf_id: str, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    nf = _row(await pg_db.fetch_one(
        "SELECT * FROM faturamento_notas WHERE id=$1 AND tenant_id=$2", nf_id, tid
    ))
    if not nf:
        raise HTTPException(status_code=404, detail="NF não encontrada")
    if nf["status"] != "emitida":
        raise HTTPException(status_code=422, detail="Duplicatas só podem ser geradas para NFs emitidas")

    await pg_db.execute(
        "DELETE FROM faturamento_duplicatas WHERE nf_id=$1 AND tenant_id=$2 AND status IN ('aberta','vencida')",
        nf_id, tid,
    )

    parcelas = _parse_parcelas(
        nf.get("condicao_pagamento", ""),
        float(nf.get("valor_total") or 0),
        nf.get("data_emissao"),
    )

    now = _now()
    nf_num = nf.get("numero_nfe") or nf.get("numero_interno")
    total_p = len(parcelas)
    dups = []

    for i, (due_date, valor) in enumerate(parcelas):
        dups.append((
            _new_id(), tid, nf_id, nf_num,
            nf.get("order_id"), nf.get("order_numero"),
            nf["cliente_nome"], nf.get("cliente_cnpj", ""), nf.get("cliente_id"),
            i + 1, total_p, f"{i + 1}/{total_p}",
            valor, 0.0,
            nf.get("data_emissao"), due_date,
            "aberta", nf.get("forma_pagamento", ""),
            None, None, "",
            user["id"], user.get("name", ""), now, now,
        ))

    await pg_db.execute_many(
        """INSERT INTO faturamento_duplicatas
           (id, tenant_id, nf_id, nf_numero, order_id, order_numero,
            cliente_nome, cliente_cnpj, cliente_id,
            numero_parcela, total_parcelas, label,
            valor, valor_pago, data_emissao, data_vencimento,
            status, forma_pagamento, data_pagamento, data_protesto, observacoes,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                   $17,$18,$19,$20,$21,$22,$23,$24,$25)""",
        dups,
    )

    await pg_db.execute(
        "UPDATE faturamento_notas SET duplicatas_geradas=TRUE, total_parcelas=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        total_p, nf_id, tid,
    )

    logger.info(f"NF {nf_num}: {total_p} duplicata(s) gerada(s) por {user['name']}")
    rows = await pg_db.fetch_all(
        "SELECT * FROM faturamento_duplicatas WHERE nf_id=$1 AND tenant_id=$2 ORDER BY numero_parcela",
        nf_id, tid,
    )
    return [_row(r) for r in rows]


# ===== DUPLICATA ROUTES =====

@faturamento_router.get("/duplicatas/dashboard")
async def duplicatas_dashboard(request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    await _auto_mark_vencidas(tid)

    today = date.today().isoformat()
    in_30 = (date.today() + timedelta(days=30)).isoformat()

    row = _row(await pg_db.fetch_one(
        """SELECT
               COUNT(*) FILTER (WHERE status='aberta') AS em_aberto,
               COUNT(*) FILTER (WHERE status='vencida') AS vencidas,
               COUNT(*) FILTER (WHERE status='aberta' AND data_vencimento >= $2 AND data_vencimento <= $3) AS a_vencer_30,
               COALESCE(SUM(valor) FILTER (WHERE status IN ('aberta','vencida')), 0) AS total_aberto,
               COALESCE(SUM(valor) FILTER (WHERE status='vencida'), 0) AS total_vencido
           FROM faturamento_duplicatas WHERE tenant_id=$1""",
        tid, today, in_30,
    ))
    return {
        "em_aberto": row["em_aberto"],
        "vencidas": row["vencidas"],
        "a_vencer_30_dias": row["a_vencer_30"],
        "total_em_aberto": round(float(row["total_aberto"]), 2),
        "total_vencido": round(float(row["total_vencido"]), 2),
    }


@faturamento_router.get("/duplicatas")
async def list_duplicatas(
    request: Request,
    status: Optional[str] = None,
    q: Optional[str] = None,
    venc_ate: Optional[str] = None,
):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    await _auto_mark_vencidas(tid)

    clauses = ["tenant_id=$1"]
    vals = [tid]
    i = 2
    if status and status != "all":
        clauses.append(f"status=${i}"); vals.append(status); i += 1
    if q:
        clauses.append(
            f"(nf_numero ILIKE ${i} OR cliente_nome ILIKE ${i} OR order_numero ILIKE ${i})"
        )
        vals.append(f"%{q}%"); i += 1
    if venc_ate:
        clauses.append(f"data_vencimento <= ${i}"); vals.append(venc_ate); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM faturamento_duplicatas WHERE {' AND '.join(clauses)} ORDER BY data_vencimento",
        *vals,
    )
    return [_row(r) for r in rows]


@faturamento_router.post("/duplicatas")
async def create_duplicata(data: DuplicataCreate, request: Request):
    user = await get_current_user(request)
    now = _now()
    dup_id = _new_id()
    await pg_db.execute(
        """INSERT INTO faturamento_duplicatas
           (id, tenant_id, nf_id, nf_numero, order_id, order_numero,
            cliente_nome, cliente_cnpj, cliente_id,
            numero_parcela, total_parcelas, label,
            valor, valor_pago, data_emissao, data_vencimento,
            status, forma_pagamento, data_pagamento, data_protesto, observacoes,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                   $17,$18,$19,$20,$21,$22,$23,$24,$25)""",
        dup_id, user["tenant_id"], data.nf_id, data.nf_numero, None, None,
        data.cliente_nome, data.cliente_cnpj, data.cliente_id,
        data.numero_parcela, data.total_parcelas, f"{data.numero_parcela}/{data.total_parcelas}",
        data.valor, 0.0, data.data_emissao or now[:10], data.data_vencimento,
        "aberta", data.forma_pagamento, None, None, data.observacoes,
        user["id"], user.get("name", ""), now, now,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM faturamento_duplicatas WHERE id=$1", dup_id))


@faturamento_router.put("/duplicatas/{dup_id}")
async def update_duplicata(dup_id: str, data: DuplicataUpdate, request: Request):
    user = await get_current_user(request)
    dup = _row(await pg_db.fetch_one(
        "SELECT * FROM faturamento_duplicatas WHERE id=$1 AND tenant_id=$2", dup_id, user["tenant_id"]
    ))
    if not dup:
        raise HTTPException(status_code=404, detail="Duplicata não encontrada")

    now = _now()
    payload = data.model_dump(exclude_unset=True)
    updates: Dict[str, Any] = {"updated_at": now}

    if "status" in payload:
        if payload["status"] not in DUP_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {payload['status']}")
        updates["status"] = payload["status"]

    for field in ("valor_pago", "data_pagamento", "forma_pagamento", "data_protesto", "observacoes"):
        if field in payload and payload[field] is not None:
            updates[field] = payload[field]

    if "valor_pago" in updates:
        if float(updates["valor_pago"]) >= float(dup.get("valor", 0)):
            updates["status"] = "paga"
            if "data_pagamento" not in updates:
                updates["data_pagamento"] = now[:10]

    set_clauses = []
    vals = []
    i = 1
    for k, v in updates.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1

    await pg_db.execute(
        f"UPDATE faturamento_duplicatas SET {', '.join(set_clauses)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, dup_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM faturamento_duplicatas WHERE id=$1", dup_id))


# ===== DASHBOARD (NFs) =====
@faturamento_router.get("/dashboard")
async def faturamento_dashboard(request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    row = _row(await pg_db.fetch_one(
        """SELECT
               COUNT(*) FILTER (WHERE status='emitida') AS emitidas,
               COUNT(*) FILTER (WHERE status_pagamento='aguardando') AS aguardando,
               COUNT(*) FILTER (WHERE status_pagamento='vencido') AS vencidas,
               COALESCE(SUM(valor_total) FILTER (WHERE status='emitida' AND status_pagamento IN ('aguardando','pago_parcial')), 0) AS total_ar,
               COALESCE(SUM(valor_pago)  FILTER (WHERE status='emitida' AND status_pagamento IN ('aguardando','pago_parcial')), 0) AS total_pago
           FROM faturamento_notas WHERE tenant_id=$1""",
        tid,
    ))
    return {
        "emitidas": row["emitidas"],
        "aguardando_pagamento": row["aguardando"],
        "vencidas": row["vencidas"],
        "total_a_receber": round(float(row["total_ar"]) - float(row["total_pago"]), 2),
    }
