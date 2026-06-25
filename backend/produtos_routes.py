"""
Produtos — Produto-Pai (Família) e BOM (R24 / R33 / R31 / R32)

Produto-Pai: entidade que agrupa apresentações (SKUs-filhos) de uma mesma fórmula.
  - Fórmula/bulk (Composição 1) vive no produto-pai — compartilhada entre apresentações.
  - BOM de embalagem (Composição 2) é por apresentação (por SKU-filho).

BOM tem duas camadas:
  composicao_bulk  → itens do produto-pai (MPs + FR, %)
  composicao_embal → itens do SKU (EP / ES / RT, quantidades + conversão de unidade)

R31: troca de frasco (mesma apresentação) = revisão de BOM com data de vigência, SKU não muda.
R32: rótulo vinculado ao SKU/Apresentação; frasco é genérico — titularidade no lote/WMS.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import database as pg_db
from rbac import require_roles, PD_FULL, ADMIN_ONLY

logger = logging.getLogger(__name__)

produtos_router = APIRouter(prefix="/api/cadastros", tags=["produtos"])

_get_current_user = None
_new_id = None
_now_iso = None


def init_produtos(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global _get_current_user, _new_id, _now_iso
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Produtos module initialized")


async def create_produtos_indexes():
    pass  # Indexes managed via SQL migrations


def _row(r):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} if r else None


# ======================================================================
#   SCHEMAS
# ======================================================================

class BomItemBulk(BaseModel):
    codigo_material: str
    tipo: str
    nome_material: str
    percentual: float
    unidade: str = "%"
    observacoes: str = ""


class BomItemEmbal(BaseModel):
    codigo_material: str
    tipo: str
    nome_material: str
    quantidade_por_unidade: float
    unidade_consumo: str
    unidade_compra: str
    fator_conversao: float = 1.0
    observacoes: str = ""


class ProdutoPaiCreate(BaseModel):
    nome: str
    cliente_id: str
    descricao: str = ""
    composicao_bulk: List[BomItemBulk] = []


class ProdutoPaiUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None


class ApresentacaoVinculo(BaseModel):
    sku_id: str
    volume: Optional[float] = None
    unidade_volume: str = "ml"
    embalagem_primaria: str = ""
    composicao_embalagem: List[BomItemEmbal] = []
    qtd_envase: Optional[float] = None


class BomBulkUpdate(BaseModel):
    composicao_bulk: List[BomItemBulk]
    motivo: str = ""


class BomEmbalUpdate(BaseModel):
    composicao_embalagem: List[BomItemEmbal]
    motivo: str = ""


# ======================================================================
#   HELPERS
# ======================================================================

async def _insert_bom_bulk(tenant_id: str, produto_pai_id: str, sku_id, versao: int,
                            vigente: bool, vigente_desde: str, motivo: str, item, now: str) -> dict:
    bom_id = _new_id()
    await pg_db.execute(
        """INSERT INTO bom_items
           (id, tenant_id, produto_pai_id, sku_id, camada, versao, vigente, vigente_desde, motivo_revisao,
            codigo_material, tipo, nome_material, percentual, unidade, observacoes, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)""",
        bom_id, tenant_id, produto_pai_id, sku_id, "bulk", versao, vigente, vigente_desde, motivo,
        item.codigo_material, item.tipo, item.nome_material, item.percentual, item.unidade,
        item.observacoes, now, now,
    )
    return {
        "id": bom_id, "tenant_id": tenant_id, "produto_pai_id": produto_pai_id,
        "sku_id": sku_id, "camada": "bulk", "versao": versao, "vigente": vigente,
        "vigente_desde": vigente_desde, "motivo_revisao": motivo,
        "codigo_material": item.codigo_material, "tipo": item.tipo,
        "nome_material": item.nome_material, "percentual": item.percentual,
        "unidade": item.unidade, "observacoes": item.observacoes,
        "created_at": now, "updated_at": now,
    }


async def _insert_bom_embal(tenant_id: str, produto_pai_id: str, sku_id: str, versao: int,
                             vigente: bool, vigente_desde: str, motivo: str, item, now: str) -> dict:
    bom_id = _new_id()
    await pg_db.execute(
        """INSERT INTO bom_items
           (id, tenant_id, produto_pai_id, sku_id, camada, versao, vigente, vigente_desde, motivo_revisao,
            codigo_material, tipo, nome_material, quantidade_por_unidade, unidade_consumo, unidade_compra,
            fator_conversao, observacoes, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)""",
        bom_id, tenant_id, produto_pai_id, sku_id, "embalagem", versao, vigente, vigente_desde, motivo,
        item.codigo_material, item.tipo, item.nome_material, item.quantidade_por_unidade,
        item.unidade_consumo, item.unidade_compra, item.fator_conversao, item.observacoes,
        now, now,
    )
    return {
        "id": bom_id, "tenant_id": tenant_id, "produto_pai_id": produto_pai_id,
        "sku_id": sku_id, "camada": "embalagem", "versao": versao, "vigente": vigente,
        "vigente_desde": vigente_desde, "motivo_revisao": motivo,
        "codigo_material": item.codigo_material, "tipo": item.tipo,
        "nome_material": item.nome_material, "quantidade_por_unidade": item.quantidade_por_unidade,
        "unidade_consumo": item.unidade_consumo, "unidade_compra": item.unidade_compra,
        "fator_conversao": item.fator_conversao, "observacoes": item.observacoes,
        "created_at": now, "updated_at": now,
    }


# ======================================================================
#   PRODUTO-PAI
# ======================================================================

@produtos_router.get("/produtos-pai")
async def list_produtos_pai(
    request: Request,
    cliente_id: Optional[str] = None,
    search: Optional[str] = None,
):
    user = await _get_current_user(request)
    tid = user["tenant_id"]
    clauses = ["tenant_id=$1"]
    vals = [tid]
    i = 2
    if cliente_id:
        clauses.append(f"cliente_id=${i}"); vals.append(cliente_id); i += 1
    if search:
        clauses.append(f"nome ILIKE ${i}"); vals.append(f"%{search}%"); i += 1

    rows = await pg_db.fetch_all(
        f"SELECT * FROM produtos_pai WHERE {' AND '.join(clauses)} ORDER BY nome",
        *vals,
    )
    items = [_row(r) for r in rows]
    for item in items:
        sku_rows = await pg_db.fetch_all(
            "SELECT id, codigo_interno, nome_produto, status FROM skus WHERE produto_pai_id=$1 AND tenant_id=$2",
            item["id"], tid,
        )
        item["skus_filhos"] = [dict(r) for r in sku_rows]
    return {"produtos_pai": items, "total": len(items)}


@produtos_router.get("/produtos-pai/{produto_pai_id}")
async def get_produto_pai(produto_pai_id: str, request: Request):
    user = await _get_current_user(request)
    tid = user["tenant_id"]
    doc = _row(await pg_db.fetch_one(
        "SELECT * FROM produtos_pai WHERE id=$1 AND tenant_id=$2", produto_pai_id, tid
    ))
    if not doc:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    bom_bulk_rows = await pg_db.fetch_all(
        "SELECT * FROM bom_items WHERE tenant_id=$1 AND produto_pai_id=$2 AND camada='bulk'",
        tid, produto_pai_id,
    )
    doc["composicao_bulk"] = [_row(r) for r in bom_bulk_rows]

    sku_rows = await pg_db.fetch_all(
        "SELECT * FROM skus WHERE produto_pai_id=$1 AND tenant_id=$2", produto_pai_id, tid
    )
    skus = [_row(r) for r in sku_rows]
    for sku in skus:
        bom_embal_rows = await pg_db.fetch_all(
            "SELECT * FROM bom_items WHERE tenant_id=$1 AND sku_id=$2 AND camada='embalagem' ORDER BY versao DESC",
            tid, sku["id"],
        )
        bom_embal = [_row(r) for r in bom_embal_rows]
        sku["composicao_embalagem"] = [b for b in bom_embal if b.get("vigente")] or bom_embal[:1] or []
    doc["skus_filhos"] = skus
    return doc


@produtos_router.post("/produtos-pai", status_code=201)
async def create_produto_pai(data: ProdutoPaiCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    if not data.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do produto-pai é obrigatório")

    tid = user["tenant_id"]
    client = _row(await pg_db.fetch_one(
        "SELECT nome_empresa FROM crm_clients WHERE id=$1 AND tenant_id=$2", data.cliente_id, tid
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    now = _now_iso()
    produto_pai_id = _new_id()

    await pg_db.execute(
        """INSERT INTO produtos_pai
           (id, tenant_id, nome, descricao, cliente_id, cliente_nome,
            created_by, created_by_name, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
        produto_pai_id, tid, data.nome.strip(), data.descricao.strip(),
        data.cliente_id, client.get("nome_empresa", ""),
        user["id"], user.get("name", ""), now, now,
    )

    bom_items_inserted = []
    for item in data.composicao_bulk:
        bom_item = await _insert_bom_bulk(tid, produto_pai_id, None, 1, True, now, "", item, now)
        bom_items_inserted.append(bom_item)

    logger.info(f"Produto-Pai criado: {produto_pai_id} — {data.nome}")
    doc = _row(await pg_db.fetch_one("SELECT * FROM produtos_pai WHERE id=$1", produto_pai_id))
    doc["composicao_bulk"] = bom_items_inserted
    doc["skus_filhos"] = []
    return doc


@produtos_router.patch("/produtos-pai/{produto_pai_id}")
async def update_produto_pai(produto_pai_id: str, data: ProdutoPaiUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)
    tid = user["tenant_id"]

    existing = _row(await pg_db.fetch_one(
        "SELECT id FROM produtos_pai WHERE id=$1 AND tenant_id=$2", produto_pai_id, tid
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    updates: dict = {"updated_at": _now_iso()}
    if data.nome is not None:
        updates["nome"] = data.nome.strip()
    if data.descricao is not None:
        updates["descricao"] = data.descricao.strip()

    set_clauses = []
    vals = []
    i = 1
    for k, v in updates.items():
        set_clauses.append(f"{k}=${i}"); vals.append(v); i += 1

    await pg_db.execute(
        f"UPDATE produtos_pai SET {', '.join(set_clauses)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, produto_pai_id, tid,
    )
    return _row(await pg_db.fetch_one(
        "SELECT * FROM produtos_pai WHERE id=$1 AND tenant_id=$2", produto_pai_id, tid
    ))


@produtos_router.post("/produtos-pai/{produto_pai_id}/skus/{sku_id}")
async def vincular_sku_ao_produto_pai(
    produto_pai_id: str, sku_id: str, data: ApresentacaoVinculo, request: Request
):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)
    tid = user["tenant_id"]

    pai = _row(await pg_db.fetch_one(
        "SELECT id FROM produtos_pai WHERE id=$1 AND tenant_id=$2", produto_pai_id, tid
    ))
    if not pai:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    sku = _row(await pg_db.fetch_one(
        "SELECT id, codigo_interno FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, tid
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")

    now = _now_iso()
    apresentacao_json = {
        "volume": data.volume,
        "unidade_volume": data.unidade_volume,
        "embalagem_primaria": data.embalagem_primaria,
        "qtd_envase": data.qtd_envase,
    }
    await pg_db.execute(
        "UPDATE skus SET produto_pai_id=$1, apresentacao=$2, updated_at=$3 WHERE id=$4 AND tenant_id=$5",
        produto_pai_id, apresentacao_json, now, sku_id, tid,
    )

    bom_items_inserted = []
    for item in data.composicao_embalagem:
        bom_item = await _insert_bom_embal(tid, produto_pai_id, sku_id, 1, True, now, "", item, now)
        bom_items_inserted.append(bom_item)

    return {
        "msg": f"SKU {sku['codigo_interno']} vinculado ao produto-pai {produto_pai_id}",
        "composicao_embalagem": bom_items_inserted,
    }


# ======================================================================
#   BOM VERSIONING (R31)
# ======================================================================

@produtos_router.post("/produtos-pai/{produto_pai_id}/bom-bulk")
async def update_bom_bulk(produto_pai_id: str, data: BomBulkUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)
    tid = user["tenant_id"]

    pai = _row(await pg_db.fetch_one(
        "SELECT id FROM produtos_pai WHERE id=$1 AND tenant_id=$2", produto_pai_id, tid
    ))
    if not pai:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    now = _now_iso()
    last = _row(await pg_db.fetch_one(
        """SELECT versao FROM bom_items
           WHERE tenant_id=$1 AND produto_pai_id=$2 AND camada='bulk'
           ORDER BY versao DESC LIMIT 1""",
        tid, produto_pai_id,
    ))
    nova_versao = (last["versao"] if last else 0) + 1

    await pg_db.execute(
        "UPDATE bom_items SET vigente=FALSE WHERE tenant_id=$1 AND produto_pai_id=$2 AND camada='bulk' AND vigente=TRUE",
        tid, produto_pai_id,
    )

    inserted = []
    for item in data.composicao_bulk:
        bom_item = await _insert_bom_bulk(tid, produto_pai_id, None, nova_versao, True, now, data.motivo, item, now)
        inserted.append(bom_item)

    return {"versao": nova_versao, "composicao_bulk": inserted}


@produtos_router.post("/produtos-pai/{produto_pai_id}/skus/{sku_id}/bom-embalagem")
async def update_bom_embalagem(
    produto_pai_id: str, sku_id: str, data: BomEmbalUpdate, request: Request
):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)
    tid = user["tenant_id"]

    sku = _row(await pg_db.fetch_one(
        "SELECT id, codigo_interno, produto_pai_id FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, tid
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")
    if sku.get("produto_pai_id") != produto_pai_id:
        raise HTTPException(status_code=409, detail="SKU não pertence a este Produto-Pai")

    now = _now_iso()
    last = _row(await pg_db.fetch_one(
        """SELECT versao FROM bom_items
           WHERE tenant_id=$1 AND sku_id=$2 AND camada='embalagem'
           ORDER BY versao DESC LIMIT 1""",
        tid, sku_id,
    ))
    nova_versao = (last["versao"] if last else 0) + 1

    await pg_db.execute(
        "UPDATE bom_items SET vigente=FALSE WHERE tenant_id=$1 AND sku_id=$2 AND camada='embalagem' AND vigente=TRUE",
        tid, sku_id,
    )

    inserted = []
    for item in data.composicao_embalagem:
        bom_item = await _insert_bom_embal(tid, produto_pai_id, sku_id, nova_versao, True, now, data.motivo, item, now)
        inserted.append(bom_item)

    logger.info(f"BOM embalagem atualizado para SKU {sku['codigo_interno']} — versão {nova_versao} ({data.motivo})")
    return {
        "sku_codigo": sku["codigo_interno"],
        "versao": nova_versao,
        "vigente_desde": now,
        "motivo": data.motivo,
        "composicao_embalagem": inserted,
    }
