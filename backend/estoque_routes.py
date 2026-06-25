"""
Estoque Routes - Módulo de Controle de Estoque (4 setores + Kardex imutável)
Setores: MANIPULACAO (MP FORMULACAO), ROTULAGEM (MP ROTULO), LOGISTICA (MP EMBALAGEM), FABRICA (LotePA)
"""

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import re

import database as pg_db
from cq_routes import cq_verificar_lote_aprovado, cq_verificar_liberacao_palete

logger = logging.getLogger(__name__)

estoque_router = APIRouter(prefix="/api/estoque")

# ============ MODULE STATE ============
_get_current_user = None
_new_id = None
_now_iso = None


def init_estoque(database, get_user_fn, new_id_fn, now_iso_fn):
    global _get_current_user, _new_id, _now_iso
    _get_current_user = get_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Estoque module initialized")


def _row(r):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} if r else None


# ============ CONSTANTS ============

SETORES = ["MANIPULACAO", "ROTULAGEM", "LOGISTICA", "FABRICA", "DEVOLUCAO"]

SETOR_LABELS = {
    "MANIPULACAO": "Matérias-Primas (Manipulação)",
    "ROTULAGEM": "Rótulos (Rotulagem)",
    "LOGISTICA": "Insumos / Embalagens (Logística)",
    "FABRICA": "Produto Acabado (Fábrica)",
    "DEVOLUCAO": "Devoluções / Quarentena Especial",
}

SETOR_TIPO_MP = {
    "MANIPULACAO": "FORMULACAO",
    "ROTULAGEM": "ROTULO",
    "LOGISTICA": "EMBALAGEM",
}

_LOC_PATTERN = re.compile(r"^[A-Z]{2,5}-[A-Z]-\d{2}-\d+$", re.IGNORECASE)

TIPOS_MOVIMENTO = [
    "ENTRADA_RECEBIMENTO",
    "SAIDA_CONSUMO_OP",
    "SAIDA_EXPEDICAO",
    "AJUSTE_ENTRADA",
    "AJUSTE_SAIDA",
    "AMOSTRA",
    "TRANSFERENCIA_ENTRADA",
    "TRANSFERENCIA_SAIDA",
]

MOVIMENTOS_ENTRADA = {"ENTRADA_RECEBIMENTO", "AJUSTE_ENTRADA", "TRANSFERENCIA_ENTRADA"}
MOVIMENTOS_SAIDA = {"SAIDA_CONSUMO_OP", "SAIDA_EXPEDICAO", "AJUSTE_SAIDA", "AMOSTRA", "TRANSFERENCIA_SAIDA"}
MOVIMENTOS_COM_MOTIVO_OBRIGATORIO = {"AJUSTE_ENTRADA", "AJUSTE_SAIDA"}

TIPO_ITEM_VALORES = ["mp", "produto_acabado"]


# ============ PYDANTIC MODELS ============

POSICOES_CQ = ["livre", "quarentena", "aprovado", "reprovado"]

class EstoqueItemCreate(BaseModel):
    tipo_item: str
    setor: str
    nome: str
    codigo: str = ""
    mp_id: Optional[str] = None
    produto_id: Optional[str] = None
    unidade: str = "un"
    estoque_minimo: float = 0
    localizacao: str = ""
    localizacao_estruturada: str = ""
    lote: str = ""
    validade: Optional[str] = None
    observacoes: str = ""
    posicao_cq: str = "livre"


class EstoqueItemUpdate(BaseModel):
    nome: Optional[str] = None
    codigo: Optional[str] = None
    unidade: Optional[str] = None
    estoque_minimo: Optional[float] = None
    localizacao: Optional[str] = None
    localizacao_estruturada: Optional[str] = None
    lote: Optional[str] = None
    validade: Optional[str] = None
    observacoes: Optional[str] = None
    posicao_cq: Optional[str] = None


class MovimentoCreate(BaseModel):
    item_id: str
    tipo: str
    quantidade: float
    motivo: str = ""
    referencia: str = ""
    documento: str = ""


class TransferenciaCreate(BaseModel):
    item_origem_id: str
    setor_destino: str
    quantidade: float
    motivo: str = ""


# ============ HELPERS ============

async def _log_movimento(
    item: dict, tipo: str, quantidade: float,
    motivo: str, referencia: str, documento: str,
    user: dict, quantidade_antes: float, quantidade_depois: float,
) -> dict:
    mov_id = _new_id()
    now = _now_iso()
    await pg_db.execute(
        """INSERT INTO estoque_movimentos
           (id, tenant_id, item_id, setor, tipo_item, nome_item, codigo_item, lote,
            tipo, direcao, quantidade, unidade, quantidade_antes, quantidade_depois,
            motivo, referencia, documento, usuario, usuario_id, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)""",
        mov_id, item["tenant_id"], item["id"], item["setor"], item["tipo_item"],
        item["nome"], item.get("codigo", ""), item.get("lote", ""),
        tipo, "entrada" if tipo in MOVIMENTOS_ENTRADA else "saida",
        quantidade, item.get("unidade", "un"), quantidade_antes, quantidade_depois,
        motivo, referencia, documento, user["name"], user["id"], now,
    )
    return {
        "id": mov_id, "tenant_id": item["tenant_id"], "item_id": item["id"],
        "setor": item["setor"], "tipo_item": item["tipo_item"],
        "nome_item": item["nome"], "codigo_item": item.get("codigo", ""),
        "lote": item.get("lote", ""), "tipo": tipo,
        "direcao": "entrada" if tipo in MOVIMENTOS_ENTRADA else "saida",
        "quantidade": quantidade, "unidade": item.get("unidade", "un"),
        "quantidade_antes": quantidade_antes, "quantidade_depois": quantidade_depois,
        "motivo": motivo, "referencia": referencia, "documento": documento,
        "usuario": user["name"], "usuario_id": user["id"], "created_at": now,
    }


async def _get_item_or_404(item_id: str, tenant_id: str) -> dict:
    item = _row(await pg_db.fetch_one(
        "SELECT * FROM estoque_items WHERE id=$1 AND tenant_id=$2", item_id, tenant_id
    ))
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    return item


# ============ ITEMS CRUD ============

@estoque_router.post("/items")
async def create_item(data: EstoqueItemCreate, request: Request):
    user = await _get_current_user(request)

    if data.setor not in SETORES:
        raise HTTPException(status_code=400, detail=f"Setor inválido. Valores: {SETORES}")
    if data.tipo_item not in TIPO_ITEM_VALORES:
        raise HTTPException(status_code=400, detail=f"tipo_item inválido: {data.tipo_item}")

    if data.setor == "FABRICA" and data.tipo_item != "produto_acabado":
        raise HTTPException(status_code=400, detail="Setor FABRICA só aceita produto_acabado")
    if data.setor not in ("FABRICA", "DEVOLUCAO") and data.tipo_item != "mp":
        raise HTTPException(status_code=400, detail=f"Setor {data.setor} só aceita MPs (tipo_item=mp)")

    if data.localizacao_estruturada and not _LOC_PATTERN.match(data.localizacao_estruturada):
        raise HTTPException(
            status_code=400,
            detail="Formato de localização inválido. Use: GAL-B-04-1 (sigla-corredor-prateleira-posição)",
        )

    tid = user["tenant_id"]
    if data.mp_id:
        existing = _row(await pg_db.fetch_one(
            "SELECT id FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND mp_id=$3",
            tid, data.setor, data.mp_id,
        ))
    elif data.produto_id:
        existing = _row(await pg_db.fetch_one(
            "SELECT id FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND produto_id=$3",
            tid, data.setor, data.produto_id,
        ))
    else:
        existing = _row(await pg_db.fetch_one(
            "SELECT id FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND nome=$3 AND mp_id IS NULL AND produto_id IS NULL",
            tid, data.setor, data.nome,
        ))

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe um item deste tipo no setor {SETOR_LABELS[data.setor]}. Use movimentação de entrada.",
        )

    now = _now_iso()
    item_id = _new_id()
    await pg_db.execute(
        """INSERT INTO estoque_items
           (id, tenant_id, tipo_item, setor, nome, codigo, mp_id, produto_id,
            unidade, quantidade_atual, estoque_minimo, localizacao, lote, validade,
            observacoes, posicao_cq, localizacao_estruturada, created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)""",
        item_id, tid, data.tipo_item, data.setor, data.nome, data.codigo,
        data.mp_id, data.produto_id, data.unidade, 0, data.estoque_minimo,
        data.localizacao, data.lote, data.validade, data.observacoes,
        data.posicao_cq if data.posicao_cq in POSICOES_CQ else "livre",
        data.localizacao_estruturada, user["id"], user.get("name", ""), now, now,
    )
    logger.info(f"Created estoque_item {item_id} setor={data.setor} nome={data.nome}")
    return _row(await pg_db.fetch_one("SELECT * FROM estoque_items WHERE id=$1", item_id))


@estoque_router.get("/items")
async def list_items(
    request: Request,
    setor: Optional[str] = None,
    tipo_item: Optional[str] = None,
    search: Optional[str] = None,
    only_low_stock: bool = False,
    posicao_cq: Optional[str] = None,
):
    user = await _get_current_user(request)
    clauses = ["tenant_id=$1"]
    vals = [user["tenant_id"]]
    i = 2
    if setor:
        clauses.append(f"setor=${i}"); vals.append(setor); i += 1
    if tipo_item:
        clauses.append(f"tipo_item=${i}"); vals.append(tipo_item); i += 1
    if search:
        clauses.append(f"(nome ILIKE ${i} OR codigo ILIKE ${i} OR lote ILIKE ${i})")
        vals.append(f"%{search}%"); i += 1
    if posicao_cq:
        clauses.append(f"posicao_cq=${i}"); vals.append(posicao_cq); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM estoque_items WHERE {' AND '.join(clauses)} ORDER BY nome",
        *vals,
    )
    items = [_row(r) for r in rows]
    if only_low_stock:
        items = [
            it for it in items
            if it.get("quantidade_atual", 0) <= it.get("estoque_minimo", 0)
            and it.get("estoque_minimo", 0) > 0
        ]
    return items


@estoque_router.get("/items/{item_id}")
async def get_item(item_id: str, request: Request):
    user = await _get_current_user(request)
    return await _get_item_or_404(item_id, user["tenant_id"])


@estoque_router.put("/items/{item_id}")
async def update_item(item_id: str, data: EstoqueItemUpdate, request: Request):
    user = await _get_current_user(request)
    await _get_item_or_404(item_id, user["tenant_id"])

    update_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    set_clauses = []
    vals = []
    i = 1
    for k, v in update_fields.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1
    set_clauses.append("updated_at=NOW()")

    await pg_db.execute(
        f"UPDATE estoque_items SET {', '.join(set_clauses)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, item_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM estoque_items WHERE id=$1", item_id))


@estoque_router.delete("/items/{item_id}")
async def delete_item(item_id: str, request: Request):
    user = await _get_current_user(request)
    item = await _get_item_or_404(item_id, user["tenant_id"])

    if float(item.get("quantidade_atual") or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir: saldo = {item['quantidade_atual']} {item.get('unidade', '')}. Zere o saldo antes.",
        )

    await pg_db.execute(
        "DELETE FROM estoque_items WHERE id=$1 AND tenant_id=$2", item_id, user["tenant_id"]
    )
    logger.info(f"Deleted estoque_item {item_id}")
    return {"deleted": item_id}


@estoque_router.patch("/items/{item_id}/posicao")
async def update_posicao_cq(item_id: str, request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    nova_posicao = body.get("posicao_cq")
    if nova_posicao not in POSICOES_CQ:
        raise HTTPException(status_code=400, detail=f"Posição inválida. Permitidas: {POSICOES_CQ}")
    await _get_item_or_404(item_id, user["tenant_id"])
    await pg_db.execute(
        "UPDATE estoque_items SET posicao_cq=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        nova_posicao, item_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM estoque_items WHERE id=$1", item_id))


# ============ MOVIMENTOS (KARDEX - APPEND ONLY) ============

@estoque_router.post("/movimentos")
async def create_movimento(data: MovimentoCreate, request: Request):
    user = await _get_current_user(request)

    if data.tipo not in TIPOS_MOVIMENTO:
        raise HTTPException(status_code=400, detail=f"Tipo de movimento inválido. Valores: {TIPOS_MOVIMENTO}")
    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser > 0")
    if data.tipo in MOVIMENTOS_COM_MOTIVO_OBRIGATORIO and not data.motivo.strip():
        raise HTTPException(status_code=400, detail="Motivo é obrigatório para ajustes manuais (rastreabilidade)")
    if data.tipo in ("TRANSFERENCIA_ENTRADA", "TRANSFERENCIA_SAIDA"):
        raise HTTPException(
            status_code=400,
            detail="Transferências devem ser registradas via POST /api/estoque/transferencias",
        )

    item = await _get_item_or_404(data.item_id, user["tenant_id"])

    if data.referencia:
        await cq_verificar_lote_aprovado(None, user["tenant_id"], data.referencia)
    if data.tipo == "SAIDA_EXPEDICAO" and data.referencia:
        await cq_verificar_liberacao_palete(None, user["tenant_id"], data.referencia)

    quantidade_antes = float(item.get("quantidade_atual") or 0)
    delta = data.quantidade if data.tipo in MOVIMENTOS_ENTRADA else -data.quantidade
    quantidade_depois = quantidade_antes + delta

    if quantidade_depois < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente: atual={quantidade_antes} {item.get('unidade')}, tentativa de saída={data.quantidade}",
        )

    await pg_db.execute(
        "UPDATE estoque_items SET quantidade_atual=$1, updated_at=NOW() WHERE id=$2",
        quantidade_depois, data.item_id,
    )

    mov = await _log_movimento(
        item=item, tipo=data.tipo, quantidade=data.quantidade,
        motivo=data.motivo, referencia=data.referencia, documento=data.documento,
        user=user, quantidade_antes=quantidade_antes, quantidade_depois=quantidade_depois,
    )

    updated_item = _row(await pg_db.fetch_one("SELECT * FROM estoque_items WHERE id=$1", data.item_id))
    return {"movimento": mov, "item": updated_item}


@estoque_router.post("/transferencias")
async def create_transferencia(data: TransferenciaCreate, request: Request):
    user = await _get_current_user(request)

    if data.setor_destino not in SETORES:
        raise HTTPException(status_code=400, detail="Setor destino inválido")
    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser > 0")

    origem = await _get_item_or_404(data.item_origem_id, user["tenant_id"])
    if origem["setor"] == data.setor_destino:
        raise HTTPException(status_code=400, detail="Setor destino é igual ao origem")

    if data.setor_destino == "FABRICA" and origem["tipo_item"] != "produto_acabado":
        raise HTTPException(status_code=400, detail="Setor FABRICA só aceita produto_acabado")
    if data.setor_destino != "FABRICA" and origem["tipo_item"] != "mp":
        raise HTTPException(status_code=400, detail=f"Setor {data.setor_destino} só aceita MPs")

    qty_origem_antes = float(origem.get("quantidade_atual") or 0)
    if data.quantidade > qty_origem_antes:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente no origem: {qty_origem_antes} {origem.get('unidade')}",
        )

    tid = user["tenant_id"]
    if origem.get("mp_id"):
        destino = _row(await pg_db.fetch_one(
            "SELECT * FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND mp_id=$3",
            tid, data.setor_destino, origem["mp_id"],
        ))
    elif origem.get("produto_id"):
        destino = _row(await pg_db.fetch_one(
            "SELECT * FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND produto_id=$3",
            tid, data.setor_destino, origem["produto_id"],
        ))
    else:
        destino = _row(await pg_db.fetch_one(
            "SELECT * FROM estoque_items WHERE tenant_id=$1 AND setor=$2 AND nome=$3",
            tid, data.setor_destino, origem["nome"],
        ))

    now = _now_iso()

    if not destino:
        dest_id = _new_id()
        await pg_db.execute(
            """INSERT INTO estoque_items
               (id, tenant_id, tipo_item, setor, nome, codigo, mp_id, produto_id,
                unidade, quantidade_atual, estoque_minimo, localizacao, lote, validade,
                observacoes, posicao_cq, localizacao_estruturada, created_by, created_by_name, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,NOW(),NOW())""",
            dest_id, tid, origem["tipo_item"], data.setor_destino,
            origem["nome"], origem.get("codigo", ""), origem.get("mp_id"), origem.get("produto_id"),
            origem.get("unidade", "un"), 0, 0, "", origem.get("lote", ""), origem.get("validade"),
            f"Criado automaticamente por transferência de {SETOR_LABELS.get(origem['setor'], origem['setor'])}",
            "livre", "", user["id"], user.get("name", ""),
        )
        destino = _row(await pg_db.fetch_one("SELECT * FROM estoque_items WHERE id=$1", dest_id))

    qty_origem_depois = qty_origem_antes - data.quantidade
    qty_dest_antes = float(destino.get("quantidade_atual") or 0)
    qty_dest_depois = qty_dest_antes + data.quantidade

    await pg_db.execute(
        "UPDATE estoque_items SET quantidade_atual=$1, updated_at=NOW() WHERE id=$2",
        qty_origem_depois, origem["id"],
    )
    await pg_db.execute(
        "UPDATE estoque_items SET quantidade_atual=$1, updated_at=NOW() WHERE id=$2",
        qty_dest_depois, destino["id"],
    )

    ref = f"TRANSF-{_new_id()[:8]}"
    mov_saida = await _log_movimento(
        item=origem, tipo="TRANSFERENCIA_SAIDA",
        quantidade=data.quantidade,
        motivo=data.motivo or f"Transferência para {SETOR_LABELS.get(data.setor_destino)}",
        referencia=ref, documento=destino["id"], user=user,
        quantidade_antes=qty_origem_antes, quantidade_depois=qty_origem_depois,
    )
    mov_entrada = await _log_movimento(
        item=destino, tipo="TRANSFERENCIA_ENTRADA",
        quantidade=data.quantidade,
        motivo=data.motivo or f"Transferência de {SETOR_LABELS.get(origem['setor'])}",
        referencia=ref, documento=origem["id"], user=user,
        quantidade_antes=qty_dest_antes, quantidade_depois=qty_dest_depois,
    )

    return {
        "referencia": ref,
        "mov_saida": mov_saida,
        "mov_entrada": mov_entrada,
        "item_origem": _row(await pg_db.fetch_one("SELECT * FROM estoque_items WHERE id=$1", origem["id"])),
        "item_destino": _row(await pg_db.fetch_one("SELECT * FROM estoque_items WHERE id=$1", destino["id"])),
    }


@estoque_router.get("/kardex/{item_id}")
async def get_kardex(item_id: str, request: Request, limit: int = 500):
    user = await _get_current_user(request)
    await _get_item_or_404(item_id, user["tenant_id"])
    rows = await pg_db.fetch_all(
        f"SELECT * FROM estoque_movimentos WHERE item_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT {limit}",
        item_id, user["tenant_id"],
    )
    return [_row(r) for r in rows]


@estoque_router.get("/movimentos")
async def list_movimentos(
    request: Request,
    setor: Optional[str] = None,
    tipo: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    limit: int = 500,
):
    user = await _get_current_user(request)
    clauses = ["tenant_id=$1"]
    vals = [user["tenant_id"]]
    i = 2
    if setor:
        clauses.append(f"setor=${i}"); vals.append(setor); i += 1
    if tipo:
        clauses.append(f"tipo=${i}"); vals.append(tipo); i += 1
    if data_inicio:
        clauses.append(f"created_at::date >= ${i}::date"); vals.append(data_inicio); i += 1
    if data_fim:
        clauses.append(f"created_at::date <= ${i}::date"); vals.append(data_fim); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM estoque_movimentos WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT {limit}",
        *vals,
    )
    return [_row(r) for r in rows]


# ============ DASHBOARD ============

@estoque_router.get("/dashboard")
async def estoque_dashboard(request: Request):
    user = await _get_current_user(request)
    t_id = user["tenant_id"]

    items_all = [_row(r) for r in await pg_db.fetch_all(
        "SELECT * FROM estoque_items WHERE tenant_id=$1", t_id
    )]

    by_setor: Dict[str, Any] = {}
    low_stock = []
    expiring_soon = []
    today = datetime.now(timezone.utc).date()

    for item in items_all:
        setor = item.get("setor", "?")
        by_setor.setdefault(setor, {"total_items": 0, "total_quantidade": 0})
        by_setor[setor]["total_items"] += 1
        by_setor[setor]["total_quantidade"] += float(item.get("quantidade_atual") or 0)

        if item.get("estoque_minimo", 0) > 0 and float(item.get("quantidade_atual") or 0) <= float(item["estoque_minimo"]):
            low_stock.append(item)

        validade = item.get("validade")
        if validade:
            try:
                val_str = validade if isinstance(validade, str) else validade.isoformat()
                val_date = datetime.fromisoformat(val_str.replace("Z", "+00:00")).date()
                days_left = (val_date - today).days
                if 0 <= days_left <= 30:
                    expiring_soon.append({**item, "days_left": days_left})
            except Exception:
                pass

    last_24h = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM estoque_movimentos WHERE tenant_id=$1 AND created_at >= CURRENT_DATE::timestamptz",
        t_id,
    )

    cutoff_90 = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    active_rows = await pg_db.fetch_all(
        "SELECT DISTINCT item_id FROM estoque_movimentos WHERE tenant_id=$1 AND created_at >= $2::timestamptz",
        t_id, cutoff_90,
    )
    itens_ativos_ids = {r["item_id"] for r in active_rows}
    obsoletos = [
        it for it in items_all
        if float(it.get("quantidade_atual") or 0) > 0 and it["id"] not in itens_ativos_ids
    ]

    return {
        "setores": [
            {
                "setor": s,
                "label": SETOR_LABELS.get(s, s),
                "total_items": by_setor.get(s, {}).get("total_items", 0),
                "total_quantidade": by_setor.get(s, {}).get("total_quantidade", 0),
            }
            for s in SETORES
        ],
        "alertas": {
            "baixo_estoque": low_stock,
            "validade_proxima": expiring_soon,
            "obsoletos": obsoletos[:20],
        },
        "movimentos_hoje": last_24h,
        "total_items": len(items_all),
    }


@estoque_router.get("/options")
async def get_options():
    return {
        "setores": SETORES,
        "setor_labels": SETOR_LABELS,
        "tipos_movimento": TIPOS_MOVIMENTO,
        "movimentos_entrada": list(MOVIMENTOS_ENTRADA),
        "movimentos_saida": list(MOVIMENTOS_SAIDA),
        "tipos_item": TIPO_ITEM_VALORES,
    }


@estoque_router.get("/alertas/obsolescencia")
async def alertas_obsolescencia(request: Request, dias: int = 90):
    user = await _get_current_user(request)
    t_id = user["tenant_id"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    active_rows = await pg_db.fetch_all(
        "SELECT DISTINCT item_id FROM estoque_movimentos WHERE tenant_id=$1 AND created_at >= $2::timestamptz",
        t_id, cutoff,
    )
    itens_ativos_ids = {r["item_id"] for r in active_rows}
    items = [_row(r) for r in await pg_db.fetch_all(
        "SELECT * FROM estoque_items WHERE tenant_id=$1 AND quantidade_atual > 0", t_id
    )]
    obsoletos = [it for it in items if it["id"] not in itens_ativos_ids]
    return {"dias_sem_movimento": dias, "total": len(obsoletos), "items": obsoletos}


@estoque_router.get("/fifo-sugestao")
async def fifo_sugestao(request: Request, nome: str, setor: Optional[str] = None):
    user = await _get_current_user(request)
    clauses = ["tenant_id=$1", "nome ILIKE $2", "quantidade_atual > 0", "posicao_cq='aprovado'"]
    vals = [user["tenant_id"], f"%{nome}%"]
    i = 3
    if setor:
        clauses.append(f"setor=${i}"); vals.append(setor); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM estoque_items WHERE {' AND '.join(clauses)}",
        *vals,
    )
    items = [_row(r) for r in rows]
    items.sort(key=lambda x: x.get("validade") or "9999-99-99")
    return {"fifo_order": items, "total_lotes": len(items)}
