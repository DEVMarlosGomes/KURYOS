"""
Materiais — Cadastro de Materiais Comprados e Granel (R28 / R29 / R30)
=======================================================================
PostgreSQL backend (Fase 2 migration). Sem dependências cross-module.
"""

import logging
import re
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from rbac import require_roles, PD_FULL, ADMIN_ONLY
import database as pg_db

logger = logging.getLogger(__name__)

materiais_router = APIRouter(prefix="/api/cadastros", tags=["materiais"])

db = None
_get_current_user = None
_new_id = None
_now_iso = None

TIPO2_CATALOG = {
    "MP": ("Matéria-prima", ["Geral", "Base", "Corante", "Álcool", "Conservante", "Outro"]),
    "EP": ("Embalagem Primária", ["Frasco", "Tampa", "Sobretampa", "Válvula", "Bomba", "Outro"]),
    "ES": ("Embalagem Secundária", ["Cartucho", "Celofane", "Sleeve", "Caixa de embarque", "Outro"]),
    "RT": ("Rótulo / Etiqueta", ["Rótulo", "Etiqueta", "Outro"]),
}


def init_materiais(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    logger.info("Materiais module initialized (PostgreSQL)")


async def create_materiais_indexes():
    pass  # Indexes managed in 002_fase0_fix_schema.sql


# ─── helpers ─────────────────────────────────────────────────────────────────

def _row(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _rows(rows) -> list[dict]:
    return [_row(r) for r in rows]


async def _next_material_seq(tenant_id: str, tipo2: str) -> str:
    from workflow_engine import next_sequence_pg
    seq = await next_sequence_pg(tenant_id, f"mat_{tipo2.upper()}_seq", start=0)
    return f"{tipo2.upper()}-{str(seq).zfill(5)}"


async def _next_granel_seq(tenant_id: str) -> str:
    from workflow_engine import next_sequence_pg
    seq = await next_sequence_pg(tenant_id, "mat_BK_seq", start=0)
    return f"BK-{str(seq).zfill(5)}"


def _validate_tipo2(tipo2: str, allow_new: bool = False) -> str:
    t = tipo2.upper().strip()
    if not re.match(r"^[A-Z]{2}$", t):
        raise HTTPException(status_code=400, detail="TIPO2 deve ter exatamente 2 letras maiúsculas (ex: MP, EP)")
    if not allow_new and t not in TIPO2_CATALOG:
        allowed = ", ".join(TIPO2_CATALOG.keys())
        raise HTTPException(
            status_code=409,
            detail=f"TIPO2 '{t}' não existe. Tipos disponíveis: {allowed}. Criação de novo tipo requer alçada de admin.",
        )
    return t


# ─── schemas ─────────────────────────────────────────────────────────────────

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
    tipo2: str
    subtipo: str
    nome: str
    descricao: str = ""
    unidade_estoque: str = "kg"
    unidade_compra: str = "kg"
    fator_conversao: float = 1.0
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
    produto_pai_id: str = ""
    unidade_estoque: str = "kg"


class Tipo2Create(BaseModel):
    tipo2: str
    descricao: str
    subtipos: List[str] = []
    justificativa: str


# ─── TIPO2 governance ────────────────────────────────────────────────────────

@materiais_router.get("/materiais/tipos")
async def list_tipos(request: Request):
    await _get_current_user(request)
    return {
        "tipos": [
            {"tipo2": k, "descricao": v[0], "subtipos": v[1]}
            for k, v in TIPO2_CATALOG.items()
        ]
    }


@materiais_router.post("/materiais/tipos")
async def create_tipo(data: Tipo2Create, request: Request):
    user = await _get_current_user(request)
    require_roles(user, ADMIN_ONLY)

    tipo2 = data.tipo2.upper().strip()
    if not re.match(r"^[A-Z]{2}$", tipo2):
        raise HTTPException(status_code=400, detail="TIPO2 deve ter 2 letras maiúsculas")

    existing = await pg_db.fetch_one(
        "SELECT id FROM material_tipos WHERE tenant_id=$1 AND tipo2=$2",
        user["tenant_id"], tipo2,
    )
    if existing or tipo2 in TIPO2_CATALOG:
        raise HTTPException(status_code=409, detail=f"TIPO2 '{tipo2}' já existe")

    new_id = _new_id()
    await pg_db.execute(
        """
        INSERT INTO material_tipos(id, tenant_id, nome, descricao, tipo2, subtipos, justificativa, criado_por, criado_por_id, created_at)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
        """,
        new_id, user["tenant_id"],
        data.descricao.strip(), data.descricao.strip(),
        tipo2, data.subtipos, data.justificativa.strip(),
        user.get("name", ""), user["id"],
    )
    doc = _row(await pg_db.fetch_one("SELECT * FROM material_tipos WHERE id=$1", new_id))
    return {"tipo": doc, "msg": f"TIPO2 '{tipo2}' criado com sucesso"}


# ─── materiais comprados ─────────────────────────────────────────────────────

@materiais_router.get("/materiais")
async def list_materiais(
    request: Request,
    tipo2: Optional[str] = None,
    subtipo: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
):
    user = await _get_current_user(request)
    tid = user["tenant_id"]

    conditions = ["tenant_id=$1"]
    params: list = [tid]
    idx = 2

    if tipo2:
        conditions.append(f"tipo2=${idx}")
        params.append(tipo2.upper())
        idx += 1
    if subtipo:
        conditions.append(f"subtipo=${idx}")
        params.append(subtipo)
        idx += 1
    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1
    if search:
        conditions.append(
            f"(codigo_interno ILIKE ${idx} OR nome ILIKE ${idx} OR fornecedores::text ILIKE ${idx})"
        )
        params.append(f"%{search}%")
        idx += 1

    where = " AND ".join(conditions)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM materiais WHERE {where} ORDER BY codigo_interno",
        *params,
    )
    items = _rows(rows)
    return {"materiais": items, "total": len(items)}


@materiais_router.get("/materiais/{codigo_interno}")
async def get_material(codigo_interno: str, request: Request):
    user = await _get_current_user(request)
    row = await pg_db.fetch_one(
        "SELECT * FROM materiais WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Material {codigo_interno} não encontrado")
    return _row(row)


@materiais_router.post("/materiais", status_code=201)
async def create_material(data: MaterialCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    tipo2 = _validate_tipo2(data.tipo2)
    if not data.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do material é obrigatório")

    codigo = await _next_material_seq(user["tenant_id"], tipo2)

    fornecedores = []
    for f in data.fornecedores:
        entry = f.model_dump()
        entry["adicionado_em"] = datetime.utcnow().isoformat()
        fornecedores.append(entry)

    new_id = _new_id()
    await pg_db.execute(
        """
        INSERT INTO materiais(
          id, tenant_id, nome, codigo,
          codigo_interno, tipo2, subtipo, descricao,
          unidade_estoque, unidade, unidade_compra, fator_conversao,
          atributos, fornecedores, status,
          created_by, created_by_name, created_at, updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,'ativo',$15,$16,NOW(),NOW())
        """,
        new_id, user["tenant_id"],
        data.nome.strip(), codigo,
        codigo, tipo2, data.subtipo.strip(), data.descricao.strip(),
        data.unidade_estoque, data.unidade_estoque, data.unidade_compra, data.fator_conversao,
        data.atributos, fornecedores,
        user["id"], user.get("name", ""),
    )
    doc = _row(await pg_db.fetch_one("SELECT * FROM materiais WHERE id=$1", new_id))
    logger.info(f"Material criado: {codigo} — {data.nome}")
    return doc


@materiais_router.patch("/materiais/{codigo_interno}")
async def update_material(codigo_interno: str, data: MaterialUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    existing = await pg_db.fetch_one(
        "SELECT id FROM materiais WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Material {codigo_interno} não encontrado")

    sets = ["updated_at=NOW()"]
    params: list = []
    idx = 1

    field_map = {
        "nome": "nome", "descricao": "descricao", "subtipo": "subtipo",
        "unidade_estoque": "unidade_estoque", "unidade_compra": "unidade_compra",
        "fator_conversao": "fator_conversao", "atributos": "atributos",
        "status": "status",
    }
    for attr, col in field_map.items():
        val = getattr(data, attr)
        if val is not None:
            sets.append(f"{col}=${idx}")
            params.append(val)
            idx += 1

    params += [user["tenant_id"], codigo_interno.upper()]
    await pg_db.execute(
        f"UPDATE materiais SET {', '.join(sets)} WHERE tenant_id=${idx} AND codigo_interno=${idx+1}",
        *params,
    )
    return _row(await pg_db.fetch_one(
        "SELECT * FROM materiais WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    ))


@materiais_router.post("/materiais/{codigo_interno}/fornecedores")
async def add_fornecedor_material(codigo_interno: str, data: FornecedorMaterial, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    row = await pg_db.fetch_one(
        "SELECT id, fornecedores FROM materiais WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Material {codigo_interno} não encontrado")

    novo = data.model_dump()
    fornecedores = list(row["fornecedores"] or [])

    replaced = False
    for i, f in enumerate(fornecedores):
        if f.get("codigo_fornecedor") == novo["codigo_fornecedor"]:
            novo["adicionado_em"] = f.get("adicionado_em", datetime.utcnow().isoformat())
            fornecedores[i] = novo
            replaced = True
            break
    if not replaced:
        novo["adicionado_em"] = datetime.utcnow().isoformat()
        fornecedores.append(novo)

    await pg_db.execute(
        "UPDATE materiais SET fornecedores=$1, updated_at=NOW() WHERE tenant_id=$2 AND codigo_interno=$3",
        fornecedores, user["tenant_id"], codigo_interno.upper(),
    )
    return {"msg": "Fornecedor atualizado", "codigo_interno": codigo_interno.upper()}


# ─── granel / bulk ───────────────────────────────────────────────────────────

@materiais_router.get("/graneis")
async def list_graneis(
    request: Request,
    produto_pai_id: Optional[str] = None,
    status: Optional[str] = None,
):
    user = await _get_current_user(request)
    tid = user["tenant_id"]

    conditions = ["tenant_id=$1"]
    params: list = [tid]
    idx = 2

    if produto_pai_id:
        conditions.append(f"produto_pai_id=${idx}")
        params.append(produto_pai_id)
        idx += 1
    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM graneis WHERE {where} ORDER BY codigo_interno",
        *params,
    )
    items = _rows(rows)
    return {"graneis": items, "total": len(items)}


@materiais_router.get("/graneis/{codigo_interno}")
async def get_granel(codigo_interno: str, request: Request):
    user = await _get_current_user(request)
    row = await pg_db.fetch_one(
        "SELECT * FROM graneis WHERE tenant_id=$1 AND codigo_interno=$2",
        user["tenant_id"], codigo_interno.upper(),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Granel {codigo_interno} não encontrado")
    return _row(row)


@materiais_router.post("/graneis", status_code=201)
async def create_granel(data: GranelCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, PD_FULL)

    if not data.nome.strip():
        raise HTTPException(status_code=400, detail="Nome do granel é obrigatório")

    codigo = await _next_granel_seq(user["tenant_id"])
    new_id = _new_id()
    standalone = not bool(data.produto_pai_id)

    await pg_db.execute(
        """
        INSERT INTO graneis(
          id, tenant_id, nome, codigo,
          codigo_interno, descricao, produto_pai_id,
          unidade_estoque, standalone, status,
          created_by, created_by_name, created_at, updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'ativo',$10,$11,NOW(),NOW())
        """,
        new_id, user["tenant_id"],
        data.nome.strip(), codigo,
        codigo, data.descricao.strip(),
        data.produto_pai_id or None,
        data.unidade_estoque, standalone,
        user["id"], user.get("name", ""),
    )
    doc = _row(await pg_db.fetch_one("SELECT * FROM graneis WHERE id=$1", new_id))
    logger.info(f"Granel criado: {codigo} — {data.nome}")
    return doc
