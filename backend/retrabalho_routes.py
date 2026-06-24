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
from typing import Optional
import logging
import database as pg_db

logger = logging.getLogger(__name__)

retrabalho_router = APIRouter(prefix="/api/retrabalho")

get_current_user = None
new_id_func = None
now_iso_func = None


def init_retrabalho(database, auth_func, id_func, iso_func):
    global get_current_user, new_id_func, now_iso_func
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id():
    return new_id_func()


def now_iso():
    return now_iso_func()


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat()
    return d


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
    categoria: str = "RT-1"
    rnc_id: str
    op_id: Optional[str] = None
    lote_id: Optional[str] = None
    lote_numero: Optional[str] = None
    produto_nome: str
    problema_descrito: str
    instrucoes_retrabalho: str = ""
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = None
    data_limite: Optional[str] = None
    custo_estimado: float = 0.0
    devolucao_id: Optional[str] = None
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
    count = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM retrabalho_ordens WHERE tenant_id=$1", tenant_id
    )
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
    tid = user["tenant_id"]

    clauses = ["tenant_id=$1"]
    vals: list = [tid]
    i = 2

    if status:
        clauses.append(f"status=${i}")
        vals.append(status)
        i += 1
    if categoria:
        clauses.append(f"categoria=${i}")
        vals.append(categoria)
        i += 1
    if q:
        pat = f"%{q}%"
        clauses.append(
            f"(numero_rt ILIKE ${i} OR produto_nome ILIKE ${i+1}"
            f" OR lote_numero ILIKE ${i+2} OR rnc_numero ILIKE ${i+3})"
        )
        vals.extend([pat, pat, pat, pat])

    sql = f"SELECT * FROM retrabalho_ordens WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 500"
    rows = await pg_db.fetch_all(sql, *vals)
    return [_row(r) for r in rows]


@retrabalho_router.get("/ordens/{rt_id}")
async def get_ordem(rt_id: str, request: Request):
    user = await get_current_user(request)
    rt = _row(await pg_db.fetch_one(
        "SELECT * FROM retrabalho_ordens WHERE id=$1 AND tenant_id=$2",
        rt_id, user["tenant_id"],
    ))
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
    rnc = _row(await pg_db.fetch_one(
        "SELECT * FROM cq_rncs WHERE id=$1 AND tenant_id=$2", data.rnc_id, tid
    ))
    if not rnc:
        raise HTTPException(
            status_code=400,
            detail="RNC não encontrada. Toda Ordem de Retrabalho exige RNC vinculada (RN-RT-01)",
        )

    # RN-RT-04: RT-3 requires physical return proof
    if data.categoria == "RT-3" and not data.devolucao_id:
        raise HTTPException(
            status_code=400,
            detail="RT-3 (Devolução ao Fornecedor) exige comprovante de devolução física antes de criar a RT (RN-RT-04)",
        )

    lote_numero = data.lote_numero
    if data.categoria == "RT-1" and lote_numero and not lote_numero.endswith("R"):
        lote_numero = f"{lote_numero}R"

    # Resolve OP context for saldo tracking (RN-RT-03)
    op_numero = ""
    pedido_id = ""
    pedido_numero = ""
    if data.op_id:
        op = _row(await pg_db.fetch_one(
            "SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", data.op_id, tid
        ))
        if op:
            op_numero = op.get("numero_op", "") or ""
            pedido_id = op.get("pedido_id", "") or ""
            pedido_numero = op.get("pedido_numero", "") or ""

    numero_rt = await _next_rt_numero(tid)
    now = now_iso()
    rt_id = new_id()
    historico = [{"de": None, "para": "pendente", "por": user["name"], "em": now}]

    await pg_db.execute(
        """INSERT INTO retrabalho_ordens
           (id, tenant_id, numero_rt, categoria, rnc_id, rnc_numero,
            op_id, op_numero, pedido_id, pedido_numero,
            lote_id, lote_numero, produto_nome, problema_descrito, instrucoes_retrabalho,
            responsavel_id, responsavel_nome, data_limite, custo_estimado, devolucao_id,
            status, nova_ra_id, nova_ra_numero, observacoes, historico,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                   $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                   $21,$22,$23,$24,$25,$26,$27,$28,$29)""",
        rt_id, tid, numero_rt, data.categoria, data.rnc_id, rnc.get("numero_rnc", ""),
        data.op_id, op_numero, pedido_id, pedido_numero,
        data.lote_id, lote_numero, data.produto_nome.strip(), data.problema_descrito.strip(),
        data.instrucoes_retrabalho,
        data.responsavel_id or user["id"], data.responsavel_nome or user["name"],
        data.data_limite, data.custo_estimado, data.devolucao_id,
        "pendente", None, None, data.observacoes, historico,
        user["id"], user["name"], now, now,
    )

    logger.info(f"RT {numero_rt} ({data.categoria}) criada por {user['name']} — RNC: {rnc.get('numero_rnc', '')}")
    return _row(await pg_db.fetch_one("SELECT * FROM retrabalho_ordens WHERE id=$1", rt_id))


@retrabalho_router.put("/ordens/{rt_id}")
async def update_ordem(rt_id: str, data: RTUpdate, request: Request):
    user = await get_current_user(request)
    rt = _row(await pg_db.fetch_one(
        "SELECT * FROM retrabalho_ordens WHERE id=$1 AND tenant_id=$2",
        rt_id, user["tenant_id"],
    ))
    if not rt:
        raise HTTPException(status_code=404, detail="RT não encontrada")

    now = now_iso()
    set_parts = ["updated_at=$1"]
    vals: list = [now]
    i = 2

    payload = data.model_dump(exclude_unset=True)
    historico = list(rt.get("historico") or [])

    if "status" in payload:
        novo_status = payload["status"]
        if novo_status not in RT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status inválido: {novo_status}")
        allowed = STATUS_TRANSITIONS.get(rt["status"], [])
        if novo_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transição {rt['status']} → {novo_status} não permitida",
            )
        historico.append({"de": rt["status"], "para": novo_status, "por": user["name"], "em": now})
        set_parts.append(f"status=${i}")
        vals.append(novo_status)
        i += 1
        set_parts.append(f"historico=${i}")
        vals.append(historico)
        i += 1

    for field in ("instrucoes_retrabalho", "responsavel_id", "responsavel_nome",
                  "data_limite", "custo_estimado", "observacoes"):
        if field in payload and payload[field] is not None:
            set_parts.append(f"{field}=${i}")
            vals.append(payload[field])
            i += 1

    await pg_db.execute(
        f"UPDATE retrabalho_ordens SET {', '.join(set_parts)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, rt_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM retrabalho_ordens WHERE id=$1", rt_id))


@retrabalho_router.post("/ordens/{rt_id}/concluir")
async def concluir_ordem(rt_id: str, data: RTConcluir, request: Request):
    """Marca RT como concluída e cria nova RA para re-inspeção CQ."""
    user = await get_current_user(request)
    tid = user["tenant_id"]
    rt = _row(await pg_db.fetch_one(
        "SELECT * FROM retrabalho_ordens WHERE id=$1 AND tenant_id=$2", rt_id, tid
    ))
    if not rt:
        raise HTTPException(status_code=404, detail="RT não encontrada")
    if rt["status"] not in ("pendente", "em_retrabalho"):
        raise HTTPException(status_code=422, detail=f"RT já está em status '{rt['status']}'")

    now = now_iso()
    historico = list(rt.get("historico") or [])
    historico.append({"de": rt["status"], "para": "concluido", "por": user["name"], "em": now})

    nova_ra_id = None
    nova_ra_numero = None

    if data.criar_ra:
        count = await pg_db.fetch_val(
            "SELECT COUNT(*) FROM cq_registros_analise WHERE tenant_id=$1", tid
        )
        nova_ra_numero = f"RA-{str(count + 1).zfill(5)}"
        nova_ra_id = new_id()
        await pg_db.execute(
            """INSERT INTO cq_registros_analise
               (id, tenant_id, numero_ra, lote_id, lote_numero, tipo, status,
                origem_rt_id, origem_rt_numero, categoria_rt, produto_nome,
                parametros, created_by, created_by_name, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)""",
            nova_ra_id, tid, nova_ra_numero,
            rt.get("lote_id") or new_id(), rt.get("lote_numero", ""),
            "reinspecao_retrabalho", "rascunho",
            rt_id, rt.get("numero_rt", ""), rt.get("categoria", ""), rt.get("produto_nome", ""),
            [], user["id"], user["name"], now, now,
        )
        logger.info(f"Nova RA {nova_ra_numero} criada para re-inspeção RT {rt['numero_rt']}")

    await pg_db.execute(
        """UPDATE retrabalho_ordens SET
               status='concluido', historico=$1, nova_ra_id=$2, nova_ra_numero=$3,
               observacoes_conclusao=$4, updated_at=$5
           WHERE id=$6""",
        historico, nova_ra_id, nova_ra_numero, data.observacoes_conclusao, now, rt_id,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM retrabalho_ordens WHERE id=$1", rt_id))


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
        rows = await pg_db.fetch_all(
            """SELECT status, COUNT(*) AS count, COALESCE(SUM(custo_estimado), 0) AS custo
               FROM retrabalho_ordens WHERE tenant_id=$1 AND categoria=$2
               GROUP BY status""",
            tid, cat,
        )
        status_counts = {r["status"]: int(r["count"]) for r in rows}
        custo_total = sum(float(r["custo"]) for r in rows)
        result[cat] = {
            "total": sum(int(r["count"]) for r in rows),
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
    row = await pg_db.fetch_one(
        """SELECT
               COUNT(*) FILTER (WHERE status='pendente')      AS pendente,
               COUNT(*) FILTER (WHERE status='em_retrabalho') AS em_retrabalho,
               COUNT(*) FILTER (WHERE status='concluido')     AS concluido,
               COUNT(*) FILTER (WHERE status='reprovado')     AS reprovado,
               COALESCE(SUM(custo_estimado), 0)               AS custo_total
           FROM retrabalho_ordens WHERE tenant_id=$1""",
        tid,
    )
    pendente = int(row["pendente"] or 0)
    em_retrabalho = int(row["em_retrabalho"] or 0)
    concluido = int(row["concluido"] or 0)
    reprovado = int(row["reprovado"] or 0)
    return {
        "pendente": pendente,
        "em_retrabalho": em_retrabalho,
        "aguardando_cq": concluido,
        "reprovado": reprovado,
        "total_ativos": pendente + em_retrabalho,
        "custo_total": round(float(row["custo_total"] or 0), 2),
    }
