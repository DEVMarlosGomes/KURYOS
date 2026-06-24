"""
Compras Module — KURYOS ERP (PostgreSQL backend — Fase 4 migration)

Tabelas PostgreSQL (6 coleções novas):
  compras_fornecedores        — cadastro de fornecedores + homologação
  compras_itens               — catálogo de itens compráveis
  compras_condicoes_comerciais — condições de preço/prazo (imutável: sem PUT)
  compras_pos                 — Pedidos de Compra (PO-YYYY-NNN)
  compras_mrp_rodadas         — rodadas de MRP
  compras_demandas            — intermediário MRP → PO

Ainda no MongoDB (cross-module, não migrados):
  ordens_compra / kickoffs / homologacao_fornecedores — LEGADO OC
  estoque_items — WMS (Phase 5)
  workflow_tasks — Workflow Engine
"""
import io
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from rbac import require_roles
from workflow_engine import audit_log, next_sequence_pg, create_workflow_task
import database as pg_db

compras_router = APIRouter(prefix="/api/compras")

db = None          # MongoDB — legado OC + estoque_items (cross-module)
get_current_user = None
new_id_func = None
now_iso_func = None


def init_compras(database, auth_func, id_func, iso_func):
    global db, get_current_user, new_id_func, now_iso_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id() -> str:
    return new_id_func()


def now_iso() -> str:
    return now_iso_func()


async def create_compras_indexes():
    pass  # Indexes managed in 004_compras_schema.sql


# ── Row helpers ───────────────────────────────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════════════════
#   LEGADO — Ordens de Compra vinculadas a Kickoff/BOM  (ainda no MongoDB)
# ══════════════════════════════════════════════════════════════════════════════

OC_STATUSES = {"rascunho", "enviada", "confirmada", "entregue", "cancelada"}
OC_STATUS_LABELS = {
    "rascunho": "Rascunho", "enviada": "Enviada",
    "confirmada": "Confirmada", "entregue": "Entregue", "cancelada": "Cancelada",
}

COMPRAS_WRITE_ROLES = {"admin", "compras", "engenharia_produto"}
COMPRAS_READ_ROLES  = {"admin", "compras", "engenharia_produto", "lider_pd", "qa", "sales_ops"}


class OCCreateInput(BaseModel):
    kickoff_id: str
    bom_item_id: str
    fornecedor_id: str
    quantidade: float
    unidade: str
    preco_unitario_rs: float
    data_necessidade: Optional[str] = None
    observacoes: Optional[str] = ""


class OCUpdateInput(BaseModel):
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    preco_unitario_rs: Optional[float] = None
    data_necessidade: Optional[str] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None
    fornecedor_id: Optional[str] = None


def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _add_business_days(start: datetime, days: int) -> datetime:
    if days <= 0:
        return start
    cursor = start
    remaining = days
    while remaining > 0:
        cursor = cursor - timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return cursor


async def _get_kickoff_or_404(kickoff_id: str, tenant_id: str) -> dict:
    kickoff = await db.kickoffs.find_one({"id": kickoff_id, "tenant_id": tenant_id}, {"_id": 0})
    if not kickoff:
        raise HTTPException(status_code=404, detail="Kickoff nao encontrado.")
    return kickoff


async def _ensure_kickoff_aprovado(kickoff_id: str, tenant_id: str) -> dict:
    kickoff = await _get_kickoff_or_404(kickoff_id, tenant_id)
    if kickoff.get("status") != "aprovado":
        raise HTTPException(
            status_code=400,
            detail=f"Ordem de Compra exige Kickoff aprovado. Status atual: {kickoff.get('status')}.",
        )
    return kickoff


def _find_bom_line(kickoff: dict, bom_item_id: str) -> Optional[Dict[str, Any]]:
    bom = kickoff.get("bom") or []
    for line in bom:
        if line.get("codigo_interno") == bom_item_id or line.get("id") == bom_item_id:
            return line
    return None


async def _ensure_supplier_homologado(fornecedor_id: str, tenant_id: str) -> dict:
    forn = await db.homologacao_fornecedores.find_one(
        {"id": fornecedor_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not forn:
        raise HTTPException(status_code=404, detail="Fornecedor nao encontrado.")
    if forn.get("status") not in {"homologado", "em_avaliacao"}:
        raise HTTPException(
            status_code=400,
            detail=f"Fornecedor com status '{forn.get('status')}' nao pode receber novas Ordens de Compra.",
        )
    return forn


async def _generate_oc_number(tenant_id: str) -> str:
    seq = await next_sequence_pg(tenant_id, "ordem_compra", start=0)
    return f"OC-{datetime.now(timezone.utc).year}-{seq:04d}"


def _calc_data_necessidade(kickoff: dict) -> Optional[str]:
    bloco2 = kickoff.get("bloco2") or {}
    entrega_str = bloco2.get("data_entrega_contratada")
    lead = bloco2.get("lead_time_producao_dias_uteis")
    entrega = _parse_iso_date(entrega_str)
    if not entrega or not lead:
        return None
    necessidade = _add_business_days(entrega, int(lead))
    return necessidade.date().isoformat()


def _decorate_oc(oc: dict) -> dict:
    out = dict(oc)
    out["status_label"] = OC_STATUS_LABELS.get(oc.get("status", ""), oc.get("status", ""))
    return out


@compras_router.get("/boms")
async def list_boms_for_compras(request: Request, kickoff_id: Optional[str] = None):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_READ_ROLES)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"], "status": "aprovado"}
    if kickoff_id:
        query["id"] = kickoff_id
    cursor = db.kickoffs.find(query, {"_id": 0}).sort("approved_at", -1)
    docs = await cursor.to_list(500)
    boms = []
    for ko in docs:
        boms.append({
            "kickoff_id": ko["id"],
            "numero_kickoff": ko.get("numero_kickoff"),
            "cliente": ko.get("cliente"),
            "projeto_vinculado": ko.get("projeto_vinculado"),
            "approved_at": ko.get("approved_at"),
            "bom": ko.get("bom") or [],
        })
    return {"boms": boms, "count": len(boms)}


@compras_router.post("/ordens")
async def create_oc(data: OCCreateInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_WRITE_ROLES)
    kickoff = await _ensure_kickoff_aprovado(data.kickoff_id, user["tenant_id"])
    bom_line = _find_bom_line(kickoff, data.bom_item_id)
    if not bom_line:
        raise HTTPException(
            status_code=400,
            detail=f"Item '{data.bom_item_id}' nao encontrado no BOM do Kickoff {kickoff.get('numero_kickoff')}.",
        )
    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero.")
    if data.preco_unitario_rs < 0:
        raise HTTPException(status_code=400, detail="Preco unitario nao pode ser negativo.")
    fornecedor = await _ensure_supplier_homologado(data.fornecedor_id, user["tenant_id"])
    data_necessidade = data.data_necessidade or _calc_data_necessidade(kickoff)
    numero_oc = await _generate_oc_number(user["tenant_id"])
    oc_doc = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "numero_oc": numero_oc,
        "kickoff_id": kickoff["id"],
        "numero_kickoff": kickoff.get("numero_kickoff"),
        "projeto_id": kickoff.get("projeto_id"),
        "bom_item_id": data.bom_item_id,
        "bom_item_descricao": bom_line.get("descricao"),
        "bom_item_tipo": bom_line.get("tipo"),
        "fornecedor_id": fornecedor["id"],
        "fornecedor_nome": fornecedor.get("razao_social", ""),
        "fornecedor_cnpj": fornecedor.get("cnpj", ""),
        "quantidade": float(data.quantidade),
        "unidade": data.unidade,
        "preco_unitario_rs": float(data.preco_unitario_rs),
        "valor_total_rs": float(data.quantidade) * float(data.preco_unitario_rs),
        "data_necessidade": data_necessidade,
        "status": "rascunho",
        "observacoes": data.observacoes or "",
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "updated_at": now_iso(),
    }
    await db.ordens_compra.insert_one(oc_doc)
    await audit_log(
        tenant_id=user["tenant_id"], user_id=user["id"], user_name=user.get("name", ""),
        action="oc_created", entity_type="ordem_compra", entity_id=oc_doc["id"],
        before=None,
        after={"numero_oc": numero_oc, "kickoff_id": kickoff["id"], "fornecedor_id": fornecedor["id"]},
    )
    oc_doc.pop("_id", None)
    return _decorate_oc(oc_doc)


@compras_router.get("/ordens")
async def list_ocs(
    request: Request,
    status: Optional[str] = None,
    kickoff_id: Optional[str] = None,
    fornecedor_id: Optional[str] = None,
):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_READ_ROLES)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if kickoff_id:
        query["kickoff_id"] = kickoff_id
    if fornecedor_id:
        query["fornecedor_id"] = fornecedor_id
    cursor = db.ordens_compra.find(query, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(1000)
    return {"ordens": [_decorate_oc(d) for d in docs], "count": len(docs)}


@compras_router.get("/ordens/{oc_id}")
async def get_oc(oc_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_READ_ROLES)
    doc = await db.ordens_compra.find_one({"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Ordem de Compra nao encontrada.")
    return _decorate_oc(doc)


@compras_router.put("/ordens/{oc_id}")
async def update_oc(oc_id: str, data: OCUpdateInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, COMPRAS_WRITE_ROLES)
    existing = await db.ordens_compra.find_one({"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Ordem de Compra nao encontrada.")
    if existing.get("status") in {"entregue", "cancelada"}:
        raise HTTPException(
            status_code=400,
            detail=f"Ordem de Compra com status '{existing.get('status')}' nao pode ser editada.",
        )
    update_doc: Dict[str, Any] = {"updated_at": now_iso()}
    payload = data.dict(exclude_unset=True)
    if "status" in payload:
        new_status = payload["status"]
        if new_status not in OC_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status '{new_status}' invalido.")
        update_doc["status"] = new_status
    if "fornecedor_id" in payload and payload["fornecedor_id"]:
        forn = await _ensure_supplier_homologado(payload["fornecedor_id"], user["tenant_id"])
        update_doc["fornecedor_id"] = forn["id"]
        update_doc["fornecedor_nome"] = forn.get("razao_social", "")
        update_doc["fornecedor_cnpj"] = forn.get("cnpj", "")
    for field in ("quantidade", "unidade", "preco_unitario_rs", "data_necessidade", "observacoes"):
        if field in payload:
            update_doc[field] = payload[field]
    if "quantidade" in update_doc or "preco_unitario_rs" in update_doc:
        qtd = update_doc.get("quantidade", existing.get("quantidade", 0))
        preco = update_doc.get("preco_unitario_rs", existing.get("preco_unitario_rs", 0))
        update_doc["valor_total_rs"] = float(qtd) * float(preco)
    await db.ordens_compra.update_one({"id": oc_id, "tenant_id": user["tenant_id"]}, {"$set": update_doc})
    new_doc = await db.ordens_compra.find_one({"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    await audit_log(
        tenant_id=user["tenant_id"], user_id=user["id"], user_name=user.get("name", ""),
        action="oc_updated", entity_type="ordem_compra", entity_id=oc_id,
        before={k: existing.get(k) for k in update_doc.keys()},
        after={k: new_doc.get(k) for k in update_doc.keys()},
    )
    return _decorate_oc(new_doc)


@compras_router.delete("/ordens/{oc_id}")
async def delete_oc(oc_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, {"admin"})
    existing = await db.ordens_compra.find_one({"id": oc_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Ordem de Compra nao encontrada.")
    if existing.get("status") not in {"rascunho", "cancelada"}:
        raise HTTPException(
            status_code=400,
            detail="Apenas Ordens de Compra em rascunho ou canceladas podem ser excluidas.",
        )
    await db.ordens_compra.delete_one({"id": oc_id, "tenant_id": user["tenant_id"]})
    await audit_log(
        tenant_id=user["tenant_id"], user_id=user["id"], user_name=user.get("name", ""),
        action="oc_deleted", entity_type="ordem_compra", entity_id=oc_id,
        before=existing, after=None,
    )
    return {"deleted": True}


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 1 — ENTIDADES (6 tabelas PostgreSQL + índices)
# ══════════════════════════════════════════════════════════════════════════════

CATEGORIAS_FORNECEDOR = {
    "MP Química", "Fragrância", "Frasco", "Tampa", "Válvula",
    "Rótulo", "Cartucho", "Display", "Caixa", "Celofane", "Outros",
}

STATUS_HOMOLOGACAO = {"nao_iniciada", "em_processo", "homologado", "suspenso", "reprovado"}
STATUS_CADASTRO    = {"ativo", "inativo", "bloqueado"}
STATUS_PO          = {"rascunho", "emitida", "confirmada", "parcialmente_recebida", "recebida", "encerrada", "cancelada"}
STATUS_MRP         = {"gerada", "em_revisao", "aprovada", "parcialmente_aprovada", "descartada"}
STATUS_DEMANDA     = {"pendente", "em_cotacao", "po_emitida", "cancelada"}

_CMP_FULL   = {"admin", "compras"}
_CMP_CQ     = {"admin", "qa", "lider_pd", "compras"}
_CMP_WRITE  = {"admin", "compras", "engenharia_produto"}
_CMP_READ   = {"admin", "compras", "engenharia_produto", "lider_pd", "qa", "sales_ops"}


# ── 405 guards — novas coleções nunca deletam ──────────────────────────────────

@compras_router.delete("/fornecedores/{forn_id}")
async def bloquear_delete_fornecedor(forn_id: str):
    raise HTTPException(
        status_code=405,
        detail="Fornecedores não podem ser excluídos. Use inativação (status_cadastro=inativo) ou bloqueio.",
    )


@compras_router.delete("/itens/{item_id}")
async def bloquear_delete_item(item_id: str):
    raise HTTPException(status_code=405, detail="Itens não podem ser excluídos.")


@compras_router.delete("/condicoes-comerciais/{cond_id}")
async def bloquear_delete_condicao(cond_id: str):
    raise HTTPException(status_code=405, detail="Condições comerciais são imutáveis e não podem ser excluídas.")


@compras_router.delete("/pos/{po_id}")
async def bloquear_delete_po(po_id: str):
    raise HTTPException(status_code=405, detail="POs não podem ser excluídas. Cancele com motivo registrado.")


@compras_router.delete("/mrp/{mrp_id}")
async def bloquear_delete_mrp(mrp_id: str):
    raise HTTPException(status_code=405, detail="Rodadas MRP não podem ser excluídas.")


# ── Demandas list/detail ───────────────────────────────────────────────────────

@compras_router.get("/demandas")
async def listar_demandas(
    request: Request,
    status: Optional[str] = Query(None),
    mrp_rodada_id: Optional[str] = Query(None),
    urgente: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2

    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1
    if mrp_rodada_id:
        conditions.append(f"mrp_rodada_id=${idx}")
        params.append(mrp_rodada_id)
        idx += 1
    if urgente is not None:
        conditions.append(f"urgente=${idx}")
        params.append(urgente)
        idx += 1

    where = " AND ".join(conditions)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM compras_demandas WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM compras_demandas WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"demandas": _rows(rows), "total": total, "limit": limit, "offset": offset}


@compras_router.get("/demandas/{demanda_id}")
async def detalhar_demanda(demanda_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    row = await pg_db.fetch_one(
        "SELECT * FROM compras_demandas WHERE id=$1 AND tenant_id=$2",
        demanda_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Demanda não encontrada.")
    return _row(row)


@compras_router.delete("/demandas/{demanda_id}")
async def bloquear_delete_demanda(demanda_id: str):
    raise HTTPException(status_code=405, detail="Demandas não podem ser excluídas.")


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 2 — FORNECEDORES (CRUD + Homologação)  [PostgreSQL]
# ══════════════════════════════════════════════════════════════════════════════

# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_cnpj(cnpj: str) -> bool:
    digits = re.sub(r"\D", "", cnpj)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def _digit(nums: str, weights: List[int]) -> int:
        s = sum(int(n) * w for n, w in zip(nums, weights))
        r = s % 11
        return 0 if r < 2 else 11 - r

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return (
        int(digits[12]) == _digit(digits[:12], w1)
        and int(digits[13]) == _digit(digits[:13], w2)
    )


def _normalize_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


async def _next_for_code(tenant_id: str) -> str:
    seq = await next_sequence_pg(tenant_id, "compras_fornecedores", start=0)
    return f"FOR-{seq:04d}"


async def _get_for_or_404(forn_id: str, tenant_id: str) -> dict:
    row = await pg_db.fetch_one(
        "SELECT * FROM compras_fornecedores WHERE id=$1 AND tenant_id=$2",
        forn_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    return _row(row)


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _date_plus_days(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


# ── Pydantic models ────────────────────────────────────────────────────────────

class EnderecoInput(BaseModel):
    cep: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""


class ContatoInput(BaseModel):
    nome: str
    cargo: str = ""
    telefone: str = ""
    email: str = ""
    whatsapp: str = ""
    principal_compras: bool = False


class FornecedorCreate(BaseModel):
    razao_social: str
    nome_fantasia: str = ""
    cnpj: str
    ie: str = ""
    im: str = ""
    endereco: Optional[EnderecoInput] = None
    contatos: List[ContatoInput] = []
    categorias: List[str] = []


class FornecedorUpdate(BaseModel):
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    ie: Optional[str] = None
    im: Optional[str] = None
    endereco: Optional[EnderecoInput] = None
    contatos: Optional[List[ContatoInput]] = None
    categorias: Optional[List[str]] = None
    status_cadastro: Optional[str] = None


class HomologacaoDecidirInput(BaseModel):
    decisao: str
    justificativa: Optional[str] = None
    validade_dias: int = 365


class HomologacaoSuspenderInput(BaseModel):
    motivo: str


class IncrementarRNCInput(BaseModel):
    rnc_id: str
    classificacao: str


# ── POST /fornecedores ─────────────────────────────────────────────────────────

@compras_router.post("/fornecedores", status_code=201)
async def criar_fornecedor(data: FornecedorCreate, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_WRITE)
    tenant_id = user["tenant_id"]

    if not _validate_cnpj(data.cnpj):
        raise HTTPException(status_code=422, detail="CNPJ inválido — dígito verificador incorreto.")

    cnpj_norm = _normalize_cnpj(data.cnpj)
    existing = await pg_db.fetch_one(
        "SELECT id FROM compras_fornecedores WHERE tenant_id=$1 AND cnpj_normalizado=$2",
        tenant_id, cnpj_norm,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"CNPJ já cadastrado (fornecedor: {existing['id']}).",
        )

    codigo_interno = await _next_for_code(tenant_id)
    forn_id = new_id()
    contatos = [{**c.dict(), "id": new_id()} for c in data.contatos]

    log_entry = {
        "acao": "fornecedor_criado",
        "por_id": user["id"],
        "por_nome": user.get("name", ""),
        "em": now_iso(),
    }

    await pg_db.execute(
        """INSERT INTO compras_fornecedores(
            id, tenant_id, codigo_interno, razao_social, nome_fantasia,
            cnpj, cnpj_normalizado, ie, im,
            endereco, contatos, categorias, homologacao,
            status_cadastro, log_auditoria, created_at, updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW(),NOW())""",
        forn_id, tenant_id, codigo_interno,
        data.razao_social, data.nome_fantasia,
        data.cnpj, cnpj_norm,
        data.ie, data.im,
        data.endereco.dict() if data.endereco else {},
        contatos,
        data.categorias,
        {
            "status": "nao_iniciada",
            "data_homologacao": None,
            "proxima_reavaliacao": None,
            "documentos_file_ids": [],
            "historico_rncs_count": 0,
            "historico_rncs_criticas_12m": 0,
        },
        "ativo",
        [log_entry],
    )
    return await _get_for_or_404(forn_id, tenant_id)


# ── GET /fornecedores ──────────────────────────────────────────────────────────

@compras_router.get("/fornecedores")
async def listar_fornecedores(
    request: Request,
    status_homologacao: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    status_cadastro: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2

    if status_homologacao:
        conditions.append(f"homologacao->>'status' = ${idx}")
        params.append(status_homologacao)
        idx += 1
    if categoria:
        conditions.append(f"categorias @> ${idx}::jsonb")
        params.append([categoria])
        idx += 1
    if status_cadastro:
        conditions.append(f"status_cadastro = ${idx}")
        params.append(status_cadastro)
        idx += 1
    if q:
        conditions.append(
            f"(razao_social ILIKE ${idx} OR nome_fantasia ILIKE ${idx} "
            f"OR cnpj_normalizado ILIKE ${idx} OR codigo_interno ILIKE ${idx})"
        )
        params.append(f"%{q}%")
        idx += 1

    where = " AND ".join(conditions)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM compras_fornecedores WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM compras_fornecedores WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"fornecedores": _rows(rows), "total": total, "limit": limit, "offset": offset}


# ── GET /fornecedores/{id} ─────────────────────────────────────────────────────

@compras_router.get("/fornecedores/{forn_id}")
async def detalhar_fornecedor(forn_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    return await _get_for_or_404(forn_id, user["tenant_id"])


# ── PUT /fornecedores/{id} ─────────────────────────────────────────────────────

@compras_router.put("/fornecedores/{forn_id}")
async def atualizar_fornecedor(forn_id: str, data: FornecedorUpdate, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_WRITE)
    tenant_id = user["tenant_id"]

    await _get_for_or_404(forn_id, tenant_id)

    payload = data.dict(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    if "status_cadastro" in payload and payload["status_cadastro"] not in STATUS_CADASTRO:
        raise HTTPException(
            status_code=422,
            detail=f"status_cadastro inválido. Use: {sorted(STATUS_CADASTRO)}",
        )

    log_entry = {
        "acao": "cadastro_atualizado",
        "campos": list(payload.keys()),
        "por_id": user["id"],
        "por_nome": user.get("name", ""),
        "em": now_iso(),
    }

    sets = ["updated_at=NOW()"]
    params: list = []
    idx = 1

    for field in ("razao_social", "nome_fantasia", "ie", "im", "categorias", "status_cadastro"):
        if field in payload:
            sets.append(f"{field}=${idx}")
            params.append(payload[field])
            idx += 1

    if "endereco" in payload and payload["endereco"] is not None:
        sets.append(f"endereco=${idx}")
        params.append(payload["endereco"])
        idx += 1

    if "contatos" in payload and payload["contatos"] is not None:
        contatos_novos = []
        for c in payload["contatos"]:
            c.setdefault("id", new_id())
            contatos_novos.append(c)
        sets.append(f"contatos=${idx}")
        params.append(contatos_novos)
        idx += 1

    sets.append(f"log_auditoria = log_auditoria || ${idx}::jsonb")
    params.append([log_entry])
    idx += 1

    params += [forn_id, tenant_id]
    await pg_db.execute(
        f"UPDATE compras_fornecedores SET {', '.join(sets)} WHERE id=${idx} AND tenant_id=${idx+1}",
        *params,
    )
    return await _get_for_or_404(forn_id, tenant_id)


# ── POST /fornecedores/{id}/homologacao/iniciar ───────────────────────────────

@compras_router.post("/fornecedores/{forn_id}/homologacao/iniciar")
async def iniciar_homologacao(forn_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_WRITE)
    tenant_id = user["tenant_id"]

    doc = await _get_for_or_404(forn_id, tenant_id)
    status_atual = (doc.get("homologacao") or {}).get("status", "nao_iniciada")
    if status_atual in {"em_processo", "homologado"}:
        raise HTTPException(
            status_code=400,
            detail=f"Processo de homologação já está '{status_atual}'. Não é possível reiniciar.",
        )

    log_entry = {
        "acao": "homologacao_iniciada",
        "por_id": user["id"],
        "por_nome": user.get("name", ""),
        "em": now_iso(),
    }
    await pg_db.execute(
        """UPDATE compras_fornecedores
           SET homologacao = homologacao || $1::jsonb,
               log_auditoria = log_auditoria || $2::jsonb,
               updated_at = NOW()
           WHERE id=$3 AND tenant_id=$4""",
        {"status": "em_processo"},
        [log_entry],
        forn_id, tenant_id,
    )

    await create_workflow_task(
        tenant_id=tenant_id,
        entity_type="compras_fornecedor",
        entity_id=forn_id,
        title=f"CMP-08 Homologar Fornecedor — {doc['codigo_interno']} {doc['razao_social']}",
        description=(
            f"Processo de homologação iniciado para {doc['razao_social']} ({doc['cnpj']}). "
            f"Avalie documentação, realize auditoria e decida: homologado ou reprovado."
        ),
        category="qa",
        blocking=False,
        due_in_days=30,
        created_by=user,
        metadata={"task_type": "approval", "module_origin": "compras"},
    )
    return await _get_for_or_404(forn_id, tenant_id)


# ── POST /fornecedores/{id}/homologacao/decidir ───────────────────────────────

@compras_router.post("/fornecedores/{forn_id}/homologacao/decidir")
async def decidir_homologacao(forn_id: str, data: HomologacaoDecidirInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_CQ)
    tenant_id = user["tenant_id"]

    if data.decisao not in {"homologado", "reprovado"}:
        raise HTTPException(status_code=422, detail="decisao deve ser 'homologado' ou 'reprovado'.")
    if data.decisao == "reprovado" and not (data.justificativa or "").strip():
        raise HTTPException(status_code=422, detail="justificativa é obrigatória quando decisao=reprovado.")

    doc = await _get_for_or_404(forn_id, tenant_id)
    status_atual = (doc.get("homologacao") or {}).get("status", "nao_iniciada")
    if status_atual != "em_processo":
        raise HTTPException(
            status_code=400,
            detail=f"Homologação só pode ser decidida quando status='em_processo'. Status atual: '{status_atual}'.",
        )

    hoje = _today_iso()
    hom_patch: Dict[str, Any] = {"status": data.decisao}
    if data.decisao == "homologado":
        proxima = _date_plus_days(data.validade_dias)
        hom_patch["data_homologacao"] = hoje
        hom_patch["proxima_reavaliacao"] = proxima

    log_entry = {
        "acao": f"homologacao_{data.decisao}",
        "justificativa": data.justificativa or "",
        "por_id": user["id"],
        "por_nome": user.get("name", ""),
        "em": now_iso(),
    }
    await pg_db.execute(
        """UPDATE compras_fornecedores
           SET homologacao = homologacao || $1::jsonb,
               log_auditoria = log_auditoria || $2::jsonb,
               updated_at = NOW()
           WHERE id=$3 AND tenant_id=$4""",
        hom_patch, [log_entry], forn_id, tenant_id,
    )

    if data.decisao == "homologado":
        proxima = hom_patch["proxima_reavaliacao"]
        await create_workflow_task(
            tenant_id=tenant_id,
            entity_type="compras_fornecedor",
            entity_id=forn_id,
            title=f"CMP-09 Reavaliar Fornecedor — {doc['codigo_interno']} {doc['razao_social']}",
            description=(
                f"Reavaliação periódica de {doc['razao_social']} programada para {proxima}. "
                f"Verifique documentação, RNCs e performance de entrega."
            ),
            category="qa",
            blocking=False,
            due_in_days=max(data.validade_dias - 30, 1),
            created_by=user,
            metadata={"task_type": "standard", "module_origin": "compras", "data_reavaliacao": proxima},
        )
    return await _get_for_or_404(forn_id, tenant_id)


# ── POST /fornecedores/{id}/homologacao/suspender ─────────────────────────────

@compras_router.post("/fornecedores/{forn_id}/homologacao/suspender")
async def suspender_homologacao(forn_id: str, data: HomologacaoSuspenderInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_CQ)
    tenant_id = user["tenant_id"]

    if not data.motivo.strip():
        raise HTTPException(status_code=422, detail="motivo é obrigatório para suspender.")

    doc = await _get_for_or_404(forn_id, tenant_id)
    if (doc.get("homologacao") or {}).get("status") == "suspenso":
        raise HTTPException(status_code=400, detail="Fornecedor já está suspenso.")

    log_entry = {
        "acao": "homologacao_suspensa",
        "motivo": data.motivo.strip(),
        "por_id": user["id"],
        "por_nome": user.get("name", ""),
        "em": now_iso(),
    }
    await pg_db.execute(
        """UPDATE compras_fornecedores
           SET homologacao = homologacao || $1::jsonb,
               log_auditoria = log_auditoria || $2::jsonb,
               updated_at = NOW()
           WHERE id=$3 AND tenant_id=$4""",
        {"status": "suspenso"}, [log_entry], forn_id, tenant_id,
    )
    return await _get_for_or_404(forn_id, tenant_id)


# ── POST /fornecedores/{id}/incrementar-rnc ───────────────────────────────────

@compras_router.post("/fornecedores/{forn_id}/incrementar-rnc")
async def incrementar_rnc(forn_id: str, data: IncrementarRNCInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_CQ | {"qa"})
    tenant_id = user["tenant_id"]

    doc = await _get_for_or_404(forn_id, tenant_id)
    hom = dict(doc.get("homologacao") or {})
    hom["historico_rncs_count"] = hom.get("historico_rncs_count", 0) + 1
    if data.classificacao == "critica":
        hom["historico_rncs_criticas_12m"] = hom.get("historico_rncs_criticas_12m", 0) + 1

    log_entry = {
        "acao": "rnc_registrada",
        "rnc_id": data.rnc_id,
        "classificacao": data.classificacao,
        "por_id": user["id"],
        "por_nome": user.get("name", ""),
        "em": now_iso(),
    }
    await pg_db.execute(
        """UPDATE compras_fornecedores
           SET homologacao=$1,
               log_auditoria = log_auditoria || $2::jsonb,
               updated_at = NOW()
           WHERE id=$3 AND tenant_id=$4""",
        hom, [log_entry], forn_id, tenant_id,
    )

    doc_atualizado = await _get_for_or_404(forn_id, tenant_id)
    hom_atual = doc_atualizado.get("homologacao") or {}
    criticas_12m = hom_atual.get("historico_rncs_criticas_12m", 0)

    if criticas_12m >= 3 and hom_atual.get("status") != "suspenso":
        motivo_auto = (
            f"Suspensão automática: {criticas_12m} RNCs críticas nos últimos 12 meses "
            f"(última: RNC {data.rnc_id})."
        )
        log_suspensao = {
            "acao": "homologacao_suspensa_automatica",
            "motivo": motivo_auto,
            "rnc_id": data.rnc_id,
            "por_id": "sistema",
            "por_nome": "Sistema Automático",
            "em": now_iso(),
        }
        await pg_db.execute(
            """UPDATE compras_fornecedores
               SET homologacao = homologacao || $1::jsonb,
                   log_auditoria = log_auditoria || $2::jsonb,
                   updated_at = NOW()
               WHERE id=$3 AND tenant_id=$4""",
            {"status": "suspenso"}, [log_suspensao], forn_id, tenant_id,
        )
        await create_workflow_task(
            tenant_id=tenant_id,
            entity_type="compras_fornecedor",
            entity_id=forn_id,
            title=f"CMP-10 Fornecedor Suspenso Automaticamente — {doc['codigo_interno']} {doc['razao_social']}",
            description=(
                f"{doc['razao_social']} foi suspenso automaticamente após {criticas_12m} RNCs críticas "
                f"em 12 meses. Última: RNC {data.rnc_id}. "
                f"Avalie situação e decida sobre continuidade ou reprovação definitiva."
            ),
            category="qa",
            blocking=False,
            due_in_days=3,
            created_by=user,
            metadata={"task_type": "approval", "module_origin": "compras", "motivo": motivo_auto},
        )
        doc_atualizado = await _get_for_or_404(forn_id, tenant_id)

    return doc_atualizado


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 3 — ITENS DE COMPRA + CONDIÇÕES COMERCIAIS  [PostgreSQL]
# ══════════════════════════════════════════════════════════════════════════════

CATEGORIAS_ITEM = {"mp", "fragrancia", "embalagem"}
FRETES_VALIDOS  = {"cif", "fob", "valor_fixo", "percentual"}


# ── Pydantic models ────────────────────────────────────────────────────────────

class ItemCompraCreate(BaseModel):
    codigo_interno: str
    descricao: str
    categoria: str
    sub_categoria: str = ""
    unidade_compra: str
    fator_conversao_producao: float = 1.0
    estoque_minimo: Optional[float] = None
    estoque_seguranca: float = 0.0
    lead_time_dias: int = 0
    requer_homologacao_cq: bool = True
    fornecedores_homologados: List[str] = []


class ItemCompraUpdate(BaseModel):
    descricao: Optional[str] = None
    sub_categoria: Optional[str] = None
    unidade_compra: Optional[str] = None
    fator_conversao_producao: Optional[float] = None
    estoque_minimo: Optional[float] = None
    estoque_seguranca: Optional[float] = None
    lead_time_dias: Optional[int] = None
    requer_homologacao_cq: Optional[bool] = None
    fornecedores_homologados: Optional[List[str]] = None


class CotacaoCreate(BaseModel):
    fornecedor_id: str
    preco_unitario: float
    preco_unitario_currency: str = "BRL"
    prazo_pagamento_texto: str
    prazo_pagamento_dias: int
    prazo_entrega_dias_uteis: int
    moq: float = 1.0
    frete_tipo: str
    frete_valor: float = 0.0
    valido_ate: Optional[str] = None
    cotado_por_nome: Optional[str] = None


# ── PUT /condicoes-comerciais/{id} → 405 ─────────────────────────────────────

@compras_router.put("/condicoes-comerciais/{cond_id}")
async def bloquear_put_condicao(cond_id: str):
    raise HTTPException(
        status_code=405,
        detail="Condições comerciais são imutáveis após criação. Registre uma nova cotação com POST /itens/{id}/cotar.",
    )


# ── POST /itens ───────────────────────────────────────────────────────────────

@compras_router.post("/itens", status_code=201)
async def criar_item(data: ItemCompraCreate, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_WRITE)
    tenant_id = user["tenant_id"]

    if data.categoria not in CATEGORIAS_ITEM:
        raise HTTPException(
            status_code=422,
            detail=f"categoria inválida. Use: {sorted(CATEGORIAS_ITEM)}",
        )

    existing = await pg_db.fetch_one(
        "SELECT id FROM compras_itens WHERE tenant_id=$1 AND codigo_interno=$2",
        tenant_id, data.codigo_interno,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Item com codigo_interno '{data.codigo_interno}' já existe.",
        )

    item_id = new_id()
    await pg_db.execute(
        """INSERT INTO compras_itens(
            id, tenant_id, codigo_interno, descricao, categoria,
            sub_categoria, unidade_compra, fator_conversao_producao,
            estoque_minimo, estoque_seguranca, lead_time_dias,
            requer_homologacao_cq, fornecedores_homologados, created_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())""",
        item_id, tenant_id,
        data.codigo_interno, data.descricao, data.categoria,
        data.sub_categoria, data.unidade_compra, data.fator_conversao_producao,
        data.estoque_minimo, data.estoque_seguranca, data.lead_time_dias,
        data.requer_homologacao_cq, data.fornecedores_homologados,
    )
    row = await pg_db.fetch_one("SELECT * FROM compras_itens WHERE id=$1", item_id)
    return _row(row)


# ── GET /itens ────────────────────────────────────────────────────────────────

@compras_router.get("/itens")
async def listar_itens(
    request: Request,
    categoria: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2

    if categoria:
        conditions.append(f"categoria=${idx}")
        params.append(categoria)
        idx += 1
    if q:
        conditions.append(f"(descricao ILIKE ${idx} OR codigo_interno ILIKE ${idx})")
        params.append(f"%{q}%")
        idx += 1

    where = " AND ".join(conditions)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM compras_itens WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM compras_itens WHERE {where} ORDER BY descricao ASC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"itens": _rows(rows), "total": total, "limit": limit, "offset": offset}


# ── GET /itens/{id} ───────────────────────────────────────────────────────────

@compras_router.get("/itens/{item_id}")
async def detalhar_item(item_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM compras_itens WHERE id=$1 AND tenant_id=$2",
        item_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    doc = _row(row)

    # Última cotação por fornecedor
    conds = await pg_db.fetch_all(
        "SELECT * FROM compras_condicoes_comerciais WHERE tenant_id=$1 AND item_id=$2 ORDER BY created_at DESC",
        tenant_id, item_id,
    )
    conds_list = _rows(conds)

    ultimas_condicoes: Dict[str, dict] = {}
    for c in conds_list:
        fid = c.get("fornecedor_id")
        if fid and fid not in ultimas_condicoes:
            ultimas_condicoes[fid] = c

    fornecedores_info = []
    for fid, cond in ultimas_condicoes.items():
        forn_row = await pg_db.fetch_one(
            "SELECT razao_social, codigo_interno, homologacao FROM compras_fornecedores WHERE id=$1 AND tenant_id=$2",
            fid, tenant_id,
        )
        forn = _row(forn_row) if forn_row else None
        fornecedores_info.append({
            "fornecedor_id": fid,
            "razao_social": (forn or {}).get("razao_social", ""),
            "codigo_interno": (forn or {}).get("codigo_interno", ""),
            "status_homologacao": ((forn or {}).get("homologacao") or {}).get("status", ""),
            "ultima_cotacao": cond,
        })

    # Último preço pago via POs
    ultimo_preco_pago = None
    po_row = await pg_db.fetch_one(
        """SELECT * FROM compras_pos
           WHERE tenant_id=$1
             AND status = ANY($2::text[])
             AND EXISTS (
               SELECT 1 FROM jsonb_array_elements(itens) AS e WHERE e->>'item_id' = $3
             )
           ORDER BY created_at DESC LIMIT 1""",
        tenant_id, ["recebida", "encerrada"], item_id,
    )
    if po_row:
        po = _row(po_row)
        for it in (po.get("itens") or []):
            if it.get("item_id") == item_id:
                ultimo_preco_pago = it.get("preco_unitario")
                break

    return {
        **doc,
        "ultimo_preco_pago": ultimo_preco_pago,
        "fornecedores": fornecedores_info,
        "total_cotacoes": len(conds_list),
    }


# ── PUT /itens/{id} ───────────────────────────────────────────────────────────

@compras_router.put("/itens/{item_id}")
async def atualizar_item(item_id: str, data: ItemCompraUpdate, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_WRITE)
    tenant_id = user["tenant_id"]

    existing = await pg_db.fetch_one(
        "SELECT id FROM compras_itens WHERE id=$1 AND tenant_id=$2",
        item_id, tenant_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    payload = data.dict(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    sets = []
    params: list = []
    idx = 1
    field_map = {
        "descricao": "descricao", "sub_categoria": "sub_categoria",
        "unidade_compra": "unidade_compra",
        "fator_conversao_producao": "fator_conversao_producao",
        "estoque_minimo": "estoque_minimo", "estoque_seguranca": "estoque_seguranca",
        "lead_time_dias": "lead_time_dias",
        "requer_homologacao_cq": "requer_homologacao_cq",
        "fornecedores_homologados": "fornecedores_homologados",
    }
    for attr, col in field_map.items():
        if attr in payload:
            sets.append(f"{col}=${idx}")
            params.append(payload[attr])
            idx += 1

    if not sets:
        raise HTTPException(status_code=400, detail="Nenhum campo válido para atualizar.")

    params += [tenant_id, item_id]
    await pg_db.execute(
        f"UPDATE compras_itens SET {', '.join(sets)} WHERE tenant_id=${idx} AND id=${idx+1}",
        *params,
    )
    row = await pg_db.fetch_one(
        "SELECT * FROM compras_itens WHERE id=$1 AND tenant_id=$2", item_id, tenant_id,
    )
    return _row(row)


# ── POST /itens/{id}/cotar ───────────────────────────────────────────────────

@compras_router.post("/itens/{item_id}/cotar", status_code=201)
async def registrar_cotacao(item_id: str, data: CotacaoCreate, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_WRITE)
    tenant_id = user["tenant_id"]

    item_row = await pg_db.fetch_one(
        "SELECT id, descricao FROM compras_itens WHERE id=$1 AND tenant_id=$2",
        item_id, tenant_id,
    )
    if not item_row:
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    forn_row = await pg_db.fetch_one(
        "SELECT id, razao_social FROM compras_fornecedores WHERE id=$1 AND tenant_id=$2",
        data.fornecedor_id, tenant_id,
    )
    if not forn_row:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")

    if data.frete_tipo not in FRETES_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"frete_tipo inválido. Use: {sorted(FRETES_VALIDOS)}",
        )

    hoje = _today_iso()
    if data.valido_ate and data.valido_ate < hoje:
        raise HTTPException(
            status_code=422,
            detail=f"data de validade já expirada ({data.valido_ate} < {hoje}).",
        )

    cond_id = new_id()
    await pg_db.execute(
        """INSERT INTO compras_condicoes_comerciais(
            id, tenant_id, fornecedor_id, fornecedor_nome,
            item_id, item_descricao,
            preco_unitario, preco_unitario_currency,
            prazo_pagamento_texto, prazo_pagamento_dias,
            prazo_entrega_dias_uteis, moq,
            frete_tipo, frete_valor, valido_ate, origem,
            cotado_por_id, cotado_por_nome, created_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,NOW())""",
        cond_id, tenant_id,
        data.fornecedor_id, forn_row["razao_social"],
        item_id, item_row["descricao"],
        float(data.preco_unitario), data.preco_unitario_currency,
        data.prazo_pagamento_texto, data.prazo_pagamento_dias,
        data.prazo_entrega_dias_uteis, float(data.moq),
        data.frete_tipo, float(data.frete_valor),
        data.valido_ate, "manual",
        user["id"], data.cotado_por_nome or user.get("name", ""),
    )
    row = await pg_db.fetch_one("SELECT * FROM compras_condicoes_comerciais WHERE id=$1", cond_id)
    return _row(row)


# ── GET /itens/{id}/historico-precos ─────────────────────────────────────────

@compras_router.get("/itens/{item_id}/historico-precos")
async def historico_precos(item_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    item_row = await pg_db.fetch_one(
        "SELECT * FROM compras_itens WHERE id=$1 AND tenant_id=$2", item_id, tenant_id,
    )
    if not item_row:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    item = _row(item_row)

    todas_rows = await pg_db.fetch_all(
        "SELECT * FROM compras_condicoes_comerciais WHERE tenant_id=$1 AND item_id=$2 ORDER BY created_at DESC",
        tenant_id, item_id,
    )
    todas = _rows(todas_rows)

    por_forn: Dict[str, List[dict]] = {}
    for c in todas:
        por_forn.setdefault(c["fornecedor_id"], []).append(c)

    historico_com_variacao: List[dict] = []
    for fid, conds in por_forn.items():
        for i, c in enumerate(conds):
            c_out = dict(c)
            if i < len(conds) - 1:
                preco_anterior = conds[i + 1].get("preco_unitario", 0)
                preco_atual = c.get("preco_unitario", 0)
                if preco_anterior and preco_anterior > 0:
                    c_out["variacao_pct"] = round(
                        (preco_atual - preco_anterior) / preco_anterior * 100, 2
                    )
                else:
                    c_out["variacao_pct"] = None
            else:
                c_out["variacao_pct"] = None
            historico_com_variacao.append(c_out)

    historico_com_variacao.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # Último preço pago
    ultimo_preco_pago = None
    ultimo_preco_data = None
    po_row = await pg_db.fetch_one(
        """SELECT * FROM compras_pos
           WHERE tenant_id=$1
             AND status = ANY($2::text[])
             AND EXISTS (
               SELECT 1 FROM jsonb_array_elements(itens) AS e WHERE e->>'item_id' = $3
             )
           ORDER BY created_at DESC LIMIT 1""",
        tenant_id, ["recebida", "encerrada"], item_id,
    )
    if po_row:
        po = _row(po_row)
        for it in (po.get("itens") or []):
            if it.get("item_id") == item_id:
                ultimo_preco_pago = it.get("preco_unitario")
                ultimo_preco_data = po.get("data_emissao") or po.get("created_at")
                break

    # Comparativo por fornecedor
    comparativo_fornecedores: List[dict] = []
    for fid, conds in por_forn.items():
        ultima = conds[0]
        forn_row = await pg_db.fetch_one(
            "SELECT razao_social, codigo_interno, homologacao FROM compras_fornecedores WHERE id=$1 AND tenant_id=$2",
            fid, tenant_id,
        )
        forn = _row(forn_row) if forn_row else None
        comparativo_fornecedores.append({
            "fornecedor_id": fid,
            "fornecedor_nome": ultima.get("fornecedor_nome", ""),
            "fornecedor_codigo": (forn or {}).get("codigo_interno", ""),
            "status_homologacao": ((forn or {}).get("homologacao") or {}).get("status", ""),
            "ultimo_preco": ultima.get("preco_unitario"),
            "data": ultima.get("created_at"),
            "prazo_entrega_dias_uteis": ultima.get("prazo_entrega_dias_uteis"),
            "moq": ultima.get("moq"),
            "valido_ate": ultima.get("valido_ate"),
            "vencida": bool(ultima.get("valido_ate") and ultima["valido_ate"] < _today_iso()),
        })

    comparativo_fornecedores.sort(key=lambda x: x.get("ultimo_preco") or float("inf"))

    return {
        "item": item,
        "historico": historico_com_variacao,
        "total_cotacoes": len(historico_com_variacao),
        "ultimo_preco_pago": ultimo_preco_pago,
        "ultimo_preco_data": ultimo_preco_data,
        "comparativo_fornecedores": comparativo_fornecedores,
    }



# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 4 — MRP ENGINE  [PostgreSQL]
# ══════════════════════════════════════════════════════════════════════════════

class MRPCalcularInput(BaseModel):
    ops_ids: Optional[List[str]] = None
    incluir_estoque_minimo: bool = True


class RevisarItemInput(BaseModel):
    item_id: str
    quantidade_aprovada: float
    incluir: bool = True
    observacao: str = ""
    fornecedor_id: Optional[str] = None
    condicao_id: Optional[str] = None


class MRPAprovarInput(BaseModel):
    itens_aprovados: List[str]


async def _get_mrp_or_404(mrp_id: str, tenant_id: str) -> dict:
    row = await pg_db.fetch_one(
        "SELECT * FROM compras_mrp_rodadas WHERE id=$1 AND tenant_id=$2",
        mrp_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Rodada MRP não encontrada.")
    return _row(row)


async def _calcular_mrp_rodada(tenant_id: str, ops_ids: Optional[List[str]], incluir_estoque_minimo: bool) -> dict:
    # 1. Get active OPs from MongoDB (not migrated)
    op_query: Dict[str, Any] = {"tenant_id": tenant_id, "status": {"$in": ["aprovada", "em_producao", "aguardando_material"]}}
    if ops_ids:
        op_query["id"] = {"$in": ops_ids}
    ops = await db.ops.find(op_query, {"_id": 0}).to_list(1000)

    # 2. Aggregate material demands from OP BOMs
    demand_por_item: Dict[str, float] = {}
    ops_consideradas = []
    for op in ops:
        ops_consideradas.append({"id": op["id"], "numero_op": op.get("numero_op", ""), "status": op.get("status", "")})
        for bom_item in (op.get("bom") or []):
            item_id = bom_item.get("item_id") or bom_item.get("codigo_interno", "")
            if not item_id:
                continue
            qtd = float(bom_item.get("quantidade_necessaria", 0) or 0)
            demand_por_item[item_id] = demand_por_item.get(item_id, 0.0) + qtd

    # 3. Snapshot: estoque atual (MongoDB)
    snapshot_estoque: Dict[str, float] = {}
    async for est in db.estoque_items.find(
        {"tenant_id": tenant_id, "status": {"$in": ["aprovado", "disponivel", "liberado"]}},
        {"_id": 0, "item_id": 1, "codigo_interno": 1, "quantidade_disponivel": 1},
    ):
        key = est.get("item_id") or est.get("codigo_interno", "")
        if key:
            snapshot_estoque[key] = snapshot_estoque.get(key, 0.0) + float(est.get("quantidade_disponivel", 0) or 0)

    # 4. Snapshot: POs em trânsito (PostgreSQL)
    snapshot_pos: Dict[str, float] = {}
    for po_row in await pg_db.fetch_all(
        "SELECT itens FROM compras_pos WHERE tenant_id=$1 AND status = ANY($2::text[])",
        tenant_id, ["emitida", "confirmada", "parcialmente_recebida"],
    ):
        for it in (po_row["itens"] or []):
            key = it.get("item_id", "")
            qtd = float(it.get("quantidade_pendente", it.get("quantidade", 0)) or 0)
            snapshot_pos[key] = snapshot_pos.get(key, 0.0) + qtd

    # 5. Item catalog
    all_item_rows = await pg_db.fetch_all(
        "SELECT id, codigo_interno, descricao, categoria, unidade_compra, estoque_minimo, estoque_seguranca, lead_time_dias FROM compras_itens WHERE tenant_id=$1",
        tenant_id,
    )
    item_catalog: Dict[str, dict] = {r["id"]: _row(r) for r in all_item_rows}
    item_by_code: Dict[str, dict] = {r["codigo_interno"]: _row(r) for r in all_item_rows}

    # 6. Compute net requirements
    all_item_ids = set(demand_por_item.keys())
    if incluir_estoque_minimo:
        for it in item_catalog.values():
            if float(it.get("estoque_minimo") or 0) > 0:
                all_item_ids.add(it["id"])

    itens_sugeridos = []
    processados: set = set()
    for item_id in all_item_ids:
        if item_id in processados:
            continue
        processados.add(item_id)

        catalog_it = item_catalog.get(item_id) or item_by_code.get(item_id)
        if catalog_it is None:
            continue

        canonical_id = catalog_it["id"]
        processados.add(canonical_id)
        demanda = demand_por_item.get(item_id, 0.0) + demand_por_item.get(canonical_id, 0.0)
        est_atual = snapshot_estoque.get(item_id, 0.0) + snapshot_estoque.get(canonical_id, 0.0)
        em_transito = snapshot_pos.get(item_id, 0.0) + snapshot_pos.get(canonical_id, 0.0)
        est_seg = float(catalog_it.get("estoque_seguranca") or 0)
        est_min = float(catalog_it.get("estoque_minimo") or 0)

        necessidade = max(demanda + est_seg - est_atual - em_transito, 0.0)
        if est_atual + em_transito < est_min:
            necessidade = max(necessidade, est_min - est_atual - em_transito)

        if necessidade <= 0:
            continue

        itens_sugeridos.append({
            "item_id": canonical_id,
            "codigo_interno": catalog_it.get("codigo_interno", ""),
            "item_descricao": catalog_it.get("descricao", ""),
            "categoria": catalog_it.get("categoria", ""),
            "unidade_compra": catalog_it.get("unidade_compra", ""),
            "lead_time_dias": catalog_it.get("lead_time_dias", 0),
            "quantidade_demandada": round(demanda, 4),
            "estoque_atual": round(est_atual, 4),
            "em_transito": round(em_transito, 4),
            "estoque_seguranca": round(est_seg, 4),
            "quantidade_sugerida": round(necessidade, 4),
            "quantidade_aprovada": round(necessidade, 4),
            "incluir": True,
            "observacao": "",
            "fornecedor_id": None,
            "condicao_id": None,
        })

    itens_sugeridos.sort(key=lambda x: x["item_descricao"])
    return {
        "ops_consideradas": ops_consideradas,
        "snapshot_estoque": snapshot_estoque,
        "snapshot_pos_transito": snapshot_pos,
        "itens_sugeridos": itens_sugeridos,
    }


@compras_router.post("/mrp/calcular", status_code=201)
async def calcular_mrp(data: MRPCalcularInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    rodada_data = await _calcular_mrp_rodada(
        tenant_id, ops_ids=data.ops_ids, incluir_estoque_minimo=data.incluir_estoque_minimo,
    )
    ano = datetime.now(timezone.utc).year
    seq = await next_sequence_pg(tenant_id, f"compras_mrp_{ano}", start=0)
    numero_mrp = f"MRP-{ano}-{seq:04d}"
    mrp_id = new_id()
    await pg_db.execute(
        """INSERT INTO compras_mrp_rodadas(
            id, tenant_id, numero_mrp, status,
            ops_consideradas, snapshot_estoque, snapshot_pos_transito, itens_sugeridos,
            disparado_por_id, disparado_por_nome, created_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())""",
        mrp_id, tenant_id, numero_mrp, "gerada",
        rodada_data["ops_consideradas"], rodada_data["snapshot_estoque"],
        rodada_data["snapshot_pos_transito"], rodada_data["itens_sugeridos"],
        user["id"], user.get("name", ""),
    )
    return await _get_mrp_or_404(mrp_id, tenant_id)


@compras_router.get("/mrp")
async def listar_mrp(
    request: Request,
    status: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM compras_mrp_rodadas WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT id, tenant_id, numero_mrp, status, disparado_por_nome, created_at, aprovado_por_nome, aprovado_em "
        f"FROM compras_mrp_rodadas WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"rodadas": _rows(rows), "total": total, "limit": limit, "offset": offset}


@compras_router.get("/mrp/{mrp_id}")
async def detalhar_mrp(mrp_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    return await _get_mrp_or_404(mrp_id, user["tenant_id"])


@compras_router.put("/mrp/{mrp_id}/revisar-item")
async def revisar_mrp_item(mrp_id: str, data: RevisarItemInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    rodada = await _get_mrp_or_404(mrp_id, tenant_id)
    if rodada["status"] not in {"gerada", "em_revisao"}:
        raise HTTPException(status_code=400, detail=f"Rodada '{rodada['status']}' não pode ser revisada.")

    itens = list(rodada.get("itens_sugeridos") or [])
    encontrado = False
    for i, it in enumerate(itens):
        if it.get("item_id") == data.item_id:
            itens[i] = {
                **it,
                "quantidade_aprovada": data.quantidade_aprovada,
                "incluir": data.incluir,
                "observacao": data.observacao,
                "fornecedor_id": data.fornecedor_id,
                "condicao_id": data.condicao_id,
            }
            encontrado = True
            break

    if not encontrado:
        raise HTTPException(status_code=404, detail="Item não encontrado na rodada MRP.")

    await pg_db.execute(
        "UPDATE compras_mrp_rodadas SET itens_sugeridos=$1, status='em_revisao' WHERE id=$2 AND tenant_id=$3",
        itens, mrp_id, tenant_id,
    )
    return await _get_mrp_or_404(mrp_id, tenant_id)


@compras_router.post("/mrp/{mrp_id}/aprovar")
async def aprovar_mrp(mrp_id: str, data: MRPAprovarInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    rodada = await _get_mrp_or_404(mrp_id, tenant_id)
    if rodada["status"] in {"aprovada", "descartada"}:
        raise HTTPException(status_code=400, detail=f"Rodada '{rodada['status']}' não pode ser aprovada.")

    itens_aprovados_set = set(data.itens_aprovados)
    demandas_ids: List[str] = []

    for item in (rodada.get("itens_sugeridos") or []):
        item_id = item.get("item_id", "")
        if item_id not in itens_aprovados_set or not item.get("incluir", True):
            continue
        qtd = float(item.get("quantidade_aprovada", item.get("quantidade_sugerida", 0)))
        if qtd <= 0:
            continue

        dem_id = new_id()
        await pg_db.execute(
            """INSERT INTO compras_demandas(
                id, tenant_id, mrp_rodada_id, mrp_numero,
                item_id, item_descricao, quantidade,
                urgente, motivo,
                fornecedor_selecionado_id, condicao_comercial_id,
                status, created_at
            ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW())""",
            dem_id, tenant_id, mrp_id, rodada.get("numero_mrp", ""),
            item_id, item.get("item_descricao", ""), qtd,
            False, f"MRP {rodada.get('numero_mrp', '')}",
            item.get("fornecedor_id"), item.get("condicao_id"),
            "pendente",
        )
        demandas_ids.append(dem_id)

    total_incluir = len([it for it in (rodada.get("itens_sugeridos") or []) if it.get("incluir", True)])
    novo_status = "aprovada" if len(itens_aprovados_set) >= total_incluir else "parcialmente_aprovada"

    await pg_db.execute(
        """UPDATE compras_mrp_rodadas
           SET status=$1, aprovado_por_id=$2, aprovado_por_nome=$3, aprovado_em=$4
           WHERE id=$5 AND tenant_id=$6""",
        novo_status, user["id"], user.get("name", ""), now_iso(), mrp_id, tenant_id,
    )

    await create_workflow_task(
        tenant_id=tenant_id,
        entity_type="compras_mrp",
        entity_id=mrp_id,
        title=f"CMP-08 Emitir POs — {rodada.get('numero_mrp', '')} ({len(demandas_ids)} demandas)",
        description=(
            f"{len(demandas_ids)} demanda(s) geradas pelo MRP {rodada.get('numero_mrp', '')}. "
            f"Emita os Pedidos de Compra para cada demanda pendente."
        ),
        category="compras",
        blocking=False,
        due_in_days=2,
        created_by=user,
        metadata={"task_type": "standard", "module_origin": "compras", "demandas_ids": demandas_ids},
    )
    return {**await _get_mrp_or_404(mrp_id, tenant_id), "demandas_criadas": len(demandas_ids), "demandas_ids": demandas_ids}


@compras_router.get("/mrp/{mrp_id}/texto-disparo")
async def texto_disparo_mrp(mrp_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    rodada = await _get_mrp_or_404(mrp_id, user["tenant_id"])

    itens = [it for it in (rodada.get("itens_sugeridos") or []) if it.get("incluir", True)]
    linhas = [
        f"*Solicitação de Compras — {rodada.get('numero_mrp', '')}*",
        f"Data: {_today_iso()}  |  Responsável: {user.get('name', '')}",
        "",
    ]
    for i, it in enumerate(itens, 1):
        qtd = it.get("quantidade_aprovada", it.get("quantidade_sugerida", 0))
        linhas.append(f"{i}. *{it.get('item_descricao', '')}* ({it.get('codigo_interno', '')})")
        linhas.append(f"   Qtd: {qtd:,.2f} {it.get('unidade_compra', '')} | Lead-time: {it.get('lead_time_dias', 0)}d")
        if it.get("observacao"):
            linhas.append(f"   Obs: {it['observacao']}")
        linhas.append("")

    linhas.append("Por favor, confirme disponibilidade e prazo de entrega.")
    linhas.append(f"\n_Gerado pelo KURYOS ERP — {rodada.get('numero_mrp', '')}_")
    return {"numero_mrp": rodada.get("numero_mrp"), "texto": "\n".join(linhas)}


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 5 — PEDIDOS DE COMPRA (PO)  [PostgreSQL]
# ══════════════════════════════════════════════════════════════════════════════

class POItemInput(BaseModel):
    item_id: str
    item_descricao: str = ""
    quantidade: float
    unidade: str = ""
    preco_unitario: float
    preco_total: Optional[float] = None
    demanda_id: Optional[str] = None
    condicao_comercial_id: Optional[str] = None


class POCreateInput(BaseModel):
    fornecedor_id: str
    origem: str = "manual"
    data_entrega_solicitada: Optional[str] = None
    prazo_pagamento_texto: str = ""
    prazo_pagamento_dias: int = 0
    itens: List[POItemInput]
    ops_vinculadas: List[str] = []


class POUpdateInput(BaseModel):
    data_entrega_solicitada: Optional[str] = None
    prazo_pagamento_texto: Optional[str] = None
    prazo_pagamento_dias: Optional[int] = None
    itens: Optional[List[POItemInput]] = None


class POCancelarInput(BaseModel):
    motivo: str


class POConfirmarInput(BaseModel):
    data_entrega_confirmada: Optional[str] = None


class POReceberParcialInput(BaseModel):
    item_id: str
    quantidade_recebida: float
    nr_nota: Optional[str] = None
    data_recebimento: Optional[str] = None


class PONFInput(BaseModel):
    numero_nf: str
    data_emissao_nf: Optional[str] = None
    valor_nf: Optional[float] = None
    file_id: Optional[str] = None


async def _get_po_or_404(po_id: str, tenant_id: str) -> dict:
    row = await pg_db.fetch_one(
        "SELECT * FROM compras_pos WHERE id=$1 AND tenant_id=$2",
        po_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="PO não encontrada.")
    return _row(row)


async def _next_po_number(tenant_id: str) -> str:
    ano = datetime.now(timezone.utc).year
    seq = await next_sequence_pg(tenant_id, f"compras_po_{ano}", start=0)
    return f"PO-{ano}-{seq:04d}"


def _calc_po_total(itens: List[dict]) -> float:
    return round(sum(
        float(it.get("preco_total") or float(it.get("quantidade", 0)) * float(it.get("preco_unitario", 0)))
        for it in itens
    ), 2)


@compras_router.post("/pos", status_code=201)
async def criar_po(data: POCreateInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    if not data.itens:
        raise HTTPException(status_code=422, detail="PO deve conter pelo menos 1 item.")

    forn_row = await pg_db.fetch_one(
        "SELECT id, razao_social, cnpj, homologacao FROM compras_fornecedores WHERE id=$1 AND tenant_id=$2",
        data.fornecedor_id, tenant_id,
    )
    if not forn_row:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")
    forn = _row(forn_row)
    forn_homologado = ((forn.get("homologacao") or {}).get("status")) == "homologado"

    itens_dict = []
    for it in data.itens:
        preco_total = it.preco_total if it.preco_total is not None else round(it.quantidade * it.preco_unitario, 4)
        itens_dict.append({
            "item_id": it.item_id,
            "item_descricao": it.item_descricao,
            "quantidade": float(it.quantidade),
            "quantidade_pendente": float(it.quantidade),
            "quantidade_recebida": 0.0,
            "unidade": it.unidade,
            "preco_unitario": float(it.preco_unitario),
            "preco_total": float(preco_total),
            "demanda_id": it.demanda_id,
            "condicao_comercial_id": it.condicao_comercial_id,
            "status_item": "pendente",
        })

    po_id = new_id()
    log_entry = {"acao": "po_criada", "por_id": user["id"], "por_nome": user.get("name", ""), "em": now_iso()}
    await pg_db.execute(
        """INSERT INTO compras_pos(
            id, tenant_id, fornecedor_id, fornecedor_nome, fornecedor_cnpj,
            status, origem, ops_vinculadas,
            data_entrega_solicitada, prazo_pagamento_texto, prazo_pagamento_dias,
            fornecedor_homologado, itens, valor_total_po,
            compartilhamento, nfs_vinculadas, gatilho_financeiro_acionado,
            created_at, updated_at, created_by_id, created_by_nome, log_auditoria
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NOW(),NOW(),$18,$19,$20)""",
        po_id, tenant_id,
        forn["id"], forn["razao_social"], forn.get("cnpj", ""),
        "rascunho", data.origem, data.ops_vinculadas,
        data.data_entrega_solicitada, data.prazo_pagamento_texto, data.prazo_pagamento_dias,
        forn_homologado, itens_dict, _calc_po_total(itens_dict),
        {}, [], False,
        user["id"], user.get("name", ""), [log_entry],
    )
    return await _get_po_or_404(po_id, tenant_id)


@compras_router.get("/pos")
async def listar_pos(
    request: Request,
    status: Optional[str] = Query(None),
    fornecedor_id: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2

    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1
    if fornecedor_id:
        conditions.append(f"fornecedor_id=${idx}")
        params.append(fornecedor_id)
        idx += 1
    if origem:
        conditions.append(f"origem=${idx}")
        params.append(origem)
        idx += 1
    if q:
        conditions.append(f"(numero_po ILIKE ${idx} OR fornecedor_nome ILIKE ${idx})")
        params.append(f"%{q}%")
        idx += 1

    where = " AND ".join(conditions)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM compras_pos WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM compras_pos WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"pos": _rows(rows), "total": total, "limit": limit, "offset": offset}


@compras_router.get("/pos/{po_id}")
async def detalhar_po(po_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    return await _get_po_or_404(po_id, user["tenant_id"])


@compras_router.put("/pos/{po_id}")
async def atualizar_po(po_id: str, data: POUpdateInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    po = await _get_po_or_404(po_id, tenant_id)
    if po["status"] != "rascunho":
        raise HTTPException(status_code=400, detail=f"PO '{po['status']}' não pode ser editada (apenas rascunho).")

    payload = data.dict(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    sets = ["updated_at=NOW()"]
    params: list = []
    idx = 1

    for field in ("data_entrega_solicitada", "prazo_pagamento_texto", "prazo_pagamento_dias"):
        if field in payload:
            sets.append(f"{field}=${idx}")
            params.append(payload[field])
            idx += 1

    if "itens" in payload and payload["itens"] is not None:
        itens_dict = []
        for it in payload["itens"]:
            pt = it.get("preco_total") or round(float(it.get("quantidade", 0)) * float(it.get("preco_unitario", 0)), 4)
            itens_dict.append({
                **it,
                "quantidade_pendente": float(it.get("quantidade", 0)),
                "quantidade_recebida": 0.0,
                "preco_total": float(pt),
                "status_item": "pendente",
            })
        sets.append(f"itens=${idx}")
        params.append(itens_dict)
        idx += 1
        sets.append(f"valor_total_po=${idx}")
        params.append(_calc_po_total(itens_dict))
        idx += 1

    log_entry = {"acao": "po_atualizada", "campos": list(payload.keys()), "por_id": user["id"], "por_nome": user.get("name", ""), "em": now_iso()}
    sets.append(f"log_auditoria = log_auditoria || ${idx}::jsonb")
    params.append([log_entry])
    idx += 1

    params += [tenant_id, po_id]
    await pg_db.execute(
        f"UPDATE compras_pos SET {', '.join(sets)} WHERE tenant_id=${idx} AND id=${idx+1}",
        *params,
    )
    return await _get_po_or_404(po_id, tenant_id)


@compras_router.post("/pos/{po_id}/emitir")
async def emitir_po(po_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    po = await _get_po_or_404(po_id, tenant_id)
    if po["status"] != "rascunho":
        raise HTTPException(status_code=400, detail=f"Apenas POs em rascunho podem ser emitidas. Status: '{po['status']}'.")

    numero_po = po.get("numero_po") or await _next_po_number(tenant_id)
    hoje = _today_iso()
    prazo = int(po.get("prazo_pagamento_dias") or 0)
    data_venc = (datetime.now(timezone.utc) + timedelta(days=prazo)).date().isoformat() if prazo > 0 else None

    log_entry = {"acao": "po_emitida", "numero_po": numero_po, "por_id": user["id"], "por_nome": user.get("name", ""), "em": now_iso()}
    await pg_db.execute(
        """UPDATE compras_pos
           SET status='emitida', numero_po=$1, data_emissao=$2, data_vencimento_pagamento=$3,
               log_auditoria = log_auditoria || $4::jsonb, updated_at=NOW()
           WHERE id=$5 AND tenant_id=$6""",
        numero_po, hoje, data_venc, [log_entry], po_id, tenant_id,
    )
    for it in (po.get("itens") or []):
        if it.get("demanda_id"):
            await pg_db.execute(
                "UPDATE compras_demandas SET status='po_emitida', po_id=$1 WHERE id=$2 AND tenant_id=$3",
                po_id, it["demanda_id"], tenant_id,
            )
    return await _get_po_or_404(po_id, tenant_id)


@compras_router.post("/pos/{po_id}/confirmar")
async def confirmar_po(po_id: str, data: POConfirmarInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    po = await _get_po_or_404(po_id, tenant_id)
    if po["status"] != "emitida":
        raise HTTPException(status_code=400, detail=f"PO deve estar 'emitida' para confirmar. Status: '{po['status']}'.")

    log_entry = {"acao": "po_confirmada", "data_entrega_confirmada": data.data_entrega_confirmada, "por_id": user["id"], "por_nome": user.get("name", ""), "em": now_iso()}
    sets = ["status='confirmada'", "log_auditoria = log_auditoria || $1::jsonb", "updated_at=NOW()"]
    params: list = [[log_entry]]
    idx = 2

    if data.data_entrega_confirmada:
        sets.append(f"data_entrega_confirmada=${idx}")
        params.append(data.data_entrega_confirmada)
        idx += 1

    params += [po_id, tenant_id]
    await pg_db.execute(
        f"UPDATE compras_pos SET {', '.join(sets)} WHERE id=${idx} AND tenant_id=${idx+1}",
        *params,
    )
    return await _get_po_or_404(po_id, tenant_id)


@compras_router.post("/pos/{po_id}/receber-parcial")
async def receber_parcial_po(po_id: str, data: POReceberParcialInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    po = await _get_po_or_404(po_id, tenant_id)
    if po["status"] not in {"emitida", "confirmada", "parcialmente_recebida"}:
        raise HTTPException(status_code=400, detail=f"PO '{po['status']}' não aceita recebimento.")

    itens = list(po.get("itens") or [])
    encontrado = False
    for i, it in enumerate(itens):
        if it.get("item_id") == data.item_id:
            nova_recebida = float(it.get("quantidade_recebida", 0)) + data.quantidade_recebida
            nova_pendente = max(float(it.get("quantidade", 0)) - nova_recebida, 0.0)
            itens[i] = {
                **it,
                "quantidade_recebida": round(nova_recebida, 4),
                "quantidade_pendente": round(nova_pendente, 4),
                "status_item": "recebido" if nova_pendente <= 0 else "parcialmente_recebido",
                "nr_nota_recebimento": data.nr_nota,
                "data_recebimento": data.data_recebimento or _today_iso(),
            }
            encontrado = True
            break

    if not encontrado:
        raise HTTPException(status_code=404, detail="Item não encontrado na PO.")

    todos_recebidos = all(it.get("status_item") == "recebido" for it in itens)
    novo_status = "recebida" if todos_recebidos else "parcialmente_recebida"
    log_entry = {"acao": f"recebimento_{novo_status}", "item_id": data.item_id, "qtd": data.quantidade_recebida, "nr_nota": data.nr_nota, "por_id": user["id"], "por_nome": user.get("name", ""), "em": now_iso()}
    await pg_db.execute(
        """UPDATE compras_pos
           SET itens=$1, status=$2,
               log_auditoria = log_auditoria || $3::jsonb, updated_at=NOW()
           WHERE id=$4 AND tenant_id=$5""",
        itens, novo_status, [log_entry], po_id, tenant_id,
    )
    return await _get_po_or_404(po_id, tenant_id)


@compras_router.post("/pos/{po_id}/cancelar")
async def cancelar_po(po_id: str, data: POCancelarInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    if not data.motivo.strip():
        raise HTTPException(status_code=422, detail="motivo é obrigatório para cancelar.")

    po = await _get_po_or_404(po_id, tenant_id)
    if po["status"] in {"recebida", "encerrada", "cancelada"}:
        raise HTTPException(status_code=400, detail=f"PO '{po['status']}' não pode ser cancelada.")

    log_entry = {"acao": "po_cancelada", "motivo": data.motivo.strip(), "por_id": user["id"], "por_nome": user.get("name", ""), "em": now_iso()}
    await pg_db.execute(
        """UPDATE compras_pos
           SET status='cancelada', cancelado_motivo=$1, cancelado_por=$2, cancelado_em=$3,
               log_auditoria = log_auditoria || $4::jsonb, updated_at=NOW()
           WHERE id=$5 AND tenant_id=$6""",
        data.motivo.strip(), user["id"], now_iso(), [log_entry], po_id, tenant_id,
    )
    return await _get_po_or_404(po_id, tenant_id)


@compras_router.post("/pos/{po_id}/whatsapp")
async def whatsapp_po(po_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    po = await _get_po_or_404(po_id, user["tenant_id"])

    linhas = [
        f"*Pedido de Compra — {po.get('numero_po', 'RASCUNHO')}*",
        f"Fornecedor: {po['fornecedor_nome']}",
        f"Data: {po.get('data_emissao') or _today_iso()}",
        "",
        "*Itens:*",
    ]
    for it in (po.get("itens") or []):
        linhas.append(
            f"• {it.get('item_descricao', '')} — Qtd: {float(it.get('quantidade', 0)):,.2f} {it.get('unidade', '')} "
            f"× R$ {float(it.get('preco_unitario', 0)):,.2f} = R$ {float(it.get('preco_total', 0)):,.2f}"
        )
    linhas += [
        "",
        f"*Total: R$ {float(po.get('valor_total_po', 0)):,.2f}*",
        f"Pagamento: {po.get('prazo_pagamento_texto', '')}",
    ]
    if po.get("data_entrega_solicitada"):
        linhas.append(f"Entrega: {po['data_entrega_solicitada']}")
    linhas.append("\nPor favor, confirme o recebimento deste pedido.")
    return {"numero_po": po.get("numero_po"), "texto": "\n".join(linhas)}


@compras_router.put("/pos/{po_id}/nf")
async def vincular_nf_po(po_id: str, data: PONFInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_FULL)
    tenant_id = user["tenant_id"]

    await _get_po_or_404(po_id, tenant_id)
    nf_entry = {
        "numero_nf": data.numero_nf,
        "data_emissao_nf": data.data_emissao_nf,
        "valor_nf": data.valor_nf,
        "file_id": data.file_id,
        "registrado_por": user.get("name", ""),
        "registrado_em": now_iso(),
    }
    log_entry = {"acao": "nf_vinculada", "numero_nf": data.numero_nf, "por_id": user["id"], "por_nome": user.get("name", ""), "em": now_iso()}
    await pg_db.execute(
        """UPDATE compras_pos
           SET nfs_vinculadas = nfs_vinculadas || $1::jsonb,
               log_auditoria = log_auditoria || $2::jsonb, updated_at=NOW()
           WHERE id=$3 AND tenant_id=$4""",
        [nf_entry], [log_entry], po_id, tenant_id,
    )
    return await _get_po_or_404(po_id, tenant_id)


@compras_router.get("/pos/{po_id}/pdf")
async def gerar_pdf_po(po_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    po = await _get_po_or_404(po_id, user["tenant_id"])

    buf = io.BytesIO()
    doc_pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16, spaceAfter=8)
    story = []

    story.append(Paragraph(f"Pedido de Compra — {po.get('numero_po', 'RASCUNHO')}", title_style))
    story.append(Spacer(1, 4 * mm))

    header_data = [
        ["Fornecedor:", po.get("fornecedor_nome", ""), "Status:", (po.get("status", "")).upper()],
        ["CNPJ:", po.get("fornecedor_cnpj", ""), "Emissão:", po.get("data_emissao", "—")],
        ["Entrega Solicitada:", po.get("data_entrega_solicitada", "—"), "Pagamento:", po.get("prazo_pagamento_texto", "—")],
    ]
    ht = Table(header_data, colWidths=[40 * mm, 70 * mm, 35 * mm, 45 * mm])
    ht.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), rl_colors.grey),
        ("TEXTCOLOR", (2, 0), (2, -1), rl_colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(ht)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Itens", styles["Heading2"]))
    story.append(Spacer(1, 3 * mm))

    td = [["#", "Descrição", "Qtd", "Un.", "Preço Unit.", "Total"]]
    for i, it in enumerate(po.get("itens") or [], 1):
        td.append([
            str(i),
            it.get("item_descricao", ""),
            f"{float(it.get('quantidade', 0)):,.3f}",
            it.get("unidade", ""),
            f"R$ {float(it.get('preco_unitario', 0)):,.2f}",
            f"R$ {float(it.get('preco_total', 0)):,.2f}",
        ])
    td.append(["", "", "", "", "TOTAL", f"R$ {float(po.get('valor_total_po', 0)):,.2f}"])

    it_table = Table(td, colWidths=[10 * mm, 80 * mm, 22 * mm, 15 * mm, 28 * mm, 28 * mm])
    it_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [rl_colors.white, rl_colors.HexColor("#f8f8f8")]),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), rl_colors.HexColor("#e8f4f8")),
        ("GRID", (0, 0), (-1, -1), 0.25, rl_colors.HexColor("#cccccc")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(it_table)

    doc_pdf.build(story)
    buf.seek(0)
    filename = f"PO_{po.get('numero_po', po_id)}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 6 — ESTOQUE PROJETADO  [MongoDB estoque_items + PostgreSQL POs]
# ══════════════════════════════════════════════════════════════════════════════

async def _ler_estoque_aprovado(tenant_id: str) -> Dict[str, float]:
    estoque: Dict[str, float] = {}
    async for doc in db.estoque_items.find(
        {"tenant_id": tenant_id, "status": {"$in": ["aprovado", "disponivel", "liberado"]}},
        {"_id": 0, "item_id": 1, "codigo_interno": 1, "quantidade_disponivel": 1},
    ):
        key = doc.get("item_id") or doc.get("codigo_interno", "")
        if key:
            estoque[key] = estoque.get(key, 0.0) + float(doc.get("quantidade_disponivel", 0) or 0)
    return estoque


@compras_router.get("/estoque-projetado")
async def estoque_projetado(
    request: Request,
    categoria: Optional[str] = Query(None),
):
    user = await get_current_user(request)
    require_roles(user, _CMP_READ)
    tenant_id = user["tenant_id"]

    estoque_atual = await _ler_estoque_aprovado(tenant_id)

    em_transito: Dict[str, float] = {}
    for po_row in await pg_db.fetch_all(
        "SELECT itens FROM compras_pos WHERE tenant_id=$1 AND status = ANY($2::text[])",
        tenant_id, ["emitida", "confirmada", "parcialmente_recebida"],
    ):
        for it in (po_row["itens"] or []):
            key = it.get("item_id", "")
            em_transito[key] = em_transito.get(key, 0.0) + float(it.get("quantidade_pendente", it.get("quantidade", 0)) or 0)

    necessidades: Dict[str, float] = {}
    for r in await pg_db.fetch_all(
        "SELECT item_id, SUM(quantidade) as total FROM compras_demandas WHERE tenant_id=$1 AND status = ANY($2::text[]) GROUP BY item_id",
        tenant_id, ["pendente", "em_cotacao"],
    ):
        if r["item_id"]:
            necessidades[r["item_id"]] = float(r["total"] or 0)

    conditions = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    if categoria:
        conditions.append(f"categoria=${idx}")
        params.append(categoria)
        idx += 1

    item_rows = await pg_db.fetch_all(
        f"SELECT * FROM compras_itens WHERE {' AND '.join(conditions)} ORDER BY descricao ASC",
        *params,
    )

    projecoes = []
    for item_row in item_rows:
        item = _row(item_row)
        item_id = item["id"]
        est_atual = estoque_atual.get(item_id, 0.0) + estoque_atual.get(item.get("codigo_interno", ""), 0.0)
        transito = em_transito.get(item_id, 0.0)
        necessidade = necessidades.get(item_id, 0.0)
        est_min = float(item.get("estoque_minimo") or 0)
        est_seg = float(item.get("estoque_seguranca") or 0)
        projetado = est_atual + transito - necessidade

        alertas = []
        if projetado < est_seg:
            alertas.append("abaixo_estoque_seguranca")
        if projetado < est_min:
            alertas.append("abaixo_estoque_minimo")
        if projetado < 0:
            alertas.append("estoque_negativo_projetado")

        projecoes.append({
            "item_id": item_id,
            "codigo_interno": item.get("codigo_interno", ""),
            "descricao": item.get("descricao", ""),
            "categoria": item.get("categoria", ""),
            "unidade_compra": item.get("unidade_compra", ""),
            "estoque_atual": round(est_atual, 4),
            "em_transito": round(transito, 4),
            "necessidades_pendentes": round(necessidade, 4),
            "estoque_projetado": round(projetado, 4),
            "estoque_minimo": est_min,
            "estoque_seguranca": est_seg,
            "lead_time_dias": item.get("lead_time_dias", 0),
            "alertas": alertas,
            "requer_acao": len(alertas) > 0,
        })

    projecoes.sort(key=lambda x: (not x["requer_acao"], x["descricao"]))
    return {
        "projecoes": projecoes,
        "total": len(projecoes),
        "total_com_alerta": sum(1 for p in projecoes if p["requer_acao"]),
        "calculado_em": now_iso(),
    }

