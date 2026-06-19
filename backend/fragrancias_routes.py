"""
Fragrâncias — Cadastro de Fragrâncias (R08)
============================================

Código interno FR-[SEQ5] é a identidade estável da fragrância.
Nasce na aprovação da amostra (ou via cadastro manual).

Cada fragrância mantém lista de fornecedores com:
  - código do fornecedor (cross-reference)
  - status de homologação
  - histórico de preço
  - lead time e MOQ

Mesmo nome + composição diferente = FRs distintos.
Nome/inspiração é campo de busca, nunca a chave.

R07: campo de fragrância na amostra segue padrão "FR-NNNNN - Nome" (código primeiro).
"""

import logging
import re
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rbac import require_roles, PD_FULL, ADMIN_ONLY

logger = logging.getLogger(__name__)

fragrancias_router = APIRouter(prefix="/api/cadastros", tags=["fragrancias"])

db = None
_get_current_user = None
_new_id = None
_now_iso = None


def init_fragrancias(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Fragrâncias module initialized")


async def create_fragrancias_indexes():
    await db.fragrancias.create_index([("tenant_id", 1), ("codigo_interno", 1)], unique=True)
    await db.fragrancias.create_index([("tenant_id", 1), ("inspiracao", "text")])
    await db.fragrancias.create_index([("tenant_id", 1), ("status", 1)])
    await db.fragrancias.create_index(
        [("tenant_id", 1), ("fornecedores.codigo_fornecedor", 1)]
    )


async def _next_fr_seq(tenant_id: str) -> str:
    """Atomic FR counter per tenant. Returns 'FR-NNNNN'."""
    from workflow_engine import next_sequence
    seq = await next_sequence(tenant_id, "fr_seq", start=0)
    return f"FR-{str(seq).zfill(5)}"


# ======================================================================
#   SCHEMAS
# ======================================================================

class FornecedorRef(BaseModel):
    fornecedor_id: str = ""
    fornecedor_nome: str
    codigo_fornecedor: str          # cross-reference
    status_homologacao: str = "em_avaliacao"  # em_avaliacao | aprovado | reprovado
    preco_por_kg: Optional[float] = None
    moeda: str = "BRL"
    lead_time_dias: Optional[int] = None
    moq_kg: Optional[float] = None
    observacoes: str = ""


class FragranciaCreate(BaseModel):
    inspiracao: str                 # "Good Girl", "Velvet Rose" — search field, not key
    descricao: str = ""
    fornecedores: List[FornecedorRef] = []
    status: str = "ativa"          # ativa | inativa


class FragranciaUpdate(BaseModel):
    inspiracao: Optional[str] = None
    descricao: Optional[str] = None
    status: Optional[str] = None


class FornecedorRefAdd(BaseModel):
    fornecedor_id: str = ""
    fornecedor_nome: str
    codigo_fornecedor: str
    status_homologacao: str = "em_avaliacao"
    preco_por_kg: Optional[float] = None
    moeda: str = "BRL"
    lead_time_dias: Optional[int] = None
    moq_kg: Optional[float] = None
    observacoes: str = ""


# ======================================================================
#   ENDPOINTS
# ======================================================================

@fragrancias_router.get("/fragrancias")
async def list_fragrancias(
    request: Request,
    search: Optional[str] = None,
    status: Optional[str] = None,
):
    """Lista fragrâncias. Busca por inspiração ou código FR."""
    user = await _get_current_user(request)
    query: dict = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"codigo_interno": {"$regex": search, "$options": "i"}},
            {"inspiracao": {"$regex": search, "$options": "i"}},
            {"fornecedores.codigo_fornecedor": {"$regex": search, "$options": "i"}},
        ]
    cursor = db.fragrancias.find(query, {"_id": 0}).sort("codigo_interno", 1)
    items = await cursor.to_list(500)
    return {"fragrancias": items, "total": len(items)}


@fragrancias_router.get("/fragrancias/{codigo_interno}")
async def get_fragrancia(codigo_interno: str, request: Request):
    user = await _get_current_user(request)
    doc = await db.fragrancias.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Fragrância {codigo_interno} não encontrada")
    return doc


@fragrancias_router.post("/fragrancias", status_code=201)
async def create_fragrancia(data: FragranciaCreate, request: Request):
    """
    Cria novo cadastro de fragrância com código FR-NNNNN gerado automaticamente.
    Inspiração é campo de busca — mesmo nome com composição diferente gera FR distinto.
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    if not data.inspiracao.strip():
        raise HTTPException(status_code=400, detail="Inspiração é obrigatória")

    codigo = await _next_fr_seq(user["tenant_id"])
    now = _now_iso()

    fornecedores = [f.model_dump() for f in data.fornecedores]
    for f in fornecedores:
        f["adicionado_em"] = now
        f["codigo_fornecedor"] = f["codigo_fornecedor"].strip()

    doc = {
        "id": _new_id(),
        "tenant_id": user["tenant_id"],
        "codigo_interno": codigo,
        "inspiracao": data.inspiracao.strip(),
        "descricao": data.descricao.strip(),
        "status": data.status,
        "fornecedores": fornecedores,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.fragrancias.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Fragrância criada: {codigo} — {data.inspiracao}")
    return doc


@fragrancias_router.patch("/fragrancias/{codigo_interno}")
async def update_fragrancia(codigo_interno: str, data: FragranciaUpdate, request: Request):
    """Atualiza campos de texto da fragrância (inspiração, descrição, status)."""
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    existing = await db.fragrancias.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Fragrância {codigo_interno} não encontrada")

    updates: dict = {"updated_at": _now_iso()}
    if data.inspiracao is not None:
        updates["inspiracao"] = data.inspiracao.strip()
    if data.descricao is not None:
        updates["descricao"] = data.descricao.strip()
    if data.status is not None:
        updates["status"] = data.status

    await db.fragrancias.update_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()},
        {"$set": updates},
    )
    updated = await db.fragrancias.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()}, {"_id": 0}
    )
    return updated


@fragrancias_router.post("/fragrancias/{codigo_interno}/fornecedores")
async def add_fornecedor(codigo_interno: str, data: FornecedorRefAdd, request: Request):
    """
    Adiciona ou atualiza cross-reference de fornecedor para uma fragrância.
    Múltiplos códigos de fornecedor mapeiam para o mesmo FR interno.
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    existing = await db.fragrancias.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Fragrância {codigo_interno} não encontrada")

    now = _now_iso()
    novo = data.model_dump()
    novo["adicionado_em"] = now
    novo["codigo_fornecedor"] = novo["codigo_fornecedor"].strip()

    # If supplier+code already exists, replace (update in-place)
    fornecedores = existing.get("fornecedores", [])
    replaced = False
    for i, f in enumerate(fornecedores):
        if f.get("codigo_fornecedor") == novo["codigo_fornecedor"]:
            novo["adicionado_em"] = f.get("adicionado_em", now)
            fornecedores[i] = novo
            replaced = True
            break
    if not replaced:
        fornecedores.append(novo)

    await db.fragrancias.update_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()},
        {"$set": {"fornecedores": fornecedores, "updated_at": now}},
    )
    return {"msg": "Fornecedor atualizado", "codigo_interno": codigo_interno.upper(), "fornecedores": fornecedores}


@fragrancias_router.get("/fragrancias/by-sku/{sku_id}")
async def fragrancias_by_sku(sku_id: str, request: Request):
    """Consulta quais fragrâncias são usadas por um SKU (via BOM do produto-pai)."""
    user = await _get_current_user(request)
    # Query BOM items where tipo=FR and the SKU's produto_pai
    sku = await db.skus.find_one({"id": sku_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")
    produto_pai_id = sku.get("produto_pai_id")
    if not produto_pai_id:
        return {"fragrancias": [], "msg": "SKU sem produto-pai vinculado"}

    bom_items = await db.bom_items.find(
        {"tenant_id": user["tenant_id"], "produto_pai_id": produto_pai_id, "tipo": "FR"},
        {"_id": 0},
    ).to_list(50)

    fr_codes = [item["codigo_material"] for item in bom_items if item.get("codigo_material")]
    fragrancias = []
    for code in fr_codes:
        fr = await db.fragrancias.find_one(
            {"tenant_id": user["tenant_id"], "codigo_interno": code}, {"_id": 0}
        )
        if fr:
            fragrancias.append(fr)

    return {"fragrancias": fragrancias}
