"""
Materiais — Cadastro de Materiais Comprados e Granel (R28 / R29 / R30)
=======================================================================

Esquemas de codificação:
  Materiais comprados: [TIPO2]-[SEQ5]  ex: MP-00347, FR-00089, EP-01203
  Granel / Bulk:       BK-[SEQ5]       ex: BK-00001

Famílias (TIPO2) — lista fechada e governada (ADMIN alçada para novo tipo):
  MP — Matéria-prima   subtipos: Geral, Base, Corante, Álcool, Conservante
  EP — Embalagem Primária   subtipos: Frasco, Tampa, Sobretampa, Válvula, Bomba
  ES — Embalagem Secundária subtipos: Cartucho, Celofane, Sleeve, Caixa de embarque
  RT — Rótulo / Etiqueta    subtipos: Rótulo, Etiqueta
  (FR é gerido em fragrancias_routes.py)

Atributos em campos, nunca no código.
Relações (fornecedor, cliente-proprietário de estoque) nos campos — não no código.
Exibição: código sempre acompanhado de subtipo e, quando aplicável, cross-reference
do fornecedor (R27/R45-display).
"""

import logging
import re
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rbac import require_roles, PD_FULL, ADMIN_ONLY

logger = logging.getLogger(__name__)

materiais_router = APIRouter(prefix="/api/cadastros", tags=["materiais"])

db = None
_get_current_user = None
_new_id = None
_now_iso = None

# ---- TIPO2 canonical list: code → (label, allowed subtipos) ----
TIPO2_CATALOG = {
    "MP": ("Matéria-prima", ["Geral", "Base", "Corante", "Álcool", "Conservante", "Outro"]),
    "EP": ("Embalagem Primária", ["Frasco", "Tampa", "Sobretampa", "Válvula", "Bomba", "Outro"]),
    "ES": ("Embalagem Secundária", ["Cartucho", "Celofane", "Sleeve", "Caixa de embarque", "Outro"]),
    "RT": ("Rótulo / Etiqueta", ["Rótulo", "Etiqueta", "Outro"]),
}
# FR is managed separately in fragrancias_routes.py


def init_materiais(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Materiais module initialized")


async def create_materiais_indexes():
    await db.materiais.create_index([("tenant_id", 1), ("codigo_interno", 1)], unique=True)
    await db.materiais.create_index([("tenant_id", 1), ("tipo2", 1), ("status", 1)])
    await db.materiais.create_index([("tenant_id", 1), ("nome", "text")])
    await db.materiais.create_index(
        [("tenant_id", 1), ("fornecedores.codigo_fornecedor", 1)]
    )
    await db.graneis.create_index([("tenant_id", 1), ("codigo_interno", 1)], unique=True)
    await db.graneis.create_index([("tenant_id", 1), ("produto_pai_id", 1)])
    await db.graneis.create_index([("tenant_id", 1), ("status", 1)])


async def _next_material_seq(tenant_id: str, tipo2: str) -> str:
    """Atomic counter per tenant per tipo2. Returns 'TIPO2-NNNNN'."""
    from workflow_engine import next_sequence
    seq = await next_sequence(tenant_id, f"mat_{tipo2.upper()}_seq", start=0)
    return f"{tipo2.upper()}-{str(seq).zfill(5)}"


async def _next_granel_seq(tenant_id: str) -> str:
    """Atomic counter for BK (granel). Returns 'BK-NNNNN'."""
    from workflow_engine import next_sequence
    seq = await next_sequence(tenant_id, "mat_BK_seq", start=0)
    return f"BK-{str(seq).zfill(5)}"


def _validate_tipo2(tipo2: str, allow_new: bool = False) -> str:
    t = tipo2.upper().strip()
    if not re.match(r"^[A-Z]{2}$", t):
        raise HTTPException(status_code=400, detail="TIPO2 deve ter exatamente 2 letras maiúsculas (ex: MP, EP)")
    if not allow_new and t not in TIPO2_CATALOG:
        allowed = ", ".join(TIPO2_CATALOG.keys())
        raise HTTPException(
            status_code=409,
            detail=f"TIPO2 '{t}' não existe. Tipos disponíveis: {allowed}. Criação de novo tipo requer alçada de admin."
        )
    return t


# ======================================================================
#   SCHEMAS
# ======================================================================

class FornecedorMaterial(BaseModel):
    fornecedor_id: str = ""
    fornecedor_nome: str
    codigo_fornecedor: str
    status_homologacao: str = "em_avaliacao"
    preco_por_unidade: Optional[float] = None
    unidade_compra: str = "kg"
    moeda: str = "BRL"
    lead_time_dias: Optional[int] = None
    moq: Optional[float] = None
    observacoes: str = ""


class MaterialCreate(BaseModel):
    tipo2: str                      # MP, EP, ES, RT
    subtipo: str                    # campo, nunca compõe o código
    nome: str
    descricao: str = ""
    unidade_estoque: str = "kg"     # kg, g, ml, l, un, m, cx
    unidade_compra: str = "kg"
    fator_conversao: float = 1.0    # unidade_estoque por unidade_compra
    # Atributos opcionais por subtipo (campos, não código)
    atributos: dict = {}
    fornecedores: List[FornecedorMaterial] = []


class MaterialUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    subtipo: Optional[str] = None
    unidade_estoque: Optional[str] = None
    unidade_compra: Optional[str] = None
    fator_conversao: Optional[float] = None
    atributos: Optional[dict] = None
    status: Optional[str] = None


class GranelCreate(BaseModel):
    nome: str
    descricao: str = ""
    produto_pai_id: str = ""        # vínculo ao produto-pai (R24)
    unidade_estoque: str = "kg"


class Tipo2Create(BaseModel):
    tipo2: str
    descricao: str
    subtipos: List[str] = []
    justificativa: str


# ======================================================================
#   TIPO2 governance (R28)
# ======================================================================

@materiais_router.get("/materiais/tipos")
async def list_tipos(request: Request):
    """Lista os tipos de material disponíveis (TIPO2 — lista governada)."""
    await _get_current_user(request)
    return {
        "tipos": [
            {"tipo2": k, "descricao": v[0], "subtipos": v[1]}
            for k, v in TIPO2_CATALOG.items()
        ]
    }


@materiais_router.post("/materiais/tipos")
async def create_tipo(data: Tipo2Create, request: Request):
    """
    Cria novo TIPO2 (requer alçada de admin — R28).
    Afeta apenas a configuração do tenant, não insere no TIPO2_CATALOG global.
    """
    user = await _get_current_user(request)
    require_roles(user, ADMIN_ONLY)

    tipo2 = data.tipo2.upper().strip()
    if not re.match(r"^[A-Z]{2}$", tipo2):
        raise HTTPException(status_code=400, detail="TIPO2 deve ter 2 letras maiúsculas")

    existing = await db.material_tipos.find_one({"tenant_id": user["tenant_id"], "tipo2": tipo2})
    if existing or tipo2 in TIPO2_CATALOG:
        nome = existing["descricao"] if existing else TIPO2_CATALOG.get(tipo2, ("?",))[0]
        raise HTTPException(status_code=409, detail=f"TIPO2 '{tipo2}' já existe: {nome}")

    now = _now_iso()
    doc = {
        "id": _new_id(),
        "tenant_id": user["tenant_id"],
        "tipo2": tipo2,
        "descricao": data.descricao.strip(),
        "subtipos": data.subtipos,
        "justificativa": data.justificativa.strip(),
        "criado_por": user.get("name", ""),
        "criado_por_id": user["id"],
        "created_at": now,
    }
    await db.material_tipos.insert_one(doc)
    doc.pop("_id", None)
    return {"tipo": doc, "msg": f"TIPO2 '{tipo2}' criado com sucesso"}


# ======================================================================
#   MATERIAIS COMPRADOS [TIPO2]-[SEQ5]
# ======================================================================

@materiais_router.get("/materiais")
async def list_materiais(
    request: Request,
    tipo2: Optional[str] = None,
    subtipo: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
):
    """Lista materiais comprados com filtros."""
    user = await _get_current_user(request)
    query: dict = {"tenant_id": user["tenant_id"]}
    if tipo2:
        query["tipo2"] = tipo2.upper()
    if subtipo:
        query["subtipo"] = subtipo
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"codigo_interno": {"$regex": search, "$options": "i"}},
            {"nome": {"$regex": search, "$options": "i"}},
            {"fornecedores.codigo_fornecedor": {"$regex": search, "$options": "i"}},
        ]
    cursor = db.materiais.find(query, {"_id": 0}).sort("codigo_interno", 1)
    items = await cursor.to_list(1000)
    return {"materiais": items, "total": len(items)}


@materiais_router.get("/materiais/{codigo_interno}")
async def get_material(codigo_interno: str, request: Request):
    user = await _get_current_user(request)
    doc = await db.materiais.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Material {codigo_interno} não encontrado")
    return doc


@materiais_router.post("/materiais", status_code=201)
async def create_material(data: MaterialCreate, request: Request):
    """
    Cria novo material comprado com código [TIPO2]-[SEQ5].
    Subtipo é campo — nunca compõe o código.
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    tipo2 = _validate_tipo2(data.tipo2)

    if not data.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do material é obrigatório")

    codigo = await _next_material_seq(user["tenant_id"], tipo2)
    now = _now_iso()

    fornecedores = [f.model_dump() for f in data.fornecedores]
    for f in fornecedores:
        f["adicionado_em"] = now

    doc = {
        "id": _new_id(),
        "tenant_id": user["tenant_id"],
        "codigo_interno": codigo,
        "tipo2": tipo2,
        "subtipo": data.subtipo.strip(),
        "nome": data.nome.strip(),
        "descricao": data.descricao.strip(),
        "unidade_estoque": data.unidade_estoque,
        "unidade_compra": data.unidade_compra,
        "fator_conversao": data.fator_conversao,
        "atributos": data.atributos,
        "fornecedores": fornecedores,
        "status": "ativo",
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.materiais.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Material criado: {codigo} — {data.nome}")
    return doc


@materiais_router.patch("/materiais/{codigo_interno}")
async def update_material(codigo_interno: str, data: MaterialUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    existing = await db.materiais.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Material {codigo_interno} não encontrado")

    updates: dict = {"updated_at": _now_iso()}
    for field in ("nome", "descricao", "subtipo", "unidade_estoque", "unidade_compra", "fator_conversao", "atributos", "status"):
        val = getattr(data, field)
        if val is not None:
            updates[field] = val

    await db.materiais.update_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()},
        {"$set": updates},
    )
    updated = await db.materiais.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()}, {"_id": 0}
    )
    return updated


@materiais_router.post("/materiais/{codigo_interno}/fornecedores")
async def add_fornecedor_material(codigo_interno: str, data: FornecedorMaterial, request: Request):
    """Adiciona ou atualiza cross-reference de fornecedor para um material."""
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    existing = await db.materiais.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Material {codigo_interno} não encontrado")

    now = _now_iso()
    novo = data.model_dump()
    novo["adicionado_em"] = now

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

    await db.materiais.update_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()},
        {"$set": {"fornecedores": fornecedores, "updated_at": now}},
    )
    return {"msg": "Fornecedor atualizado", "codigo_interno": codigo_interno.upper()}


# ======================================================================
#   GRANEL / BULK  BK-[SEQ5]
# ======================================================================

@materiais_router.get("/graneis")
async def list_graneis(
    request: Request,
    produto_pai_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """Lista graneis (semi-acabados e standalone)."""
    user = await _get_current_user(request)
    query: dict = {"tenant_id": user["tenant_id"]}
    if produto_pai_id:
        query["produto_pai_id"] = produto_pai_id
    if status:
        query["status"] = status
    cursor = db.graneis.find(query, {"_id": 0}).sort("codigo_interno", 1)
    items = await cursor.to_list(500)
    return {"graneis": items, "total": len(items)}


@materiais_router.get("/graneis/{codigo_interno}")
async def get_granel(codigo_interno: str, request: Request):
    user = await _get_current_user(request)
    doc = await db.graneis.find_one(
        {"tenant_id": user["tenant_id"], "codigo_interno": codigo_interno.upper()},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Granel {codigo_interno} não encontrado")
    return doc


@materiais_router.post("/graneis", status_code=201)
async def create_granel(data: GranelCreate, request: Request):
    """
    Cria novo granel com código BK-[SEQ5].
    Vinculado ao produto-pai (R30) — rastreado como estoque semi-acabado quando standalone.
    """
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    if not data.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do granel é obrigatório")

    codigo = await _next_granel_seq(user["tenant_id"])
    now = _now_iso()

    doc = {
        "id": _new_id(),
        "tenant_id": user["tenant_id"],
        "codigo_interno": codigo,
        "nome": data.nome.strip(),
        "descricao": data.descricao.strip(),
        "produto_pai_id": data.produto_pai_id or None,
        "unidade_estoque": data.unidade_estoque,
        "status": "ativo",
        "standalone": not bool(data.produto_pai_id),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.graneis.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Granel criado: {codigo} — {data.nome}")
    return doc
