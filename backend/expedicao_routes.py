"""
Expedição — saída de produto acabado para o cliente.
Fluxo:
  1. PI (Pedido de Industrialização) concluído → criar Ordem de Expedição (EXP)
  2. Separação e embalagem → status preparando
  3. Despacho confirmado → status expedido → SAIDA_EXPEDICAO no WMS
  4. Entrega confirmada → status entregue
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import logging
import database as pg_db

logger = logging.getLogger(__name__)

expedicao_router = APIRouter(prefix="/api/expedicao")

get_current_user = None
new_id_func = None
now_iso_func = None


def init_expedicao(database, auth_func, id_func, iso_func):
    global get_current_user, new_id_func, now_iso_func
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def _new_id():
    return new_id_func()


def _now():
    return now_iso_func()


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat()
    return d


EXP_STATUSES = ["pendente", "preparando", "conferido", "expedido", "entregue", "cancelado"]

STATUS_TRANSITIONS = {
    "pendente":    ["preparando", "cancelado"],
    "preparando":  ["conferido", "cancelado"],
    "conferido":   ["expedido", "cancelado"],
    "expedido":    ["entregue"],
    "entregue":    [],
    "cancelado":   [],
}


# ===== MODELS =====
class ExpItem(BaseModel):
    produto_nome: str
    sku: str = ""
    quantidade: float
    unidade: str = "un"
    lote: str = ""
    numero_serie: str = ""
    estoque_item_id: Optional[str] = None
    volumes: int = 1
    peso_unitario: float = 0


class ExpCreate(BaseModel):
    order_id: Optional[str] = None
    order_numero: Optional[str] = None
    cliente_nome: str
    cliente_id: Optional[str] = None
    endereco_entrega: str = ""
    transportadora: str = ""
    previsao_entrega: Optional[str] = None
    numero_nf_saida: str = ""
    items: List[ExpItem]
    observacoes: str = ""


class ExpUpdate(BaseModel):
    status: Optional[str] = None
    transportadora: Optional[str] = None
    endereco_entrega: Optional[str] = None
    previsao_entrega: Optional[str] = None
    data_expedicao: Optional[str] = None
    data_entrega: Optional[str] = None
    codigo_rastreio: Optional[str] = None
    numero_nf_saida: Optional[str] = None
    observacoes: Optional[str] = None


class ConferenciaItem(BaseModel):
    produto_nome: str
    quantidade_conferida: float
    lote_conferido: str = ""
    ok: bool = True
    divergencia: str = ""


class ConferenciaCreate(BaseModel):
    items: List[ConferenciaItem]
    conferente_nome: str = ""
    observacoes: str = ""


# ===== SEQUENCE =====
async def _next_exp_numero(tenant_id: str) -> str:
    count = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM expedicao_ordens WHERE tenant_id=$1", tenant_id
    )
    return f"EXP-{str(count + 1).zfill(5)}"


# ===== ROUTES =====
@expedicao_router.get("/ordens")
async def list_ordens(
    request: Request,
    status: Optional[str] = None,
    q: Optional[str] = None,
):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    clauses = ["tenant_id=$1"]
    vals: list = [tid]
    i = 2

    if status:
        clauses.append(f"status=${i}")
        vals.append(status)
        i += 1
    if q:
        pat = f"%{q}%"
        clauses.append(
            f"(numero_exp ILIKE ${i} OR cliente_nome ILIKE ${i+1} OR order_numero ILIKE ${i+2})"
        )
        vals.extend([pat, pat, pat])

    sql = f"SELECT * FROM expedicao_ordens WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 500"
    rows = await pg_db.fetch_all(sql, *vals)
    return [_row(r) for r in rows]


@expedicao_router.get("/ordens/{exp_id}")
async def get_ordem(exp_id: str, request: Request):
    user = await get_current_user(request)
    exp = _row(await pg_db.fetch_one(
        "SELECT * FROM expedicao_ordens WHERE id=$1 AND tenant_id=$2",
        exp_id, user["tenant_id"],
    ))
    if not exp:
        raise HTTPException(status_code=404, detail="Ordem de Expedição não encontrada")
    return exp


@expedicao_router.post("/ordens")
async def create_ordem(data: ExpCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if not data.items:
        raise HTTPException(status_code=400, detail="Informe ao menos um item")
    if not data.cliente_nome.strip():
        raise HTTPException(status_code=400, detail="Nome do cliente obrigatório")

    numero_exp = await _next_exp_numero(tid)
    now = _now()
    exp_id = _new_id()

    # Enrich from PI if provided
    order_numero = data.order_numero or ""
    project_name = ""
    if data.order_id:
        pi = _row(await pg_db.fetch_one(
            "SELECT numero_pedido, project_name FROM orders WHERE id=$1 AND tenant_id=$2",
            data.order_id, tid,
        ))
        if pi:
            order_numero = pi.get("numero_pedido") or order_numero
            project_name = pi.get("project_name") or ""

    historico = [{"de": None, "para": "pendente", "por": user["name"], "em": now}]

    await pg_db.execute(
        """INSERT INTO expedicao_ordens
           (id, tenant_id, numero_exp, order_id, order_numero, project_name,
            cliente_nome, cliente_id, endereco_entrega, transportadora,
            previsao_entrega, data_expedicao, data_entrega, codigo_rastreio,
            numero_nf_saida, status, conferencia, items, observacoes, historico,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)""",
        exp_id, tid, numero_exp, data.order_id, order_numero, project_name,
        data.cliente_nome.strip(), data.cliente_id, data.endereco_entrega, data.transportadora,
        data.previsao_entrega, None, None, None,
        data.numero_nf_saida, "pendente", None,
        [i.model_dump() for i in data.items], data.observacoes, historico,
        user["id"], user["name"], now, now,
    )

    # Update PI status if linked
    if data.order_id:
        await pg_db.execute(
            "UPDATE orders SET exp_id=$1, exp_numero=$2, updated_at=NOW() WHERE id=$3 AND tenant_id=$4",
            exp_id, numero_exp, data.order_id, tid,
        )

    logger.info(f"EXP {numero_exp} criada por {user['name']}")
    return _row(await pg_db.fetch_one("SELECT * FROM expedicao_ordens WHERE id=$1", exp_id))


@expedicao_router.put("/ordens/{exp_id}")
async def update_ordem(exp_id: str, data: ExpUpdate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    exp = _row(await pg_db.fetch_one(
        "SELECT * FROM expedicao_ordens WHERE id=$1 AND tenant_id=$2", exp_id, tid
    ))
    if not exp:
        raise HTTPException(status_code=404, detail="EXP não encontrada")

    now = _now()
    set_parts = ["updated_at=$1"]
    vals: list = [now]
    i = 2

    payload = data.model_dump(exclude_unset=True)
    historico = list(exp.get("historico") or [])

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in EXP_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = STATUS_TRANSITIONS.get(exp["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {exp['status']} → {novo_status} não permitida",
            )
        historico.append({"de": exp["status"], "para": novo_status, "por": user["name"], "em": now})
        set_parts.append(f"status=${i}")
        vals.append(novo_status)
        i += 1
        set_parts.append(f"historico=${i}")
        vals.append(historico)
        i += 1

        # When expedido: register WMS exit for each item
        if novo_status == "expedido":
            data_exp = payload.get("data_expedicao") or now[:10]
            set_parts.append(f"data_expedicao=${i}")
            vals.append(data_exp)
            i += 1
            for item in (exp.get("items") or []):
                eid = item.get("estoque_item_id")
                if not eid:
                    continue
                est = _row(await pg_db.fetch_one(
                    "SELECT * FROM estoque_items WHERE id=$1 AND tenant_id=$2", eid, tid
                ))
                if not est:
                    continue
                qty_antes = float(est.get("quantidade_atual") or 0)
                qty_saida = float(item.get("quantidade") or 0)
                qty_depois = max(0.0, qty_antes - qty_saida)
                await pg_db.execute(
                    "UPDATE estoque_items SET quantidade_atual=$1, updated_at=$2 WHERE id=$3",
                    qty_depois, now, eid,
                )
                await pg_db.execute(
                    """INSERT INTO estoque_movimentos
                       (id, tenant_id, item_id, setor, tipo_item, nome_item, codigo_item, lote,
                        tipo, direcao, quantidade, unidade, quantidade_antes, quantidade_depois,
                        motivo, referencia, documento, usuario, usuario_id, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)""",
                    _new_id(), tid, eid,
                    est.get("setor", "FABRICA"), "produto_acabado",
                    item.get("produto_nome", ""), item.get("sku", ""), item.get("lote", ""),
                    "SAIDA_EXPEDICAO", "saida", qty_saida, item.get("unidade", "un"),
                    qty_antes, qty_depois,
                    f"Expedição {exp['numero_exp']}", exp_id, exp.get("numero_exp", ""),
                    user["name"], user["id"], now,
                )

        if novo_status == "entregue":
            data_ent = payload.get("data_entrega") or now[:10]
            set_parts.append(f"data_entrega=${i}")
            vals.append(data_ent)
            i += 1

    for field in ("transportadora", "endereco_entrega", "previsao_entrega",
                  "codigo_rastreio", "numero_nf_saida", "observacoes",
                  "data_expedicao", "data_entrega"):
        if field in payload and payload[field] is not None:
            set_parts.append(f"{field}=${i}")
            vals.append(payload[field])
            i += 1

    await pg_db.execute(
        f"UPDATE expedicao_ordens SET {', '.join(set_parts)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, exp_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM expedicao_ordens WHERE id=$1", exp_id))


@expedicao_router.post("/ordens/{exp_id}/conferir")
async def conferir_ordem(exp_id: str, data: ConferenciaCreate, request: Request):
    """Realiza a conferência física dos itens — prepara → conferido."""
    user = await get_current_user(request)
    tid = user["tenant_id"]
    exp = _row(await pg_db.fetch_one(
        "SELECT * FROM expedicao_ordens WHERE id=$1 AND tenant_id=$2", exp_id, tid
    ))
    if not exp:
        raise HTTPException(status_code=404, detail="EXP não encontrada")
    if exp["status"] != "preparando":
        raise HTTPException(
            status_code=422,
            detail=f"Conferência só é possível quando status = 'preparando' (atual: {exp['status']})",
        )

    tem_divergencia = any(not item.ok for item in data.items)
    now = _now()
    historico = list(exp.get("historico") or [])
    historico.append({
        "de": "preparando", "para": "conferido", "por": user["name"], "em": now,
        "nota": "com divergências" if tem_divergencia else "OK",
    })

    conferencia_record = {
        "conferente_nome": data.conferente_nome or user["name"],
        "conferente_id": user["id"],
        "data_conferencia": now,
        "tem_divergencia": tem_divergencia,
        "observacoes": data.observacoes,
        "items": [i.model_dump() for i in data.items],
    }

    await pg_db.execute(
        """UPDATE expedicao_ordens SET
               status='conferido', conferencia=$1, historico=$2, updated_at=$3
           WHERE id=$4 AND tenant_id=$5""",
        conferencia_record, historico, now, exp_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM expedicao_ordens WHERE id=$1", exp_id))


@expedicao_router.get("/ordens/{exp_id}/romaneio")
async def romaneio(exp_id: str, request: Request):
    """Retorna dados estruturados para impressão do romaneio / packing list."""
    user = await get_current_user(request)
    exp = _row(await pg_db.fetch_one(
        "SELECT * FROM expedicao_ordens WHERE id=$1 AND tenant_id=$2",
        exp_id, user["tenant_id"],
    ))
    if not exp:
        raise HTTPException(status_code=404, detail="EXP não encontrada")

    items = exp.get("items") or []
    total_volumes = sum(int(i.get("volumes", 1)) for i in items)
    peso_total = sum(
        float(i.get("volumes", 1)) * float(i.get("peso_unitario", 0))
        for i in items
    )

    return {
        "numero_exp": exp["numero_exp"],
        "numero_nf_saida": exp.get("numero_nf_saida", ""),
        "cliente_nome": exp["cliente_nome"],
        "endereco_entrega": exp.get("endereco_entrega", ""),
        "transportadora": exp.get("transportadora", ""),
        "previsao_entrega": exp.get("previsao_entrega"),
        "data_expedicao": exp.get("data_expedicao"),
        "codigo_rastreio": exp.get("codigo_rastreio", ""),
        "status": exp["status"],
        "items": [
            {
                "produto_nome": i.get("produto_nome", ""),
                "sku": i.get("sku", ""),
                "lote": i.get("lote", ""),
                "quantidade": i.get("quantidade", 0),
                "unidade": i.get("unidade", "un"),
                "volumes": i.get("volumes", 1),
                "peso_unitario": i.get("peso_unitario", 0),
                "peso_total_item": float(i.get("volumes", 1)) * float(i.get("peso_unitario", 0)),
            }
            for i in items
        ],
        "totais": {
            "total_itens": len(items),
            "total_volumes": total_volumes,
            "peso_total_kg": round(peso_total, 3),
        },
        "conferencia": exp.get("conferencia"),
        "order_numero": exp.get("order_numero", ""),
        "observacoes": exp.get("observacoes", ""),
    }


@expedicao_router.delete("/ordens/{exp_id}")
async def delete_blocked(exp_id: str):
    raise HTTPException(status_code=405, detail="Exclusão de Ordens de Expedição não é permitida. Cancele a ordem.")


@expedicao_router.get("/dashboard")
async def expedicao_dashboard(request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    row = await pg_db.fetch_one(
        """SELECT
               COUNT(*) FILTER (WHERE status='pendente')    AS pendente,
               COUNT(*) FILTER (WHERE status='preparando')  AS preparando,
               COUNT(*) FILTER (WHERE status='conferido')   AS conferido,
               COUNT(*) FILTER (WHERE status='expedido')    AS expedido
           FROM expedicao_ordens WHERE tenant_id=$1""",
        tid,
    )
    pendente   = int(row["pendente"]   or 0)
    preparando = int(row["preparando"] or 0)
    conferido  = int(row["conferido"]  or 0)
    expedido   = int(row["expedido"]   or 0)
    return {
        "pendente": pendente,
        "preparando": preparando,
        "conferido": conferido,
        "expedido": expedido,
        "total_ativos": pendente + preparando + conferido + expedido,
    }
