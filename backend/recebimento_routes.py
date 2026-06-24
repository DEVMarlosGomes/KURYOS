"""
Recebimento de Materiais — entrada de NF vinculada à PO.
Fluxo:
  1. Recebimento criado → cada item vai para estoque em posicao_cq="quarentena"
  2. RA CQ criada automaticamente (recepcao_mp ou recepcao_embalagem)
  3. CQ aprova → WMS posicao_cq="aprovado"; CQ reprova → posicao_cq="reprovado"

Regras de Negócio:
  RN-REC-00: SLA configurável por tipo de insumo (FORMULACAO/ROTULO/EMBALAGEM)
  RN-REC-00B: URGENTE se insumo está bloqueando OP nos próximos 14 dias
  RN-REC-01: Liberar CQ → atualiza checklist MRP automaticamente
  RN-REC-02: Reprova CQ → abre RNC automaticamente
  RN-REC-03: Auto-vincular PO por fornecedor + insumo (1 match = auto; N > 1 = lista)
  RN-REC-04: Insumo de origem cliente → link direto ao PI
  RN-REC-05: Registro imutável (sem DELETE) com who/when/qty/link
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import database as pg_db

logger = logging.getLogger(__name__)

recebimento_router = APIRouter(prefix="/api/recebimento")

get_current_user = None
new_id_func = None
now_iso_func = None


def init_recebimento(database, auth_func, id_func, iso_func):
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


# ===== MAPS =====
_TIPO_MP_TO_SETOR = {
    "FORMULACAO": "MANIPULACAO",
    "ROTULO": "ROTULAGEM",
    "EMBALAGEM": "LOGISTICA",
}

_TIPO_MP_TO_RA_TIPO = {
    "FORMULACAO": "recepcao_mp",
    "ROTULO": "recepcao_embalagem",
    "EMBALAGEM": "recepcao_embalagem",
}

_DEFAULT_SLA = {"FORMULACAO": 3, "ROTULO": 2, "EMBALAGEM": 2}


# ===== MODELS =====
class RecebimentoItem(BaseModel):
    nome: str
    codigo: str = ""
    tipo_mp: str = "FORMULACAO"
    quantidade: float
    unidade: str = "kg"
    lote: str = ""
    validade: Optional[str] = None
    mp_id: Optional[str] = None
    origem_cliente: bool = False
    pedido_id: Optional[str] = None


class RecebimentoCreate(BaseModel):
    po_id: Optional[str] = None
    po_numero: Optional[str] = None
    fornecedor_id: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    numero_nf: str
    data_nf: str
    items: List[RecebimentoItem]
    observacoes: str = ""


class SLAConfig(BaseModel):
    FORMULACAO: int = 3
    ROTULO: int = 2
    EMBALAGEM: int = 2


# ===== HELPERS =====
async def _check_urgente(tid: str, item_nome: str) -> bool:
    """RN-REC-00B: True if item is blocking a scheduled OP within 14 days."""
    deadline = (datetime.utcnow() + timedelta(days=14)).isoformat()[:10]
    today = datetime.utcnow().isoformat()[:10]
    rows = await pg_db.fetch_all(
        """SELECT insumos FROM ops
           WHERE tenant_id=$1
             AND status IN ('pendente','liberada','em_producao')
             AND data_prevista IS NOT NULL
             AND data_prevista <= $2 AND data_prevista >= $3
           LIMIT 300""",
        tid, deadline, today,
    )
    nome_lower = item_nome.lower()
    for op in rows:
        for ins in (op.get("insumos") or []):
            if nome_lower in (ins.get("nome") or "").lower():
                return True
    return False


async def _get_sla(tid: str) -> dict:
    row = _row(await pg_db.fetch_one(
        "SELECT * FROM recebimento_sla_config WHERE tenant_id=$1", tid
    ))
    if row:
        return {
            "tenant_id": tid,
            "FORMULACAO": row["formulacao"],
            "ROTULO": row["rotulo"],
            "EMBALAGEM": row["embalagem"],
        }
    return {**_DEFAULT_SLA, "tenant_id": tid}


# ===== ROUTES =====

# ---- SLA Config ----
@recebimento_router.get("/sla-config")
async def get_sla_config(request: Request):
    """RN-REC-00: Get CQ SLA days by material type."""
    user = await get_current_user(request)
    return await _get_sla(user["tenant_id"])


@recebimento_router.put("/sla-config")
async def update_sla_config(data: SLAConfig, request: Request):
    """RN-REC-00: Update CQ SLA days by material type."""
    user = await get_current_user(request)
    tid = user["tenant_id"]
    await pg_db.execute(
        """INSERT INTO recebimento_sla_config (tenant_id, formulacao, rotulo, embalagem, updated_at)
           VALUES ($1, $2, $3, $4, NOW())
           ON CONFLICT (tenant_id) DO UPDATE SET
               formulacao = EXCLUDED.formulacao,
               rotulo     = EXCLUDED.rotulo,
               embalagem  = EXCLUDED.embalagem,
               updated_at = NOW()""",
        tid, data.FORMULACAO, data.ROTULO, data.EMBALAGEM,
    )
    return {"tenant_id": tid, "FORMULACAO": data.FORMULACAO, "ROTULO": data.ROTULO, "EMBALAGEM": data.EMBALAGEM}


# ---- PO Auto-link Suggestion ----
@recebimento_router.get("/sugerir-po")
async def sugerir_po(
    request: Request,
    item_nome: Optional[str] = None,
    fornecedor_id: Optional[str] = None,
):
    """RN-REC-03: Suggest open POs matching fornecedor + item name."""
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if fornecedor_id:
        rows = await pg_db.fetch_all(
            """SELECT * FROM compras_pos
               WHERE tenant_id=$1 AND status IN ('aprovada','em_entrega') AND fornecedor_id=$2
               ORDER BY created_at DESC LIMIT 100""",
            tid, fornecedor_id,
        )
    else:
        rows = await pg_db.fetch_all(
            """SELECT * FROM compras_pos
               WHERE tenant_id=$1 AND status IN ('aprovada','em_entrega')
               ORDER BY created_at DESC LIMIT 100""",
            tid,
        )

    pos = [_row(r) for r in rows]

    if item_nome:
        nome_lower = item_nome.lower()
        pos = [
            po for po in pos
            if any(
                nome_lower in (it.get("nome") or "").lower()
                for it in (po.get("items") or po.get("itens") or [])
            )
        ]

    return pos[:10]


# ---- URGENT Check ----
@recebimento_router.get("/check-urgente")
async def check_urgente(request: Request, item_nome: str):
    """RN-REC-00B: Check if an insumo is blocking a scheduled OP in the next 14 days."""
    user = await get_current_user(request)
    urgente = await _check_urgente(user["tenant_id"], item_nome)
    return {"urgente": urgente, "item_nome": item_nome}


# ---- List / Get ----
@recebimento_router.get("/entradas")
async def list_entradas(
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
            f"(numero_nf ILIKE ${i} OR fornecedor_nome ILIKE ${i+1} OR po_numero ILIKE ${i+2})"
        )
        vals.extend([pat, pat, pat])

    sql = f"SELECT * FROM recebimentos WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 500"
    rows = await pg_db.fetch_all(sql, *vals)
    return [_row(r) for r in rows]


@recebimento_router.get("/entradas/{entrada_id}")
async def get_entrada(entrada_id: str, request: Request):
    user = await get_current_user(request)
    entrada = _row(await pg_db.fetch_one(
        "SELECT * FROM recebimentos WHERE id=$1 AND tenant_id=$2",
        entrada_id, user["tenant_id"],
    ))
    if not entrada:
        raise HTTPException(status_code=404, detail="Recebimento não encontrado")
    return entrada


# ---- Create ----
@recebimento_router.post("/entradas")
async def create_entrada(data: RecebimentoCreate, request: Request):
    """
    Registra entrada de NF (RN-REC-05: imutável):
    - Cria/atualiza itens no estoque com posicao_cq=quarentena
    - Marca URGENTE se insumo bloqueia OP nos próximos 14 dias (RN-REC-00B)
    - Cria RA no CQ para cada item
    - Aplica SLA ao prazo da RA (RN-REC-00)
    - Cria registro imutável do recebimento
    """
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if not data.items:
        raise HTTPException(status_code=400, detail="Informe ao menos um item")

    now = now_iso()
    entrada_id = new_id()
    sla = await _get_sla(tid)
    items_processados = []

    for item in data.items:
        setor = _TIPO_MP_TO_SETOR.get(item.tipo_mp, "MANIPULACAO")
        ra_tipo = _TIPO_MP_TO_RA_TIPO.get(item.tipo_mp, "recepcao_mp")
        urgente = await _check_urgente(tid, item.nome)

        sla_days = sla.get(item.tipo_mp, 3)
        data_limite_cq = (datetime.utcnow() + timedelta(days=sla_days)).isoformat()[:10]

        # 1) Find or create estoque item
        if item.mp_id:
            estoque_item = _row(await pg_db.fetch_one(
                "SELECT * FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND mp_id=$3 LIMIT 1",
                tid, setor, item.mp_id,
            ))
        else:
            estoque_item = _row(await pg_db.fetch_one(
                "SELECT * FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND nome=$3 AND mp_id IS NULL LIMIT 1",
                tid, setor, item.nome,
            ))

        estoque_item_id = None

        if estoque_item:
            estoque_item_id = estoque_item["id"]
            if estoque_item.get("posicao_cq") not in ("aprovado",):
                await pg_db.execute(
                    "UPDATE estoque_items SET posicao_cq='quarentena', lote=$1, updated_at=$2 WHERE id=$3",
                    item.lote or estoque_item.get("lote", ""), now, estoque_item_id,
                )
        else:
            estoque_item_id = new_id()
            await pg_db.execute(
                """INSERT INTO estoque_items
                   (id, tenant_id, tipo_item, setor, nome, codigo, mp_id, produto_id,
                    unidade, quantidade_atual, estoque_minimo, localizacao, lote, validade,
                    observacoes, posicao_cq, created_by, created_by_name, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)""",
                estoque_item_id, tid, "mp", setor, item.nome, item.codigo,
                item.mp_id, None, item.unidade, 0, 0, "", item.lote, item.validade,
                "", "quarentena", user["id"], user["name"], now, now,
            )

        # 2) WMS entry movement
        estoque_item_full = _row(await pg_db.fetch_one(
            "SELECT * FROM estoque_items WHERE id=$1", estoque_item_id
        ))
        if estoque_item_full:
            qty_antes = float(estoque_item_full.get("quantidade_atual") or 0)
            qty_depois = qty_antes + item.quantidade
            await pg_db.execute(
                "UPDATE estoque_items SET quantidade_atual=$1, updated_at=$2 WHERE id=$3",
                qty_depois, now, estoque_item_id,
            )
            await pg_db.execute(
                """INSERT INTO estoque_movimentos
                   (id, tenant_id, item_id, setor, tipo_item, nome_item, codigo_item, lote,
                    tipo, direcao, quantidade, unidade, quantidade_antes, quantidade_depois,
                    motivo, referencia, documento, usuario, usuario_id, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)""",
                new_id(), tid, estoque_item_id, setor, "mp",
                item.nome, item.codigo, item.lote,
                "ENTRADA_RECEBIMENTO", "entrada", item.quantidade, item.unidade,
                qty_antes, qty_depois,
                f"Recebimento NF {data.numero_nf}", entrada_id, data.numero_nf,
                user["name"], user["id"], now,
            )

        # 3) Create RA in CQ with SLA deadline
        lote_numero = item.lote or f"L{now[:10].replace('-', '')}"
        ra_id = new_id()
        await pg_db.execute(
            """INSERT INTO cq_registros_analise
               (id, tenant_id, lote_id, lote_numero, tipo, status,
                item_id, item_nome, item_tipo, fornecedor_id, fornecedor_nome,
                nf_numero, nf_data, quantidade_recebida, unidade,
                numero_lote_fornecedor, data_validade_fornecedor,
                data_limite_cq, urgente, parametros, recebimento_id,
                created_by, created_by_name, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)""",
            ra_id, tid, new_id(), lote_numero, ra_tipo, "rascunho",
            estoque_item_id, item.nome, item.tipo_mp,
            data.fornecedor_id, data.fornecedor_nome,
            data.numero_nf, data.data_nf, item.quantidade, item.unidade,
            item.lote, item.validade,
            data_limite_cq, urgente, [], entrada_id,
            user["id"], user["name"], now, now,
        )

        items_processados.append({
            **item.model_dump(),
            "estoque_item_id": estoque_item_id,
            "setor": setor,
            "ra_id": ra_id,
            "ra_status": "rascunho",
            "urgente": urgente,
            "data_limite_cq": data_limite_cq,
        })

    # 4) Create immutable recebimento record (RN-REC-05)
    tem_urgente = any(i.get("urgente") for i in items_processados)
    await pg_db.execute(
        """INSERT INTO recebimentos
           (id, tenant_id, po_id, po_numero, fornecedor_id, fornecedor_nome,
            numero_nf, data_nf, status, items, tem_urgente, observacoes,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)""",
        entrada_id, tid, data.po_id, data.po_numero or "",
        data.fornecedor_id, data.fornecedor_nome or "",
        data.numero_nf, data.data_nf, "quarentena",
        items_processados, tem_urgente, data.observacoes,
        user["id"], user["name"], now, now,
    )

    logger.info(
        f"Recebimento {entrada_id} criado: NF={data.numero_nf} "
        f"itens={len(items_processados)} urgente={tem_urgente}"
    )
    return _row(await pg_db.fetch_one("SELECT * FROM recebimentos WHERE id=$1", entrada_id))


# ---- RN-REC-05: No DELETE ----
@recebimento_router.delete("/entradas/{entrada_id}")
async def delete_blocked(entrada_id: str):
    raise HTTPException(
        status_code=405,
        detail="Registros de recebimento são imutáveis. Exclusão não permitida (RN-REC-05).",
    )
