"""
Produtos — Produto-Pai (Família) e BOM (R24 / R33 / R31 / R32)
================================================================

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

from rbac import require_roles, PD_FULL, ADMIN_ONLY

logger = logging.getLogger(__name__)

produtos_router = APIRouter(prefix="/api/cadastros", tags=["produtos"])

db = None
_get_current_user = None
_new_id = None
_now_iso = None


def init_produtos(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Produtos module initialized")


async def create_produtos_indexes():
    await db.produtos_pai.create_index([("tenant_id", 1), ("id", 1)], unique=True)
    await db.produtos_pai.create_index([("tenant_id", 1), ("cliente_id", 1)])
    await db.bom_items.create_index([("tenant_id", 1), ("produto_pai_id", 1), ("camada", 1)])
    await db.bom_items.create_index([("tenant_id", 1), ("sku_id", 1), ("camada", 1)])
    await db.bom_versoes.create_index([("tenant_id", 1), ("sku_id", 1), ("vigente_desde", -1)])


# ======================================================================
#   SCHEMAS
# ======================================================================

class BomItemBulk(BaseModel):
    """Linha da Composição 1 — Bulk/fórmula (no Produto-Pai)."""
    codigo_material: str            # FR-NNNNN, MP-NNNNN
    tipo: str                       # FR | MP
    nome_material: str
    percentual: float               # % em peso
    unidade: str = "%"
    observacoes: str = ""


class BomItemEmbal(BaseModel):
    """Linha da Composição 2 — Embalagem/Insumos (por SKU)."""
    codigo_material: str            # EP-NNNNN, ES-NNNNN, RT-NNNNN
    tipo: str                       # EP | ES | RT
    nome_material: str
    quantidade_por_unidade: float   # consumo por unidade acabada (decimal ok)
    unidade_consumo: str            # un, m, kg, g, cx
    unidade_compra: str             # un, m, kg, g, cx (pode diferir)
    fator_conversao: float = 1.0   # unid_compra / unid_consumo
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
    """Vincula um SKU-filho ao produto-pai com seus dados de apresentação."""
    sku_id: str
    volume: Optional[float] = None
    unidade_volume: str = "ml"
    embalagem_primaria: str = ""
    composicao_embalagem: List[BomItemEmbal] = []
    qtd_envase: Optional[float] = None   # quantidade de granel por unidade acabada


class BomBulkUpdate(BaseModel):
    """Substitui a composição bulk inteira (nova versão de BOM)."""
    composicao_bulk: List[BomItemBulk]
    motivo: str = ""


class BomEmbalUpdate(BaseModel):
    """Substitui composição de embalagem de um SKU (revisão, R31)."""
    composicao_embalagem: List[BomItemEmbal]
    motivo: str = ""


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
    query: dict = {"tenant_id": user["tenant_id"]}
    if cliente_id:
        query["cliente_id"] = cliente_id
    if search:
        query["nome"] = {"$regex": search, "$options": "i"}
    cursor = db.produtos_pai.find(query, {"_id": 0}).sort("nome", 1)
    items = await cursor.to_list(500)
    # Attach child SKUs
    for item in items:
        skus = await db.skus.find(
            {"produto_pai_id": item["id"], "tenant_id": user["tenant_id"]},
            {"_id": 0, "id": 1, "codigo_interno": 1, "nome_produto": 1, "status": 1},
        ).to_list(50)
        item["skus_filhos"] = skus
    return {"produtos_pai": items, "total": len(items)}


@produtos_router.get("/produtos-pai/{produto_pai_id}")
async def get_produto_pai(produto_pai_id: str, request: Request):
    user = await _get_current_user(request)
    doc = await db.produtos_pai.find_one(
        {"tenant_id": user["tenant_id"], "id": produto_pai_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    # Attach bulk BOM
    bom_bulk = await db.bom_items.find(
        {"tenant_id": user["tenant_id"], "produto_pai_id": produto_pai_id, "camada": "bulk"},
        {"_id": 0},
    ).to_list(200)
    doc["composicao_bulk"] = bom_bulk

    # Attach child SKUs with their embalagem BOM
    skus = await db.skus.find(
        {"produto_pai_id": produto_pai_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    ).to_list(50)
    for sku in skus:
        bom_embal = await db.bom_items.find(
            {"tenant_id": user["tenant_id"], "sku_id": sku["id"], "camada": "embalagem"},
            {"_id": 0},
        ).sort("versao", -1).to_list(200)
        # Only active version
        versao_ativa = next((b for b in bom_embal if b.get("vigente")), None)
        sku["composicao_embalagem"] = [b for b in bom_embal if b.get("vigente")] or bom_embal[:1] or []
    doc["skus_filhos"] = skus

    return doc


@produtos_router.post("/produtos-pai", status_code=201)
async def create_produto_pai(data: ProdutoPaiCreate, request: Request):
    """
    Cria um Produto-Pai (Família de Produto).
    A fórmula/bulk é definida aqui e compartilhada entre todas as apresentações.
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    if not data.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do produto-pai é obrigatório")

    client = await db.crm_clients.find_one({"id": data.cliente_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    now = _now_iso()
    produto_pai_id = _new_id()

    doc = {
        "id": produto_pai_id,
        "tenant_id": user["tenant_id"],
        "nome": data.nome.strip(),
        "descricao": data.descricao.strip(),
        "cliente_id": data.cliente_id,
        "cliente_nome": client.get("nome_empresa", ""),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.produtos_pai.insert_one(doc)
    doc.pop("_id", None)

    # Insert bulk BOM items
    bom_items_inserted = []
    for item in data.composicao_bulk:
        bom_item = {
            "id": _new_id(),
            "tenant_id": user["tenant_id"],
            "produto_pai_id": produto_pai_id,
            "sku_id": None,
            "camada": "bulk",
            "versao": 1,
            "vigente": True,
            "vigente_desde": now,
            **item.model_dump(),
            "created_at": now,
        }
        await db.bom_items.insert_one(bom_item)
        bom_item.pop("_id", None)
        bom_items_inserted.append(bom_item)

    doc["composicao_bulk"] = bom_items_inserted
    doc["skus_filhos"] = []
    logger.info(f"Produto-Pai criado: {produto_pai_id} — {data.nome}")
    return doc


@produtos_router.patch("/produtos-pai/{produto_pai_id}")
async def update_produto_pai(produto_pai_id: str, data: ProdutoPaiUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    existing = await db.produtos_pai.find_one(
        {"tenant_id": user["tenant_id"], "id": produto_pai_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    updates: dict = {"updated_at": _now_iso()}
    if data.nome is not None:
        updates["nome"] = data.nome.strip()
    if data.descricao is not None:
        updates["descricao"] = data.descricao.strip()

    await db.produtos_pai.update_one({"tenant_id": user["tenant_id"], "id": produto_pai_id}, {"$set": updates})
    return await db.produtos_pai.find_one({"tenant_id": user["tenant_id"], "id": produto_pai_id}, {"_id": 0})


@produtos_router.post("/produtos-pai/{produto_pai_id}/skus/{sku_id}")
async def vincular_sku_ao_produto_pai(
    produto_pai_id: str, sku_id: str, data: ApresentacaoVinculo, request: Request
):
    """
    Vincula um SKU-filho ao Produto-Pai e define sua composição de embalagem (Composição 2).
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    pai = await db.produtos_pai.find_one({"tenant_id": user["tenant_id"], "id": produto_pai_id}, {"_id": 0})
    if not pai:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    sku = await db.skus.find_one({"tenant_id": user["tenant_id"], "id": sku_id}, {"_id": 0})
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")

    now = _now_iso()

    # Update SKU to link to produto-pai
    await db.skus.update_one(
        {"id": sku_id, "tenant_id": user["tenant_id"]},
        {"$set": {
            "produto_pai_id": produto_pai_id,
            "apresentacao": {
                "volume": data.volume,
                "unidade_volume": data.unidade_volume,
                "embalagem_primaria": data.embalagem_primaria,
                "qtd_envase": data.qtd_envase,
            },
            "updated_at": now,
        }},
    )

    # Insert embalagem BOM items (versão 1, vigente)
    bom_items_inserted = []
    for item in data.composicao_embalagem:
        bom_item = {
            "id": _new_id(),
            "tenant_id": user["tenant_id"],
            "produto_pai_id": produto_pai_id,
            "sku_id": sku_id,
            "camada": "embalagem",
            "versao": 1,
            "vigente": True,
            "vigente_desde": now,
            **item.model_dump(),
            "created_at": now,
        }
        await db.bom_items.insert_one(bom_item)
        bom_item.pop("_id", None)
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
    """
    R31: Atualiza composição bulk do produto-pai (nova versão). Não altera o SKU.
    Versão anterior é mantida com vigente=False para rastreabilidade histórica.
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    pai = await db.produtos_pai.find_one({"tenant_id": user["tenant_id"], "id": produto_pai_id}, {"_id": 0})
    if not pai:
        raise HTTPException(status_code=404, detail="Produto-Pai não encontrado")

    now = _now_iso()

    # Get current version number
    last = await db.bom_items.find_one(
        {"tenant_id": user["tenant_id"], "produto_pai_id": produto_pai_id, "camada": "bulk"},
        sort=[("versao", -1)],
    )
    nova_versao = (last.get("versao", 0) if last else 0) + 1

    # Inactivate previous
    await db.bom_items.update_many(
        {"tenant_id": user["tenant_id"], "produto_pai_id": produto_pai_id, "camada": "bulk", "vigente": True},
        {"$set": {"vigente": False}},
    )

    # Insert new version
    inserted = []
    for item in data.composicao_bulk:
        bom_item = {
            "id": _new_id(),
            "tenant_id": user["tenant_id"],
            "produto_pai_id": produto_pai_id,
            "sku_id": None,
            "camada": "bulk",
            "versao": nova_versao,
            "vigente": True,
            "vigente_desde": now,
            "motivo_revisao": data.motivo,
            **item.model_dump(),
            "created_at": now,
        }
        await db.bom_items.insert_one(bom_item)
        bom_item.pop("_id", None)
        inserted.append(bom_item)

    return {"versao": nova_versao, "composicao_bulk": inserted}


@produtos_router.post("/produtos-pai/{produto_pai_id}/skus/{sku_id}/bom-embalagem")
async def update_bom_embalagem(
    produto_pai_id: str, sku_id: str, data: BomEmbalUpdate, request: Request
):
    """
    R31: Troca de frasco (mesma apresentação) → nova versão de BOM com vigência.
    O SKU permanece o mesmo — código não muda.
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    sku = await db.skus.find_one({"tenant_id": user["tenant_id"], "id": sku_id}, {"_id": 0})
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")
    if sku.get("produto_pai_id") != produto_pai_id:
        raise HTTPException(status_code=409, detail="SKU não pertence a este Produto-Pai")

    now = _now_iso()

    last = await db.bom_items.find_one(
        {"tenant_id": user["tenant_id"], "sku_id": sku_id, "camada": "embalagem"},
        sort=[("versao", -1)],
    )
    nova_versao = (last.get("versao", 0) if last else 0) + 1

    await db.bom_items.update_many(
        {"tenant_id": user["tenant_id"], "sku_id": sku_id, "camada": "embalagem", "vigente": True},
        {"$set": {"vigente": False}},
    )

    inserted = []
    for item in data.composicao_embalagem:
        bom_item = {
            "id": _new_id(),
            "tenant_id": user["tenant_id"],
            "produto_pai_id": produto_pai_id,
            "sku_id": sku_id,
            "camada": "embalagem",
            "versao": nova_versao,
            "vigente": True,
            "vigente_desde": now,
            "motivo_revisao": data.motivo,
            **item.model_dump(),
            "created_at": now,
        }
        await db.bom_items.insert_one(bom_item)
        bom_item.pop("_id", None)
        inserted.append(bom_item)

    logger.info(f"BOM embalagem atualizado para SKU {sku['codigo_interno']} — versão {nova_versao} ({data.motivo})")
    return {
        "sku_codigo": sku["codigo_interno"],
        "versao": nova_versao,
        "vigente_desde": now,
        "motivo": data.motivo,
        "composicao_embalagem": inserted,
    }
