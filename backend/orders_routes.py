"""
Orders Module (Pedidos) - Production Order management
- Auto-creates order when PD request transitions to APPROVED
- Generates "Ordem de Produção" PDF (Kuryos layout)
- Visible to all roles
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import io
import logging

from cq_routes import (
    cq_verificar_assepsia_manipulacao,
    cq_verificar_assepsia_envase,
    cq_verificar_setup_linha,
)

logger = logging.getLogger(__name__)

orders_router = APIRouter(prefix="/api/orders")

db = None
get_current_user = None
new_id_func = None
now_iso_func = None


def init_orders(database, auth_func, id_func, iso_func):
    global db, get_current_user, new_id_func, now_iso_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id():
    return new_id_func()


def now_iso():
    return now_iso_func()


# ============ STATUS ============
ORDER_STATUSES = ["rascunho", "confirmado", "em_producao", "concluido", "cancelado"]
ORDER_STATUS_LABELS = {
    "rascunho": "Rascunho",
    "confirmado": "Confirmado",
    "em_producao": "Em Produção",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
}


# ============ CONSTANTS ============
TIPOS_SERVICO = ["producao", "reposicao", "retrabalho"]
NIVEIS_FORMALIZACAO = [1, 2, 3]
CONDICAO_PGTO_RE = r"^\d{3}/\d{3}/\d{3}$"

# Spec Section 1.6 — 12 fixed insumo categories
CATEGORIAS_INSUMO = [
    "Arte / Aprovação de arte",
    "Cadastro ANVISA / Notificação",
    "Rótulos / Gravação",
    "Frascos / Potes",
    "Tampas / Sobretampa",
    "Cartucho",
    "Válvulas",
    "Celofane / Sleeve",
    "Display",
    "Caixa de embarque",
    "Essência / Fragrância",
    "Matérias-primas específicas",
]

# Statuses that make the order immutable (RN-PI-05)
STATUSES_IMUTAVEL = {"confirmado", "em_producao", "concluido"}

# Alçadas de aprovação comercial por desconto total (RN-PI-10)
# desconto_pct ≤ TIER_AUTO     → aprovacao_comercial = "nao_necessaria"
# TIER_AUTO < pct ≤ TIER_GERENTE → aprovacao_comercial = "pendente", nivel = "gerente_vendas"  (roles: sales_ops, admin)
# pct > TIER_GERENTE             → aprovacao_comercial = "pendente", nivel = "diretoria"        (roles: admin only)
TIER_AUTO = 5.0
TIER_GERENTE = 25.0


# ============ MODELS ============
class OrderItem(BaseModel):
    codigo_kuryos: str = ""
    codigo_cliente: str = ""
    item: str
    prazo_entrega: str = ""
    valor_unitario: float = 0.0
    valor_unitario_currency: str = "BRL"
    desconto_percentual: float = 0.0      # RN-PI-10: 0–100 %
    qtd: float = 0
    valor_total: float = 0.0
    tipo_servico: str = "producao"   # per-item type: producao | reposicao | retrabalho


class OrderInsumo(BaseModel):
    item: str = ""
    especificacoes: str = ""
    quantidade: str = ""
    arte: bool = False
    anvisa: bool = False
    rotulo: bool = False
    frasco: bool = False
    tampa: bool = False


class InsumoChecklistItem(BaseModel):
    """Structured insumo checklist — one entry per category (spec Section 1.6)."""
    categoria: str
    ativo: bool = False                        # whether this category applies
    origem: str = "kuryos"                     # kuryos | cliente
    status: str = "pendente"                   # pendente | em_andamento | confirmado | recebido
    responsavel: str = ""                      # who follows up when origem=cliente
    data_prevista: Optional[str] = None
    observacoes: str = ""


class ClienteData(BaseModel):
    nome: str = ""
    razao_social: str = ""
    cnpj: str = ""
    cidade_uf: str = ""
    responsavel: str = ""
    telefone: str = ""
    email: str = ""


class FreteData(BaseModel):
    tipo: str = "FOB"  # FOB or CIF
    endereco: str = ""
    cidade_uf: str = ""
    prazo_coleta: str = ""


class CondicoesData(BaseModel):
    prazo: str = ""
    forma_pgto: str = ""
    condicao_pagamento: str = "000/000/000"    # RN-PI-08: NNN/NNN/NNN


class OrderCreate(BaseModel):
    pd_request_id: Optional[str] = None
    kickoff_id: Optional[str] = None          # Gap A: optional FK to kickoffs collection
    client_card_id: Optional[str] = None
    numero_pedido: Optional[str] = None
    data_pedido: Optional[str] = None
    tipo_servico: str = "producao"             # producao | reposicao | retrabalho
    nivel_formalizacao: int = 1                # 1 | 2 | 3
    cliente: ClienteData = Field(default_factory=ClienteData)
    frete: FreteData = Field(default_factory=FreteData)
    items: List[OrderItem] = []
    condicoes: CondicoesData = Field(default_factory=CondicoesData)
    insumos: List[OrderInsumo] = []
    checklist_insumos: List[InsumoChecklistItem] = []
    observacoes: str = ""


class OrderUpdate(BaseModel):
    kickoff_id: Optional[str] = None          # Gap A: allow linking/unlinking kickoff
    numero_pedido: Optional[str] = None
    data_pedido: Optional[str] = None
    status: Optional[str] = None
    tipo_servico: Optional[str] = None
    nivel_formalizacao: Optional[int] = None
    cliente: Optional[ClienteData] = None
    frete: Optional[FreteData] = None
    items: Optional[List[OrderItem]] = None
    condicoes: Optional[CondicoesData] = None
    insumos: Optional[List[OrderInsumo]] = None
    checklist_insumos: Optional[List[InsumoChecklistItem]] = None
    observacoes: Optional[str] = None
    cgi_status: Optional[str] = None          # "pendente" | "assinado"
    # Client approval fields (RN-PI-04)
    aprovacao_cliente: Optional[str] = None   # pendente | aprovado
    aprovacao_cliente_obs: Optional[str] = None
    aprovacao_cliente_em: Optional[str] = None
    justificativa: Optional[str] = None        # R21: required to edit locked fields


# ===== OP MODELS =====
class OPItem(BaseModel):
    item: str = ""
    codigo_kuryos: str = ""
    qtd_planejada: float = 0
    qtd_produzida: float = 0
    lote: str = ""
    prazo_sla: str = ""


class OPCreate(BaseModel):
    pedido_id: str
    items: List[OPItem] = []
    observacoes: str = ""


class OPUpdate(BaseModel):
    status: Optional[str] = None  # "aberta" | "em_processo" | "concluida" | "cancelada"
    items: Optional[List[OPItem]] = None
    observacoes: Optional[str] = None


OP_STATUSES = ["aberta", "em_processo", "concluida", "cancelada"]


# ===== R15: REPRODUZIR MODELS =====
class ItemOverride(BaseModel):
    codigo_kuryos: str = ""
    valor_unitario: Optional[float] = None
    prazo_entrega: Optional[str] = None
    qtd: Optional[float] = None


class ReproduzirInput(BaseModel):
    items_override: List[ItemOverride] = []
    endereco_entrega: Optional[str] = None
    observacoes: Optional[str] = None


# ============ HELPERS ============
async def _generate_order_number(tenant_id: str) -> str:
    """Generate order number in format MM_NN (e.g. 02_07) - sequential per month"""
    now = datetime.now(timezone.utc)
    month_str = f"{now.month:02d}"
    # Count orders for this tenant in this month
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()
    count = await db.orders.count_documents({
        "tenant_id": tenant_id,
        "created_at": {"$gte": start_of_month},
    })
    seq = count + 1
    return f"{month_str}_{seq:02d}"


def _calculate_totals(items: List[Dict[str, Any]]) -> Dict[str, float]:
    """Recalculate item totals (applying per-item discount) and return order-level aggregates."""
    total_bruto = 0.0
    total_desconto = 0.0
    for it in items:
        valor_bruto = round((it.get("valor_unitario") or 0) * (it.get("qtd") or 0), 2)
        desc_pct = max(0.0, min(100.0, float(it.get("desconto_percentual") or 0)))
        valor_desc = round(valor_bruto * desc_pct / 100, 2)
        valor_liq = round(valor_bruto - valor_desc, 2)
        it["valor_desconto"] = valor_desc
        it["valor_total"] = valor_liq
        total_bruto += valor_bruto
        total_desconto += valor_desc
    total_liquido = round(total_bruto - total_desconto, 2)
    desc_pct_medio = round((total_desconto / total_bruto * 100) if total_bruto > 0 else 0.0, 2)
    return {
        "total_pedido": total_liquido,
        "total_bruto": round(total_bruto, 2),
        "total_desconto": round(total_desconto, 2),
        "desconto_pct_medio": desc_pct_medio,
    }


def _eval_aprovacao_comercial(totals: Dict[str, float], existing: Optional[Dict] = None) -> Dict[str, Any]:
    """Determine aprovacao_comercial status based on order discount. (RN-PI-10)"""
    pct = totals.get("desconto_pct_medio", 0.0)
    if pct <= TIER_AUTO:
        return {"aprovacao_comercial": "nao_necessaria", "aprovacao_comercial_nivel": None}
    # Keep existing approval if already approved at the right level
    if existing:
        cur = existing.get("aprovacao_comercial")
        if cur == "aprovada":
            return {"aprovacao_comercial": "aprovada",
                    "aprovacao_comercial_nivel": existing.get("aprovacao_comercial_nivel")}
    nivel = "gerente_vendas" if pct <= TIER_GERENTE else "diretoria"
    return {"aprovacao_comercial": "pendente", "aprovacao_comercial_nivel": nivel}


async def _validate_kickoff_fk(kickoff_id: Optional[str], tenant_id: str) -> None:
    """Gap A: validate that kickoff_id references an existing kickoff for this tenant."""
    if not kickoff_id:
        return
    doc = await db.kickoffs.find_one({"id": kickoff_id, "tenant_id": tenant_id}, {"_id": 0, "id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Kickoff '{kickoff_id}' não encontrado (Gap A).")


async def _enrich_from_crm(client_card_id: Optional[str], tenant_id: str) -> Dict[str, Any]:
    """Pull client data from CRM card if available"""
    cliente = {
        "nome": "", "razao_social": "", "cnpj": "",
        "cidade_uf": "", "responsavel": "", "telefone": "", "email": "",
    }
    if not client_card_id:
        return cliente

    card = await db.cards.find_one({"id": client_card_id, "tenant_id": tenant_id}, {"_id": 0})
    if not card:
        return cliente

    cliente["nome"] = card.get("nome_cliente", "") or ""
    # Try to pull CRM client data
    crm_client_id = card.get("crm_client_id") or card.get("cliente_id")
    crm_client = None
    if crm_client_id:
        crm_client = await db.crm_clients.find_one({"id": crm_client_id, "tenant_id": tenant_id}, {"_id": 0})

    if crm_client:
        cliente["razao_social"] = crm_client.get("nome_empresa", "") or cliente["nome"]
        cliente["cnpj"] = crm_client.get("cnpj", "")
        cidade = crm_client.get("cidade", "") or crm_client.get("regiao", "")
        uf = crm_client.get("uf", "") or crm_client.get("estado", "")
        cliente["cidade_uf"] = f"{cidade}/{uf}" if cidade and uf else (cidade or uf)
        contato = crm_client.get("contato_principal") or {}
        cliente["responsavel"] = contato.get("nome", "")
        cliente["telefone"] = contato.get("whatsapp", "")
        cliente["email"] = contato.get("email", "")
    else:
        # Fallback to card-level fields
        cliente["razao_social"] = card.get("razao_social", "") or card.get("nome_cliente", "")
        cliente["cnpj"] = card.get("cnpj", "")
        cliente["responsavel"] = card.get("responsavel", "") or card.get("contato_nome", "")
        cliente["telefone"] = card.get("telefone", "") or card.get("contato_whatsapp", "")
        cliente["email"] = card.get("email", "") or card.get("contato_email", "")

    return cliente


async def _build_items_from_pd(pd_request_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """Build initial order items from the PD request + samples + formula"""
    pd_req = await db.pd_requests.find_one({"id": pd_request_id, "tenant_id": tenant_id}, {"_id": 0})
    if not pd_req:
        return []

    items: List[Dict[str, Any]] = []
    project_name = pd_req.get("commercial_name") or pd_req.get("project_name") or ""
    volume = pd_req.get("volume") or ""
    sku = pd_req.get("sku") or pd_req.get("internal_code") or ""
    item_label = f"{project_name} {volume}".strip() if volume else project_name

    items.append({
        "codigo_kuryos": sku,
        "codigo_cliente": "",
        "item": item_label,
        "prazo_entrega": "20 Dias",
        "valor_unitario": 0.0,
        "qtd": 0,
        "valor_total": 0.0,
    })
    return items


async def auto_create_order_on_pd_approval(pd_request_id: str, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Called from pd_routes.py when PD transitions to APPROVED. Idempotent."""
    if db is None:
        return None
    tenant_id = user["tenant_id"]
    # Idempotency: skip if already exists
    existing = await db.orders.find_one({"pd_request_id": pd_request_id, "tenant_id": tenant_id}, {"_id": 0})
    if existing:
        return existing

    pd_req = await db.pd_requests.find_one({"id": pd_request_id, "tenant_id": tenant_id}, {"_id": 0})
    if not pd_req:
        return None

    cliente = await _enrich_from_crm(pd_req.get("client_card_id"), tenant_id)
    items = await _build_items_from_pd(pd_request_id, tenant_id)
    numero = await _generate_order_number(tenant_id)

    # Gap A: auto-link kickoff if the PD request's project has one
    kickoff_id = None
    crm_proj_id = pd_req.get("crm_project_id")
    if crm_proj_id:
        proj = await db.crm_projects.find_one({"id": crm_proj_id, "tenant_id": tenant_id}, {"_id": 0, "kickoff_id": 1})
        kickoff_id = proj.get("kickoff_id") if proj else None

    checklist_default = [{"categoria": c, "ativo": False, "origem": "kuryos", "status": "pendente", "responsavel": "", "data_prevista": None, "observacoes": ""} for c in CATEGORIAS_INSUMO]
    totals = _calculate_totals(items)
    ap_comercial = _eval_aprovacao_comercial(totals)
    order = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "pd_request_id": pd_request_id,
        "kickoff_id": kickoff_id,
        "client_card_id": pd_req.get("client_card_id"),
        "numero_pedido": numero,
        "data_pedido": now_iso(),
        "status": "rascunho",
        "tipo_servico": "producao",
        "nivel_formalizacao": 1,
        "project_name": pd_req.get("project_name", ""),
        "cliente": cliente,
        "frete": {
            "tipo": "FOB",
            "endereco": "",
            "cidade_uf": cliente.get("cidade_uf", ""),
            "prazo_coleta": "Até 5 dias úteis após confirmação da produção",
        },
        "items": items,
        "condicoes": {
            "prazo": "30 dias",
            "forma_pgto": "Boleto + Depósito",
            "condicao_pagamento": "030/000/000",
        },
        "insumos": [],
        "checklist_insumos": checklist_default,
        "total_pedido": totals["total_pedido"],
        "total_bruto": totals["total_bruto"],
        "total_desconto": totals["total_desconto"],
        "desconto_pct_medio": totals["desconto_pct_medio"],
        "observacoes": "",
        "cgi_status": "pendente",
        "cgi_assinado_em": None,
        "cgi_assinado_por": None,
        "aprovacao_cliente": "pendente",
        "aprovacao_cliente_obs": "",
        "aprovacao_cliente_em": None,
        "aprovacao_comercial": ap_comercial["aprovacao_comercial"],
        "aprovacao_comercial_nivel": ap_comercial["aprovacao_comercial_nivel"],
        "aprovacao_comercial_por": None,
        "aprovacao_comercial_em": None,
        "aprovacao_comercial_obs": "",
        "op_id": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "auto_created": True,
    }
    await db.orders.insert_one(order)
    order.pop("_id", None)
    logger.info(f"Order auto-created for PD {pd_request_id}: {numero}")
    return order


# ============ ROUTES ============
@orders_router.get("")
async def list_orders(request: Request, status: Optional[str] = None, q: Optional[str] = None):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"numero_pedido": {"$regex": q, "$options": "i"}},
            {"cliente.nome": {"$regex": q, "$options": "i"}},
            {"cliente.razao_social": {"$regex": q, "$options": "i"}},
            {"project_name": {"$regex": q, "$options": "i"}},
        ]
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return orders


@orders_router.get("/{order_id}")
async def get_order(order_id: str, request: Request):
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@orders_router.get("/reorder/{client_card_id}")
async def get_reorder_draft(client_card_id: str, request: Request):
    """Return a pre-populated draft order based on the most recent order for a CRM client card."""
    user = await get_current_user(request)
    last_order = await db.orders.find_one(
        {"client_card_id": client_card_id, "tenant_id": user["tenant_id"]},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not last_order:
        raise HTTPException(status_code=404, detail="Nenhum pedido anterior encontrado para este cliente")

    numero = await _generate_order_number(user["tenant_id"])
    draft = {
        **last_order,
        "id": None,
        "numero_pedido": numero,
        "data_pedido": now_iso(),
        "status": "rascunho",
        "observacoes": "",
        "auto_created": False,
        "is_reorder_draft": True,
        "reorder_from": last_order["id"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
    }
    return draft


@orders_router.post("")
async def create_order(data: OrderCreate, request: Request):
    import re
    user = await get_current_user(request)

    if data.tipo_servico not in TIPOS_SERVICO:
        raise HTTPException(status_code=400, detail=f"tipo_servico inválido. Permitidos: {TIPOS_SERVICO}")

    condicoes = data.condicoes.model_dump()
    cpgto = condicoes.get("condicao_pagamento", "")
    if cpgto and not re.match(CONDICAO_PGTO_RE, cpgto):
        raise HTTPException(status_code=400, detail="condicao_pagamento deve ter formato NNN/NNN/NNN (RN-PI-08)")

    # Gap A: validate kickoff FK if provided
    await _validate_kickoff_fk(data.kickoff_id, user["tenant_id"])

    cliente = data.cliente.model_dump()
    if data.client_card_id and not cliente.get("razao_social"):
        cliente = await _enrich_from_crm(data.client_card_id, user["tenant_id"])

    items = [it.model_dump() for it in data.items]
    if data.pd_request_id and not items:
        items = await _build_items_from_pd(data.pd_request_id, user["tenant_id"])

    # Build default checklist if not provided
    checklist = [c.model_dump() for c in data.checklist_insumos] if data.checklist_insumos else \
        [{"categoria": c, "ativo": False, "origem": "kuryos", "status": "pendente", "responsavel": "", "data_prevista": None, "observacoes": ""} for c in CATEGORIAS_INSUMO]

    numero = data.numero_pedido or await _generate_order_number(user["tenant_id"])
    totals = _calculate_totals(items)
    ap_comercial = _eval_aprovacao_comercial(totals)

    order = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "pd_request_id": data.pd_request_id,
        "kickoff_id": data.kickoff_id,
        "client_card_id": data.client_card_id,
        "numero_pedido": numero,
        "data_pedido": data.data_pedido or now_iso(),
        "status": "rascunho",
        "tipo_servico": data.tipo_servico,
        "nivel_formalizacao": data.nivel_formalizacao,
        "project_name": "",
        "cliente": cliente,
        "frete": data.frete.model_dump(),
        "items": items,
        "condicoes": condicoes,
        "insumos": [it.model_dump() for it in data.insumos],
        "checklist_insumos": checklist,
        "total_pedido": totals["total_pedido"],
        "total_bruto": totals["total_bruto"],
        "total_desconto": totals["total_desconto"],
        "desconto_pct_medio": totals["desconto_pct_medio"],
        "observacoes": data.observacoes,
        "cgi_status": "pendente",
        "cgi_assinado_em": None,
        "cgi_assinado_por": None,
        "aprovacao_cliente": "pendente",
        "aprovacao_cliente_obs": "",
        "aprovacao_cliente_em": None,
        # Gap B: aprovacao_comercial
        "aprovacao_comercial": ap_comercial["aprovacao_comercial"],
        "aprovacao_comercial_nivel": ap_comercial["aprovacao_comercial_nivel"],
        "aprovacao_comercial_por": None,
        "aprovacao_comercial_em": None,
        "aprovacao_comercial_obs": "",
        "op_id": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "auto_created": False,
    }
    await db.orders.insert_one(order)
    order.pop("_id", None)
    return order


@orders_router.put("/{order_id}")
async def update_order(order_id: str, data: OrderUpdate, request: Request):
    import re
    user = await get_current_user(request)
    existing = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    update_fields: Dict[str, Any] = {}
    payload = data.model_dump(exclude_unset=True)

    if "status" in payload and payload["status"] not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido. Permitidos: {ORDER_STATUSES}")

    # Gap A: validate kickoff FK if being set
    if "kickoff_id" in payload:
        await _validate_kickoff_fk(payload["kickoff_id"], user["tenant_id"])

    # RN-PI-01: CGI must be signed before confirming
    if payload.get("status") == "confirmado":
        if existing.get("cgi_status", "pendente") != "assinado":
            raise HTTPException(status_code=422, detail="CGI não assinado. Assine o Contrato Geral de Industrialização antes de confirmar o pedido. (RN-PI-01)")
        # RN-PI-10: commercial approval must be resolved before confirming
        if existing.get("aprovacao_comercial") == "pendente":
            nivel = existing.get("aprovacao_comercial_nivel", "gerente_vendas")
            raise HTTPException(status_code=422, detail=f"Aprovação comercial pendente (desconto > {TIER_AUTO}%). Requer aprovação de {nivel.replace('_', ' ')} antes de confirmar. (RN-PI-10)")

    # RN-PI-05 + R21: confirmed/em_producao/concluido orders are immutable — only allowed fields
    IMMUTABLE_BLOCK = {"items", "cliente", "frete", "condicoes", "insumos", "numero_pedido", "data_pedido", "tipo_servico", "nivel_formalizacao"}
    if existing.get("status") in STATUSES_IMUTAVEL:
        blocked = IMMUTABLE_BLOCK & set(payload.keys())
        if blocked:
            justificativa = (payload.get("justificativa") or "").strip()
            if not justificativa:
                raise HTTPException(
                    status_code=422,
                    detail=f"Pedido {existing['status']} é imutável (RN-PI-05). Campos bloqueados: {sorted(blocked)}. Forneça uma justificativa para editar campos comerciais. (R21)"
                )
            # R21: write audit log entry
            old_vals = {k: existing.get(k) for k in blocked}
            new_vals = {k: payload.get(k) for k in blocked}
            audit_entry = {
                "id": new_id(),
                "tenant_id": user["tenant_id"],
                "order_id": order_id,
                "order_numero": existing.get("numero_pedido", ""),
                "user_id": user["id"],
                "user_name": user.get("name", ""),
                "action": "edit_locked",
                "fields_changed": sorted(blocked),
                "old_values": old_vals,
                "new_values": new_vals,
                "justificativa": justificativa,
                "created_at": now_iso(),
            }
            await db.order_audit_log.insert_one(audit_entry)

    # CQ hard stops — verify CK prerequisites before starting production
    if payload.get("status") == "em_producao":
        op_tipo = existing.get("tipo", "")
        if op_tipo == "manipulacao":
            await cq_verificar_assepsia_manipulacao(db, user["tenant_id"], order_id)
        elif op_tipo == "envase":
            await cq_verificar_assepsia_envase(db, user["tenant_id"], order_id)
            await cq_verificar_setup_linha(db, user["tenant_id"], order_id)

    # Validate NNN/NNN/NNN if condicoes.condicao_pagamento is provided
    if "condicoes" in payload and payload["condicoes"]:
        cpgto = payload["condicoes"].get("condicao_pagamento", "")
        if cpgto and not re.match(CONDICAO_PGTO_RE, cpgto):
            raise HTTPException(status_code=400, detail="condicao_pagamento deve ter formato NNN/NNN/NNN (RN-PI-08)")

    for key in ("kickoff_id", "numero_pedido", "data_pedido", "status", "observacoes", "cgi_status",
                "tipo_servico", "nivel_formalizacao",
                "aprovacao_cliente", "aprovacao_cliente_obs", "aprovacao_cliente_em"):
        if key in payload:
            update_fields[key] = payload[key]

    for key in ("cliente", "frete", "condicoes"):
        if key in payload and payload[key] is not None:
            update_fields[key] = payload[key]

    if "items" in payload and payload["items"] is not None:
        items = payload["items"]
        update_fields["items"] = items
        totals = _calculate_totals(items)
        update_fields["total_pedido"] = totals["total_pedido"]
        update_fields["total_bruto"] = totals["total_bruto"]
        update_fields["total_desconto"] = totals["total_desconto"]
        update_fields["desconto_pct_medio"] = totals["desconto_pct_medio"]
        # Re-evaluate commercial approval tier (RN-PI-10)
        ap = _eval_aprovacao_comercial(totals, existing)
        update_fields["aprovacao_comercial"] = ap["aprovacao_comercial"]
        update_fields["aprovacao_comercial_nivel"] = ap["aprovacao_comercial_nivel"]
        # Reset approval if discount increased beyond previous approval
        if ap["aprovacao_comercial"] == "pendente":
            update_fields["aprovacao_comercial_por"] = None
            update_fields["aprovacao_comercial_em"] = None

    if "insumos" in payload and payload["insumos"] is not None:
        update_fields["insumos"] = payload["insumos"]

    if "checklist_insumos" in payload and payload["checklist_insumos"] is not None:
        update_fields["checklist_insumos"] = payload["checklist_insumos"]

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # R19: Auto-create followups when order first transitions to concluido
    if payload.get("status") == "concluido" and existing.get("status") != "concluido":
        if not existing.get("followups"):
            now_dt = datetime.now(timezone.utc)
            marcos_dias = [("1m", 30), ("3m", 90), ("6m", 180)]
            update_fields["followups"] = [
                {"marco": marco, "vence_em": (now_dt + timedelta(days=dias)).isoformat(), "notificado": False}
                for marco, dias in marcos_dias
            ]

    update_fields["updated_at"] = now_iso()
    await db.orders.update_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"$set": update_fields})
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated


@orders_router.post("/{order_id}/aprovar-cliente")
async def aprovar_cliente(order_id: str, request: Request):
    """Register client approval (RN-PI-04) — sets aprovacao_cliente=aprovado."""
    from pydantic import BaseModel as PM
    class AprovBody(PM):
        observacoes: str = ""

    user = await get_current_user(request)
    body_raw = await request.json()
    obs = body_raw.get("observacoes", "")
    existing = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    now = now_iso()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "aprovacao_cliente": "aprovado",
            "aprovacao_cliente_obs": obs,
            "aprovacao_cliente_em": now,
            "aprovacao_cliente_por": user["name"],
            "updated_at": now,
        }}
    )
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


@orders_router.post("/{order_id}/aprovar-comercial")
async def aprovar_comercial(order_id: str, request: Request):
    """Register commercial approval (RN-PI-10) — required when order discount exceeds TIER_AUTO.
    Requires role: sales_ops (desconto ≤ TIER_GERENTE) or admin (desconto > TIER_GERENTE)."""
    user = await get_current_user(request)
    body = await request.json()
    obs = body.get("observacoes", "")
    existing = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if existing.get("aprovacao_comercial") == "nao_necessaria":
        raise HTTPException(status_code=400, detail="Este pedido não requer aprovação comercial (desconto dentro do limite automático).")
    # Role check: diretoria level requires admin; gerente level requires sales_ops or admin
    nivel = existing.get("aprovacao_comercial_nivel", "gerente_vendas")
    roles_ok = {"admin"} if nivel == "diretoria" else {"sales_ops", "admin"}
    if user.get("role") not in roles_ok:
        raise HTTPException(status_code=403, detail=f"Aprovação de nível '{nivel}' requer role: {sorted(roles_ok)}.")
    now = now_iso()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "aprovacao_comercial": "aprovada",
            "aprovacao_comercial_obs": obs,
            "aprovacao_comercial_em": now,
            "aprovacao_comercial_por": user.get("name", ""),
            "updated_at": now,
        }}
    )
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


@orders_router.post("/{order_id}/rejeitar-comercial")
async def rejeitar_comercial(order_id: str, request: Request):
    """Reject the commercial approval request (RN-PI-10)."""
    user = await get_current_user(request)
    body = await request.json()
    obs = body.get("observacoes", "")
    existing = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    nivel = existing.get("aprovacao_comercial_nivel", "gerente_vendas")
    roles_ok = {"admin"} if nivel == "diretoria" else {"sales_ops", "admin"}
    if user.get("role") not in roles_ok:
        raise HTTPException(status_code=403, detail=f"Rejeição de nível '{nivel}' requer role: {sorted(roles_ok)}.")
    now = now_iso()
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "aprovacao_comercial": "rejeitada",
            "aprovacao_comercial_obs": obs,
            "aprovacao_comercial_em": now,
            "aprovacao_comercial_por": user.get("name", ""),
            "updated_at": now,
        }}
    )
    return await db.orders.find_one({"id": order_id}, {"_id": 0})


@orders_router.delete("/{order_id}")
async def delete_order(order_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.orders.delete_one({"id": order_id, "tenant_id": user["tenant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return {"message": "Pedido removido"}


# ============ CGI SIGN (RN-PI-01) ============
@orders_router.post("/{order_id}/sign-cgi")
async def sign_cgi(order_id: str, request: Request):
    """Mark the CGI (Contrato Geral de Industrialização) as signed for this order."""
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "cgi_status": "assinado",
            "cgi_assinado_em": now_iso(),
            "cgi_assinado_por": user.get("name", ""),
            "updated_at": now_iso(),
        }},
    )
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated


# ============ OP — CREATE FROM ORDER ============
async def _generate_op_number(tenant_id: str) -> str:
    now = datetime.now(timezone.utc)
    year = now.year
    count = await db.ops.count_documents({"tenant_id": tenant_id, "created_at": {"$gte": f"{year}-01-01"}})
    return f"OP-{year}-{count + 1:03d}"


@orders_router.post("/{order_id}/create-op")
async def create_op_from_order(order_id: str, request: Request):
    """Convert a confirmed PI into an Ordem de Produção."""
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.get("status") not in ("confirmado", "em_producao"):
        raise HTTPException(status_code=422, detail="OP só pode ser gerada a partir de um pedido Confirmado.")
    if order.get("op_id"):
        existing_op = await db.ops.find_one({"id": order["op_id"]}, {"_id": 0})
        if existing_op:
            return existing_op

    numero_op = await _generate_op_number(user["tenant_id"])
    op_items = [
        {
            "item": it.get("item", ""),
            "codigo_kuryos": it.get("codigo_kuryos", ""),
            "qtd_planejada": it.get("qtd", 0),
            "qtd_produzida": 0,
            "lote": "",
            "prazo_sla": it.get("prazo_entrega", ""),
        }
        for it in (order.get("items") or [])
    ]
    op = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "numero_op": numero_op,
        "pedido_id": order_id,
        "numero_pedido": order.get("numero_pedido", ""),
        "cliente_nome": order.get("cliente", {}).get("nome") or order.get("cliente", {}).get("razao_social", ""),
        "project_name": order.get("project_name", ""),
        "status": "aberta",
        "items": op_items,
        "observacoes": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
    }
    await db.ops.insert_one(op)
    op.pop("_id", None)
    # Link back to the order
    await db.orders.update_one({"id": order_id}, {"$set": {"op_id": op["id"], "status": "em_producao", "updated_at": now_iso()}})
    return op


# ============ R15: REPRODUZIR PEDIDO ============
@orders_router.post("/{order_id}/reproduzir")
async def reproduzir_pedido(order_id: str, data: ReproduzirInput, request: Request):
    """Clone an existing locked order and immediately create a new OP (R15)."""
    import copy
    user = await get_current_user(request)
    if user.get("role") not in {"admin", "vendedor", "sales_ops"}:
        raise HTTPException(status_code=403, detail="Permissão negada. Apenas Comercial e Admin podem reproduzir pedidos.")

    original = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not original:
        raise HTTPException(status_code=404, detail="Pedido original não encontrado")
    if original.get("status") not in STATUSES_IMUTAVEL:
        raise HTTPException(status_code=422, detail="Só é possível reproduzir pedidos Confirmados, Em Produção ou Concluídos.")

    # Clone items applying overrides keyed by codigo_kuryos
    items = copy.deepcopy(original.get("items", []))
    override_map = {ov.codigo_kuryos: ov for ov in data.items_override if ov.codigo_kuryos}
    for it in items:
        ov = override_map.get(it.get("codigo_kuryos", ""))
        if ov:
            if ov.valor_unitario is not None:
                it["valor_unitario"] = ov.valor_unitario
            if ov.prazo_entrega is not None:
                it["prazo_entrega"] = ov.prazo_entrega
            if ov.qtd is not None:
                it["qtd"] = ov.qtd

    totals = _calculate_totals(items)
    ap_comercial = _eval_aprovacao_comercial(totals)
    numero = await _generate_order_number(user["tenant_id"])

    frete = copy.deepcopy(original.get("frete", {}))
    if data.endereco_entrega is not None:
        frete["endereco"] = data.endereco_entrega

    checklist_default = [
        {"categoria": c, "ativo": False, "origem": "kuryos", "status": "pendente",
         "responsavel": "", "data_prevista": None, "observacoes": ""}
        for c in CATEGORIAS_INSUMO
    ]
    ts = now_iso()
    new_order = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "pd_request_id": original.get("pd_request_id"),
        "kickoff_id": original.get("kickoff_id"),
        "client_card_id": original.get("client_card_id"),
        "numero_pedido": numero,
        "data_pedido": ts,
        "status": "confirmado",
        "tipo_servico": original.get("tipo_servico", "producao"),
        "nivel_formalizacao": original.get("nivel_formalizacao", 1),
        "project_name": original.get("project_name", ""),
        "cliente": copy.deepcopy(original.get("cliente", {})),
        "frete": frete,
        "items": items,
        "condicoes": copy.deepcopy(original.get("condicoes", {})),
        "insumos": [],
        "checklist_insumos": checklist_default,
        "total_pedido": totals["total_pedido"],
        "total_bruto": totals["total_bruto"],
        "total_desconto": totals["total_desconto"],
        "desconto_pct_medio": totals["desconto_pct_medio"],
        "observacoes": data.observacoes or "",
        "cgi_status": "assinado",
        "cgi_assinado_em": ts,
        "cgi_assinado_por": user.get("name", ""),
        "aprovacao_cliente": "aprovado",
        "aprovacao_cliente_obs": f"Reprodução do pedido #{original.get('numero_pedido', '')}",
        "aprovacao_cliente_em": ts,
        "aprovacao_cliente_por": user.get("name", ""),
        "aprovacao_comercial": ap_comercial["aprovacao_comercial"],
        "aprovacao_comercial_nivel": ap_comercial["aprovacao_comercial_nivel"],
        "aprovacao_comercial_por": None,
        "aprovacao_comercial_em": None,
        "aprovacao_comercial_obs": "",
        "op_id": None,
        "reproducao_de": order_id,
        "followups": [],
        "created_at": ts,
        "updated_at": ts,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "auto_created": False,
    }
    await db.orders.insert_one(new_order)
    new_order.pop("_id", None)

    # Immediately create the OP
    numero_op = await _generate_op_number(user["tenant_id"])
    op_items = [
        {
            "item": it.get("item", ""),
            "codigo_kuryos": it.get("codigo_kuryos", ""),
            "qtd_planejada": it.get("qtd", 0),
            "qtd_produzida": 0,
            "lote": "",
            "prazo_sla": it.get("prazo_entrega", ""),
        }
        for it in items
    ]
    op = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "numero_op": numero_op,
        "pedido_id": new_order["id"],
        "numero_pedido": numero,
        "cliente_nome": new_order["cliente"].get("nome") or new_order["cliente"].get("razao_social", ""),
        "project_name": new_order.get("project_name", ""),
        "status": "aberta",
        "items": op_items,
        "observacoes": "",
        "created_at": ts,
        "updated_at": ts,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
    }
    await db.ops.insert_one(op)
    op.pop("_id", None)

    # Link OP to new order and set status to em_producao
    await db.orders.update_one(
        {"id": new_order["id"]},
        {"$set": {"op_id": op["id"], "status": "em_producao", "updated_at": ts}}
    )
    new_order["op_id"] = op["id"]
    new_order["status"] = "em_producao"

    return {"order": new_order, "op": op}


# ============ PDF GENERATION ============
@orders_router.get("/{order_id}/pdf")
async def export_order_pdf(order_id: str, request: Request):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=15 * mm, bottomMargin=15 * mm,
        leftMargin=15 * mm, rightMargin=15 * mm,
        title=f"Ordem de Produção {order.get('numero_pedido', '')}",
    )

    KURYOS_BLUE = rl_colors.HexColor("#1F2C5C")
    HEADER_GRAY = rl_colors.HexColor("#F5F5F8")
    DARK_BLUE = rl_colors.HexColor("#2A3A77")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "OrderTitle", parent=styles["Title"],
        fontSize=18, fontName="Helvetica-Bold",
        textColor=rl_colors.black, alignment=TA_CENTER, spaceAfter=2,
    )
    section_num = ParagraphStyle(
        "SectionNum", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica-Bold", textColor=KURYOS_BLUE,
    )
    section_title = ParagraphStyle(
        "SectionTitle", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica-Bold", textColor=KURYOS_BLUE, leftIndent=0,
    )
    cell_label = ParagraphStyle(  # noqa: F841 - kept for future use
        "CellLabel", parent=styles["Normal"],
        fontSize=8.5, fontName="Helvetica-Bold", textColor=rl_colors.black,
    )
    cell_value = ParagraphStyle(  # noqa: F841 - kept for future use
        "CellValue", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica", textColor=rl_colors.black, alignment=TA_CENTER,
    )
    note_style = ParagraphStyle(
        "Note", parent=styles["Normal"],
        fontSize=7.5, fontName="Helvetica", textColor=rl_colors.HexColor("#444444"),
    )

    elements: List[Any] = []

    # ===== TITLE + LOGO =====
    title_table = Table([
        [Paragraph("<u><b>ORDEM DE PRODUÇÃO</b></u>", title_style),
         Paragraph('<font color="#1F2C5C" size="22"><b>KURYOS</b></font><br/><font size="6" color="#1F2C5C">INDÚSTRIA DE COSMÉTICOS</font>',
                   ParagraphStyle("logo", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=22))],
    ], colWidths=[120 * mm, 60 * mm])
    title_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    elements.append(title_table)
    elements.append(Spacer(1, 4 * mm))

    # ===== Helper to render section with numbered header =====
    def render_section(num: str, title: str, rows: List[List[str]], col_widths: List[float] = None):
        # Header
        hdr = Table([[Paragraph(f"<b>{num})</b>", section_num),
                     Paragraph(f"<b>{title}</b>", section_title)]],
                    colWidths=[10 * mm, 170 * mm])
        hdr.setStyle(TableStyle([
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(hdr)
        # Body
        if rows:
            t = Table(rows, colWidths=col_widths or [40 * mm, 140 * mm])
            t.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.6, rl_colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#999999")),
                ("BACKGROUND", (0, 0), (0, -1), HEADER_GRAY),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ]))
            elements.append(t)
        elements.append(Spacer(1, 4 * mm))

    # ===== 1) INFORMAÇÕES INICIAIS =====
    data_pedido_str = ""
    try:
        if order.get("data_pedido"):
            dp = datetime.fromisoformat(order["data_pedido"].replace("Z", "+00:00"))
            data_pedido_str = dp.strftime("%d/%m/%Y")
    except Exception:
        data_pedido_str = order.get("data_pedido", "")

    render_section("1", "INFORMAÇÕES INICIAIS", [
        ["Cliente", order.get("cliente", {}).get("nome", "") or "-"],
        ["# Pedido", order.get("numero_pedido", "") or "-"],
        ["Data", data_pedido_str or "-"],
    ])

    # ===== 2) DADOS DO CLIENTE =====
    cliente = order.get("cliente", {})
    render_section("2", "DADOS DO CLIENTE", [
        ["Razão Social", cliente.get("razao_social", "") or "-"],
        ["CNPJ", cliente.get("cnpj", "") or "-"],
        ["Cidade / UF", cliente.get("cidade_uf", "") or "-"],
        ["Responsável", cliente.get("responsavel", "") or "-"],
        ["Telefone", cliente.get("telefone", "") or "-"],
        ["e-mail", cliente.get("email", "") or "-"],
    ])

    # ===== 3) FRETE =====
    frete = order.get("frete", {})
    render_section("3", "FRETE", [
        ["Tipo de Frete", frete.get("tipo", "FOB") or "-"],
        ["Endereço", frete.get("endereco", "") or "-"],
        ["Cidade / UF", frete.get("cidade_uf", "") or "-"],
        ["Prazo p/ Coleta", frete.get("prazo_coleta", "") or "-"],
    ])

    # ===== 4) PEDIDO =====
    elements.append(Table([[Paragraph("<b>4)</b>", section_num),
                            Paragraph("<b>PEDIDO</b>", section_title)]],
                          colWidths=[10 * mm, 170 * mm]))

    items_header = ["#", "Código Kuryos", "Código Cliente", "Item", "Prazo de Entrega²",
                    "Valor Unitário", "Qtd.", "Valor Total"]
    items_rows = [items_header]
    items_list = order.get("items", []) or []
    total = 0.0
    for idx, it in enumerate(items_list, start=1):
        valor_unit = it.get("valor_unitario", 0) or 0
        qtd = it.get("qtd", 0) or 0
        valor_total = it.get("valor_total") or (valor_unit * qtd)
        total += valor_total
        items_rows.append([
            str(idx),
            it.get("codigo_kuryos", "") or "-",
            it.get("codigo_cliente", "") or "-",
            it.get("item", "") or "-",
            it.get("prazo_entrega", "") or "-",
            f"R$ {valor_unit:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"{qtd:,.0f}".replace(",", "."),
            f"R$ {valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        ])

    items_rows.append(["", "", "", "", "", "", "Total do Pedido",
                       f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")])

    items_table = Table(items_rows,
                        colWidths=[8 * mm, 24 * mm, 24 * mm, 50 * mm, 24 * mm, 22 * mm, 14 * mm, 24 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOX", (0, 0), (-1, -2), 0.6, rl_colors.black),
        ("INNERGRID", (0, 0), (-1, -2), 0.3, rl_colors.HexColor("#999999")),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ALIGN", (0, 1), (-1, -2), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (6, -1), (-1, -1), 0.6, rl_colors.black),
        ("BOX", (6, -1), (-1, -1), 0.6, rl_colors.black),
        ("FONTNAME", (6, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (7, -1), (7, -1), "RIGHT"),
        ("ALIGN", (6, -1), (6, -1), "RIGHT"),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 4 * mm))

    # ===== 5) CONDIÇÕES DE PRAZO E PAGAMENTO =====
    cond = order.get("condicoes", {})
    render_section("5", "CONDIÇÕES DE PRAZO E PAGAMENTO", [
        ["Prazo", cond.get("prazo", "") or "-"],
        ["Forma de Pgto", cond.get("forma_pgto", "") or "-"],
    ])

    # ===== 6) INSUMOS A SEREM ENVIADOS =====
    elements.append(Table([[Paragraph("<b>6)</b>", section_num),
                            Paragraph("<b>INSUMOS À SEREM ENVIADOS</b>", section_title)]],
                          colWidths=[10 * mm, 170 * mm]))
    insumos = order.get("insumos", []) or []
    insumos_rows = [["#", "Item", "Especificações³", "Quantidade"]]
    if insumos:
        for idx, ins in enumerate(insumos, start=1):
            insumos_rows.append([
                str(idx),
                ins.get("item", "") or "-",
                ins.get("especificacoes", "") or "-",
                ins.get("quantidade", "") or "-",
            ])
    else:
        insumos_rows.append(["1", "-", "-", "-"])

    insumos_table = Table(insumos_rows, colWidths=[10 * mm, 70 * mm, 70 * mm, 30 * mm])
    insumos_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.6, rl_colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#999999")),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ALIGN", (0, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(insumos_table)
    elements.append(Spacer(1, 6 * mm))

    # ===== FOOTNOTES =====
    elements.append(HRFlowable(width="100%", thickness=0.3, color=rl_colors.HexColor("#999999"), dash=[2, 2]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "1. Após a confirmação da produção por parte da Kuryos, uma vez não retirado o material indicado no prazo, será cobrado o valor de posição de pallets, no valor de R$ 40,00 / dia.",
        note_style))
    elements.append(Paragraph(
        "2. Prazo de entrega passa a contar no momento da confirmação de recebimento e aprovação de todos os insumos referentes ao pedido, sendo este <b>full service</b> ou <b>terceirização</b>.",
        note_style))
    elements.append(Paragraph(
        "3. [Material] / [Altura x Largura ou Diâmetro x Profundidade] (em milímetros) / [Capacidade]",
        note_style))

    pdf.build(elements)
    buffer.seek(0)
    filename = f"ordem_producao_{order.get('numero_pedido', order_id)}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============ OPS ROUTER ============
ops_router = APIRouter(prefix="/api/ops")


@ops_router.get("")
async def list_ops(request: Request, status: Optional[str] = None, q: Optional[str] = None):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"numero_op": {"$regex": q, "$options": "i"}},
            {"cliente_nome": {"$regex": q, "$options": "i"}},
            {"project_name": {"$regex": q, "$options": "i"}},
        ]
    ops = await db.ops.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return ops


@ops_router.get("/{op_id}")
async def get_op(op_id: str, request: Request):
    user = await get_current_user(request)
    op = await db.ops.find_one({"id": op_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    return op


@ops_router.put("/{op_id}")
async def update_op(op_id: str, data: OPUpdate, request: Request):
    user = await get_current_user(request)
    op = await db.ops.find_one({"id": op_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    payload = data.model_dump(exclude_unset=True)
    if "status" in payload and payload["status"] not in OP_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido. Permitidos: {OP_STATUSES}")
    update_fields: Dict[str, Any] = {k: v for k, v in payload.items() if v is not None or k == "observacoes"}
    update_fields["updated_at"] = now_iso()
    await db.ops.update_one({"id": op_id}, {"$set": update_fields})
    updated = await db.ops.find_one({"id": op_id}, {"_id": 0})

    # On conclusion: compute un/h and push to SKU production history (RN-SK-05)
    if payload.get("status") == "concluida":
        await _record_op_producao_to_sku(updated)

    return updated


async def _record_op_producao_to_sku(op: dict):
    """Calculate un/h from apontamentos and push result into SKU medias_producao."""
    try:
        from workflow_engine import recalc_sku_averages
        apontamentos = op.get("apontamentos") or []
        if not apontamentos:
            return
        total_produzido = sum(a.get("qtd_produzida", 0) for a in apontamentos)
        if total_produzido <= 0:
            return

        horarios = sorted([a["horario"] for a in apontamentos if a.get("horario")])
        duracao_h = 0.0
        if len(horarios) >= 2:
            from datetime import datetime, timezone
            t0 = datetime.fromisoformat(horarios[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(horarios[-1].replace("Z", "+00:00"))
            raw_h = (t1 - t0).total_seconds() / 3600
            pause_h = sum(p.get("duracao_min", 0) for p in (op.get("pausas") or [])) / 60
            duracao_h = max(raw_h - pause_h, 0.0)

        if duracao_h <= 0:
            return
        unh = round(total_produzido / duracao_h, 1)

        # Resolve sku_id via codigo_kuryos on first OP item
        items = op.get("items") or []
        codigo_kuryos = items[0].get("codigo_kuryos", "") if items else ""
        if not codigo_kuryos:
            return
        sku = await db.skus.find_one(
            {"codigo_interno": codigo_kuryos, "tenant_id": op["tenant_id"]}, {"_id": 0}
        )
        if not sku:
            return

        await db.skus.update_one(
            {"id": sku["id"]},
            {"$push": {"medias_producao.historico_producao": {
                "op_id": op["id"],
                "op_numero": op.get("numero_op"),
                "data": now_iso(),
                "qtd_produzida": total_produzido,
                "duracao_h": round(duracao_h, 2),
                "unh": unh,
            }}}
        )
        await recalc_sku_averages(op["tenant_id"], sku["id"])
    except Exception:
        pass  # Non-critical — don't fail the OP update


# ─── Apontamento de produção ─────────────────────────────────────────────────
class ApontamentoCreate(BaseModel):
    item_idx: int = 0
    qtd_produzida: float
    turno: str = "integral"     # manha | tarde | noite | integral
    horario: Optional[str] = None
    observacoes: str = ""


@ops_router.post("/{op_id}/apontar")
async def apontar_producao(op_id: str, data: ApontamentoCreate, request: Request):
    user = await get_current_user(request)
    op = await db.ops.find_one({"id": op_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if op["status"] not in ("em_processo", "aberta"):
        raise HTTPException(status_code=422, detail="Apontamento só é permitido em OPs abertas ou em processo")
    if data.qtd_produzida <= 0:
        raise HTTPException(status_code=400, detail="Quantidade produzida deve ser positiva")

    items = list(op.get("items", []))
    if data.item_idx >= len(items):
        raise HTTPException(status_code=400, detail=f"item_idx {data.item_idx} inválido")

    now = now_iso()
    apontamento = {
        "id": new_id(),
        "item_idx": data.item_idx,
        "item_nome": items[data.item_idx].get("item", ""),
        "qtd_produzida": data.qtd_produzida,
        "turno": data.turno,
        "horario": data.horario or now,
        "observacoes": data.observacoes,
        "por": user["name"],
        "em": now,
    }

    # Accumulate qtd_produzida on the item
    items[data.item_idx]["qtd_produzida"] = (
        float(items[data.item_idx].get("qtd_produzida") or 0) + data.qtd_produzida
    )

    await db.ops.update_one(
        {"id": op_id},
        {
            "$push": {"apontamentos": apontamento},
            "$set": {"items": items, "updated_at": now},
        }
    )
    return await db.ops.find_one({"id": op_id}, {"_id": 0})


# ─── Pausa / Retomada ─────────────────────────────────────────────────────────
class PausaCreate(BaseModel):
    motivo: str
    tipo: str = "outro"   # manutencao | falta_material | almoco | outro
    horario_inicio: Optional[str] = None


@ops_router.post("/{op_id}/pausar")
async def pausar_op(op_id: str, data: PausaCreate, request: Request):
    user = await get_current_user(request)
    op = await db.ops.find_one({"id": op_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if op["status"] != "em_processo":
        raise HTTPException(status_code=422, detail="Só é possível pausar OPs em processo")
    # Check no open pause
    pausas = op.get("pausas", [])
    if any(p.get("horario_fim") is None for p in pausas):
        raise HTTPException(status_code=409, detail="Há uma pausa em aberto — retome antes de pausar novamente")

    now = now_iso()
    pausa = {
        "id": new_id(),
        "tipo": data.tipo,
        "motivo": data.motivo,
        "horario_inicio": data.horario_inicio or now,
        "horario_fim": None,
        "duracao_min": None,
        "por": user["name"],
        "em": now,
    }
    await db.ops.update_one(
        {"id": op_id},
        {"$push": {"pausas": pausa}, "$set": {"status": "pausada", "updated_at": now}}
    )
    return await db.ops.find_one({"id": op_id}, {"_id": 0})


@ops_router.post("/{op_id}/retomar")
async def retomar_op(op_id: str, request: Request):
    user = await get_current_user(request)
    op = await db.ops.find_one({"id": op_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if op["status"] != "pausada":
        raise HTTPException(status_code=422, detail="OP não está pausada")

    now = now_iso()
    pausas = list(op.get("pausas", []))
    # Close the open pause
    for p in reversed(pausas):
        if p.get("horario_fim") is None:
            from datetime import datetime, timezone
            try:
                inicio = datetime.fromisoformat(p["horario_inicio"].replace("Z", "+00:00"))
                fim = datetime.now(timezone.utc)
                p["duracao_min"] = int((fim - inicio).total_seconds() / 60)
            except Exception:
                p["duracao_min"] = None
            p["horario_fim"] = now
            break

    await db.ops.update_one(
        {"id": op_id},
        {"$set": {"pausas": pausas, "status": "em_processo", "updated_at": now}}
    )
    return await db.ops.find_one({"id": op_id}, {"_id": 0})


# ─── Registro de perdas ───────────────────────────────────────────────────────
class PerdaCreate(BaseModel):
    item_idx: int = 0
    tipo: str = "processo"    # processo | material | embalagem | outro
    quantidade: float
    unidade: str = "un"
    motivo: str = ""


@ops_router.post("/{op_id}/perda")
async def registrar_perda(op_id: str, data: PerdaCreate, request: Request):
    user = await get_current_user(request)
    op = await db.ops.find_one({"id": op_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade de perda deve ser positiva")

    items = list(op.get("items", []))
    item_nome = items[data.item_idx].get("item", "") if data.item_idx < len(items) else ""

    now = now_iso()
    perda = {
        "id": new_id(),
        "item_idx": data.item_idx,
        "item_nome": item_nome,
        "tipo": data.tipo,
        "quantidade": data.quantidade,
        "unidade": data.unidade,
        "motivo": data.motivo,
        "por": user["name"],
        "em": now,
    }
    await db.ops.update_one(
        {"id": op_id},
        {"$push": {"perdas": perda}, "$set": {"updated_at": now}}
    )
    return await db.ops.find_one({"id": op_id}, {"_id": 0})
