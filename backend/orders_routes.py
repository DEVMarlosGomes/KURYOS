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

import database as pg_db
from cq_routes import (
    cq_verificar_assepsia_manipulacao,
    cq_verificar_assepsia_envase,
    cq_verificar_setup_linha,
)

logger = logging.getLogger(__name__)

orders_router = APIRouter(prefix="/api/orders")

get_current_user = None
new_id_func = None
now_iso_func = None


def init_orders(database, auth_func, id_func, iso_func):
    global get_current_user, new_id_func, now_iso_func
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id():
    return new_id_func()


def _now():
    return now_iso_func()


def _row(r):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} if r else None


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

STATUSES_IMUTAVEL = {"confirmado", "em_producao", "concluido"}

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
    desconto_percentual: float = 0.0
    qtd: float = 0
    valor_total: float = 0.0
    tipo_servico: str = "producao"


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
    categoria: str
    ativo: bool = False
    origem: str = "kuryos"
    status: str = "pendente"
    responsavel: str = ""
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
    tipo: str = "FOB"
    endereco: str = ""
    cidade_uf: str = ""
    prazo_coleta: str = ""


class CondicoesData(BaseModel):
    prazo: str = ""
    forma_pgto: str = ""
    condicao_pagamento: str = "000/000/000"


class OrderCreate(BaseModel):
    pd_request_id: Optional[str] = None
    kickoff_id: Optional[str] = None
    client_card_id: Optional[str] = None
    numero_pedido: Optional[str] = None
    data_pedido: Optional[str] = None
    tipo_servico: str = "producao"
    nivel_formalizacao: int = 1
    cliente: ClienteData = Field(default_factory=ClienteData)
    frete: FreteData = Field(default_factory=FreteData)
    items: List[OrderItem] = []
    condicoes: CondicoesData = Field(default_factory=CondicoesData)
    insumos: List[OrderInsumo] = []
    checklist_insumos: List[InsumoChecklistItem] = []
    observacoes: str = ""


class OrderUpdate(BaseModel):
    kickoff_id: Optional[str] = None
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
    cgi_status: Optional[str] = None
    aprovacao_cliente: Optional[str] = None
    aprovacao_cliente_obs: Optional[str] = None
    aprovacao_cliente_em: Optional[str] = None
    justificativa: Optional[str] = None


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
    status: Optional[str] = None
    items: Optional[List[OPItem]] = None
    observacoes: Optional[str] = None


OP_STATUSES = ["aberta", "em_processo", "concluida", "cancelada"]


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
    now = datetime.now(timezone.utc)
    month_str = f"{now.month:02d}"
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()
    count = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM orders WHERE tenant_id=$1 AND created_at >= $2::timestamptz",
        tenant_id, start_of_month,
    )
    seq = (count or 0) + 1
    return f"{month_str}_{seq:02d}"


def _calculate_totals(items: List[Dict[str, Any]]) -> Dict[str, float]:
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
    pct = totals.get("desconto_pct_medio", 0.0)
    if pct <= TIER_AUTO:
        return {"aprovacao_comercial": "nao_necessaria", "aprovacao_comercial_nivel": None}
    if existing:
        cur = existing.get("aprovacao_comercial")
        if cur == "aprovada":
            return {"aprovacao_comercial": "aprovada",
                    "aprovacao_comercial_nivel": existing.get("aprovacao_comercial_nivel")}
    nivel = "gerente_vendas" if pct <= TIER_GERENTE else "diretoria"
    return {"aprovacao_comercial": "pendente", "aprovacao_comercial_nivel": nivel}


async def _validate_kickoff_fk(kickoff_id: Optional[str], tenant_id: str) -> None:
    if not kickoff_id:
        return
    doc = await pg_db.fetch_one(
        "SELECT id FROM kickoffs WHERE id=$1 AND tenant_id=$2", kickoff_id, tenant_id
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Kickoff '{kickoff_id}' não encontrado (Gap A).")


async def _enrich_from_crm(client_card_id: Optional[str], tenant_id: str) -> Dict[str, Any]:
    cliente = {
        "nome": "", "razao_social": "", "cnpj": "",
        "cidade_uf": "", "responsavel": "", "telefone": "", "email": "",
    }
    if not client_card_id:
        return cliente

    card_row = _row(await pg_db.fetch_one(
        "SELECT * FROM cards WHERE id=$1 AND tenant_id=$2", client_card_id, tenant_id
    ))
    if not card_row:
        return cliente
    card = {**card_row, **(card_row.get("data") or {})}

    cliente["nome"] = card.get("nome_cliente", "") or ""
    crm_client_id = card.get("crm_client_id") or card.get("cliente_id")
    crm_client = None
    if crm_client_id:
        crm_client = _row(await pg_db.fetch_one(
            "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2", crm_client_id, tenant_id
        ))

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
        cliente["razao_social"] = card.get("razao_social", "") or card.get("nome_cliente", "")
        cliente["cnpj"] = card.get("cnpj", "")
        cliente["responsavel"] = card.get("responsavel", "") or card.get("contato_nome", "")
        cliente["telefone"] = card.get("telefone", "") or card.get("contato_whatsapp", "")
        cliente["email"] = card.get("email", "") or card.get("contato_email", "")

    return cliente


async def _build_items_from_pd(pd_request_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    pd_req = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_requests WHERE id=$1 AND tenant_id=$2", pd_request_id, tenant_id
    ))
    if not pd_req:
        return []

    project_name = pd_req.get("commercial_name") or pd_req.get("project_name") or ""
    volume = pd_req.get("volume") or ""
    sku = pd_req.get("sku") or pd_req.get("internal_code") or ""
    item_label = f"{project_name} {volume}".strip() if volume else project_name

    return [{
        "codigo_kuryos": sku,
        "codigo_cliente": "",
        "item": item_label,
        "prazo_entrega": "20 Dias",
        "valor_unitario": 0.0,
        "qtd": 0,
        "valor_total": 0.0,
    }]


async def auto_create_order_on_pd_approval(pd_request_id: str, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Called from pd_routes.py when PD transitions to APPROVED. Idempotent."""
    tenant_id = user["tenant_id"]
    existing = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE pd_request_id=$1 AND tenant_id=$2 LIMIT 1",
        pd_request_id, tenant_id,
    ))
    if existing:
        return existing

    pd_req = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_requests WHERE id=$1 AND tenant_id=$2", pd_request_id, tenant_id
    ))
    if not pd_req:
        return None

    cliente = await _enrich_from_crm(pd_req.get("client_card_id"), tenant_id)
    items = await _build_items_from_pd(pd_request_id, tenant_id)
    numero = await _generate_order_number(tenant_id)

    kickoff_id = None
    crm_proj_id = pd_req.get("crm_project_id")
    if crm_proj_id:
        proj = _row(await pg_db.fetch_one(
            "SELECT kickoff_id FROM crm_projects WHERE id=$1 AND tenant_id=$2", crm_proj_id, tenant_id
        ))
        kickoff_id = proj.get("kickoff_id") if proj else None

    checklist_default = [
        {"categoria": c, "ativo": False, "origem": "kuryos", "status": "pendente",
         "responsavel": "", "data_prevista": None, "observacoes": ""}
        for c in CATEGORIAS_INSUMO
    ]
    totals = _calculate_totals(items)
    ap = _eval_aprovacao_comercial(totals)
    now = _now()
    order_id = new_id()

    await pg_db.execute(
        """INSERT INTO orders (
            id, tenant_id, pd_request_id, kickoff_id, client_card_id,
            numero_pedido, data_pedido, status, tipo_servico, nivel_formalizacao,
            project_name, cliente, frete, items, condicoes, insumos, checklist_insumos,
            total_pedido, total_bruto, total_desconto, desconto_pct_medio,
            observacoes, cgi_status, cgi_assinado_em, cgi_assinado_por,
            aprovacao_cliente, aprovacao_cliente_obs, aprovacao_cliente_em,
            aprovacao_comercial, aprovacao_comercial_nivel,
            aprovacao_comercial_por, aprovacao_comercial_em, aprovacao_comercial_obs,
            op_id, auto_created, created_at, updated_at, created_by, created_by_name
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,
            $31,$32,$33,$34,$35,$36,$37,$38,$39
        )""",
        order_id, tenant_id, pd_request_id, kickoff_id, pd_req.get("client_card_id"),
        numero, now, "rascunho", "producao", 1,
        pd_req.get("project_name", ""),
        cliente,
        {"tipo": "FOB", "endereco": "", "cidade_uf": cliente.get("cidade_uf", ""),
         "prazo_coleta": "Até 5 dias úteis após confirmação da produção"},
        items,
        {"prazo": "30 dias", "forma_pgto": "Boleto + Depósito", "condicao_pagamento": "030/000/000"},
        [], checklist_default,
        totals["total_pedido"], totals["total_bruto"], totals["total_desconto"], totals["desconto_pct_medio"],
        "", "pendente", None, None,
        "pendente", "", None,
        ap["aprovacao_comercial"], ap["aprovacao_comercial_nivel"],
        None, None, "",
        None, True, now, now, user["id"], user.get("name", ""),
    )
    logger.info(f"Order auto-created for PD {pd_request_id}: {numero}")
    return _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", order_id))


# ============ ROUTES ============
@orders_router.get("")
async def list_orders(request: Request, status: Optional[str] = None, q: Optional[str] = None):
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
        clauses.append(
            f"(numero_pedido ILIKE ${i} OR cliente->>'nome' ILIKE ${i} "
            f"OR cliente->>'razao_social' ILIKE ${i} OR project_name ILIKE ${i})"
        )
        vals.append(f"%{q}%")
        i += 1
    rows = await pg_db.fetch_all(
        f"SELECT * FROM orders WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 1000",
        *vals,
    )
    return [_row(r) for r in rows]


@orders_router.get("/{order_id}")
async def get_order(order_id: str, request: Request):
    user = await get_current_user(request)
    order = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE id=$1 AND tenant_id=$2", order_id, user["tenant_id"]
    ))
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order


@orders_router.get("/reorder/{client_card_id}")
async def get_reorder_draft(client_card_id: str, request: Request):
    """Return a pre-populated draft order based on the most recent order for a CRM client card."""
    user = await get_current_user(request)
    last_order = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE client_card_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 1",
        client_card_id, user["tenant_id"],
    ))
    if not last_order:
        raise HTTPException(status_code=404, detail="Nenhum pedido anterior encontrado para este cliente")

    numero = await _generate_order_number(user["tenant_id"])
    now = _now()
    draft = {
        **last_order,
        "id": None,
        "numero_pedido": numero,
        "data_pedido": now,
        "status": "rascunho",
        "observacoes": "",
        "auto_created": False,
        "is_reorder_draft": True,
        "reorder_from": last_order["id"],
        "created_at": now,
        "updated_at": now,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
    }
    return draft


@orders_router.post("")
async def create_order(data: OrderCreate, request: Request):
    import re
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if data.tipo_servico not in TIPOS_SERVICO:
        raise HTTPException(status_code=400, detail=f"tipo_servico inválido. Permitidos: {TIPOS_SERVICO}")

    condicoes = data.condicoes.model_dump()
    cpgto = condicoes.get("condicao_pagamento", "")
    if cpgto and not re.match(CONDICAO_PGTO_RE, cpgto):
        raise HTTPException(status_code=400, detail="condicao_pagamento deve ter formato NNN/NNN/NNN (RN-PI-08)")

    await _validate_kickoff_fk(data.kickoff_id, tid)

    cliente = data.cliente.model_dump()
    if data.client_card_id and not cliente.get("razao_social"):
        cliente = await _enrich_from_crm(data.client_card_id, tid)

    items = [it.model_dump() for it in data.items]
    if data.pd_request_id and not items:
        items = await _build_items_from_pd(data.pd_request_id, tid)

    checklist = [c.model_dump() for c in data.checklist_insumos] if data.checklist_insumos else [
        {"categoria": c, "ativo": False, "origem": "kuryos", "status": "pendente",
         "responsavel": "", "data_prevista": None, "observacoes": ""}
        for c in CATEGORIAS_INSUMO
    ]

    numero = data.numero_pedido or await _generate_order_number(tid)
    totals = _calculate_totals(items)
    ap = _eval_aprovacao_comercial(totals)
    now = _now()
    order_id = new_id()

    await pg_db.execute(
        """INSERT INTO orders (
            id, tenant_id, pd_request_id, kickoff_id, client_card_id,
            numero_pedido, data_pedido, status, tipo_servico, nivel_formalizacao,
            project_name, cliente, frete, items, condicoes, insumos, checklist_insumos,
            total_pedido, total_bruto, total_desconto, desconto_pct_medio,
            observacoes, cgi_status, cgi_assinado_em, cgi_assinado_por,
            aprovacao_cliente, aprovacao_cliente_obs, aprovacao_cliente_em,
            aprovacao_comercial, aprovacao_comercial_nivel,
            aprovacao_comercial_por, aprovacao_comercial_em, aprovacao_comercial_obs,
            op_id, auto_created, created_at, updated_at, created_by, created_by_name
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,
            $31,$32,$33,$34,$35,$36,$37,$38,$39
        )""",
        order_id, tid, data.pd_request_id, data.kickoff_id, data.client_card_id,
        numero, data.data_pedido or now, "rascunho", data.tipo_servico, data.nivel_formalizacao,
        "",
        cliente,
        data.frete.model_dump(),
        items, condicoes,
        [it.model_dump() for it in data.insumos], checklist,
        totals["total_pedido"], totals["total_bruto"], totals["total_desconto"], totals["desconto_pct_medio"],
        data.observacoes, "pendente", None, None,
        "pendente", "", None,
        ap["aprovacao_comercial"], ap["aprovacao_comercial_nivel"],
        None, None, "",
        None, False, now, now, user["id"], user.get("name", ""),
    )
    return _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", order_id))


@orders_router.put("/{order_id}")
async def update_order(order_id: str, data: OrderUpdate, request: Request):
    import re
    user = await get_current_user(request)
    tid = user["tenant_id"]
    existing = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE id=$1 AND tenant_id=$2", order_id, tid
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    update_fields: Dict[str, Any] = {}
    payload = data.model_dump(exclude_unset=True)

    if "status" in payload and payload["status"] not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido. Permitidos: {ORDER_STATUSES}")

    if "kickoff_id" in payload:
        await _validate_kickoff_fk(payload["kickoff_id"], tid)

    if payload.get("status") == "confirmado":
        if existing.get("cgi_status", "pendente") != "assinado":
            raise HTTPException(status_code=422, detail="CGI não assinado. Assine o Contrato Geral de Industrialização antes de confirmar o pedido. (RN-PI-01)")
        if existing.get("aprovacao_comercial") == "pendente":
            nivel = existing.get("aprovacao_comercial_nivel", "gerente_vendas")
            raise HTTPException(status_code=422, detail=f"Aprovação comercial pendente (desconto > {TIER_AUTO}%). Requer aprovação de {nivel.replace('_', ' ')} antes de confirmar. (RN-PI-10)")

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
            old_vals = {k: existing.get(k) for k in blocked}
            new_vals = {k: payload.get(k) for k in blocked}
            await pg_db.execute(
                """INSERT INTO order_audit_log
                   (id, tenant_id, order_id, order_numero, user_id, user_name, action,
                    fields_changed, before_data, after_data, justificativa, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                new_id(), tid, order_id, existing.get("numero_pedido", ""),
                user["id"], user.get("name", ""), "edit_locked",
                sorted(blocked), old_vals, new_vals, justificativa, _now(),
            )

    if payload.get("status") == "em_producao":
        op_tipo = existing.get("tipo", "")
        if op_tipo == "manipulacao":
            await cq_verificar_assepsia_manipulacao(None, tid, order_id)
        elif op_tipo == "envase":
            await cq_verificar_assepsia_envase(None, tid, order_id)
            await cq_verificar_setup_linha(None, tid, order_id)

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
        ap = _eval_aprovacao_comercial(totals, existing)
        update_fields["aprovacao_comercial"] = ap["aprovacao_comercial"]
        update_fields["aprovacao_comercial_nivel"] = ap["aprovacao_comercial_nivel"]
        if ap["aprovacao_comercial"] == "pendente":
            update_fields["aprovacao_comercial_por"] = None
            update_fields["aprovacao_comercial_em"] = None

    if "insumos" in payload and payload["insumos"] is not None:
        update_fields["insumos"] = payload["insumos"]

    if "checklist_insumos" in payload and payload["checklist_insumos"] is not None:
        update_fields["checklist_insumos"] = payload["checklist_insumos"]

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    if payload.get("status") == "concluido" and existing.get("status") != "concluido":
        if not existing.get("followups"):
            now_dt = datetime.now(timezone.utc)
            marcos_dias = [("1m", 30), ("3m", 90), ("6m", 180)]
            update_fields["followups"] = [
                {"marco": marco, "vence_em": (now_dt + timedelta(days=dias)).isoformat(), "notificado": False}
                for marco, dias in marcos_dias
            ]

    update_fields["updated_at"] = _now()
    cols = []
    vals: list = []
    i = 1
    for key, val in update_fields.items():
        cols.append(f"{key}=${i}")
        vals.append(val)
        i += 1
    await pg_db.execute(
        f"UPDATE orders SET {', '.join(cols)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, order_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", order_id))


@orders_router.post("/{order_id}/aprovar-cliente")
async def aprovar_cliente(order_id: str, request: Request):
    user = await get_current_user(request)
    body_raw = await request.json()
    obs = body_raw.get("observacoes", "")
    existing = _row(await pg_db.fetch_one(
        "SELECT id FROM orders WHERE id=$1 AND tenant_id=$2", order_id, user["tenant_id"]
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    now = _now()
    await pg_db.execute(
        """UPDATE orders SET aprovacao_cliente='aprovado', aprovacao_cliente_obs=$1,
           aprovacao_cliente_em=$2, aprovacao_cliente_por=$3, updated_at=$2
           WHERE id=$4 AND tenant_id=$5""",
        obs, now, user.get("name", ""), order_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", order_id))


@orders_router.post("/{order_id}/aprovar-comercial")
async def aprovar_comercial(order_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    obs = body.get("observacoes", "")
    existing = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE id=$1 AND tenant_id=$2", order_id, user["tenant_id"]
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if existing.get("aprovacao_comercial") == "nao_necessaria":
        raise HTTPException(status_code=400, detail="Este pedido não requer aprovação comercial.")
    nivel = existing.get("aprovacao_comercial_nivel", "gerente_vendas")
    roles_ok = {"admin"} if nivel == "diretoria" else {"sales_ops", "admin"}
    if user.get("role") not in roles_ok:
        raise HTTPException(status_code=403, detail=f"Aprovação de nível '{nivel}' requer role: {sorted(roles_ok)}.")
    now = _now()
    await pg_db.execute(
        """UPDATE orders SET aprovacao_comercial='aprovada', aprovacao_comercial_obs=$1,
           aprovacao_comercial_em=$2, aprovacao_comercial_por=$3, updated_at=$2
           WHERE id=$4 AND tenant_id=$5""",
        obs, now, user.get("name", ""), order_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", order_id))


@orders_router.post("/{order_id}/rejeitar-comercial")
async def rejeitar_comercial(order_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    obs = body.get("observacoes", "")
    existing = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE id=$1 AND tenant_id=$2", order_id, user["tenant_id"]
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    nivel = existing.get("aprovacao_comercial_nivel", "gerente_vendas")
    roles_ok = {"admin"} if nivel == "diretoria" else {"sales_ops", "admin"}
    if user.get("role") not in roles_ok:
        raise HTTPException(status_code=403, detail=f"Rejeição de nível '{nivel}' requer role: {sorted(roles_ok)}.")
    now = _now()
    await pg_db.execute(
        """UPDATE orders SET aprovacao_comercial='rejeitada', aprovacao_comercial_obs=$1,
           aprovacao_comercial_em=$2, aprovacao_comercial_por=$3, updated_at=$2
           WHERE id=$4 AND tenant_id=$5""",
        obs, now, user.get("name", ""), order_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", order_id))


@orders_router.delete("/{order_id}")
async def delete_order(order_id: str, request: Request):
    user = await get_current_user(request)
    result = await pg_db.execute(
        "DELETE FROM orders WHERE id=$1 AND tenant_id=$2", order_id, user["tenant_id"]
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return {"message": "Pedido removido"}


@orders_router.post("/{order_id}/sign-cgi")
async def sign_cgi(order_id: str, request: Request):
    user = await get_current_user(request)
    order = _row(await pg_db.fetch_one(
        "SELECT id FROM orders WHERE id=$1 AND tenant_id=$2", order_id, user["tenant_id"]
    ))
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    now = _now()
    await pg_db.execute(
        "UPDATE orders SET cgi_status='assinado', cgi_assinado_em=$1, cgi_assinado_por=$2, updated_at=$1 WHERE id=$3 AND tenant_id=$4",
        now, user.get("name", ""), order_id, user["tenant_id"],
    )
    return _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", order_id))


# ============ OP — CREATE FROM ORDER ============
async def _generate_op_number(tenant_id: str) -> str:
    now = datetime.now(timezone.utc)
    year = now.year
    count = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM ops WHERE tenant_id=$1 AND created_at >= $2::timestamptz",
        tenant_id, f"{year}-01-01T00:00:00Z",
    )
    return f"OP-{year}-{(count or 0) + 1:03d}"


@orders_router.post("/{order_id}/create-op")
async def create_op_from_order(order_id: str, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    order = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE id=$1 AND tenant_id=$2", order_id, tid
    ))
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.get("status") not in ("confirmado", "em_producao"):
        raise HTTPException(status_code=422, detail="OP só pode ser gerada a partir de um pedido Confirmado.")
    if order.get("op_id"):
        existing_op = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", order["op_id"], tid))
        if existing_op:
            return existing_op

    numero_op = await _generate_op_number(tid)
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
    op_id = new_id()
    now = _now()
    await pg_db.execute(
        """INSERT INTO ops (id, tenant_id, numero_op, pedido_id, pedido_numero,
           cliente_nome, project_name, status, items, observacoes,
           created_at, updated_at, created_by, created_by_name)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11,$12,$13)""",
        op_id, tid, numero_op, order_id, order.get("numero_pedido", ""),
        order.get("cliente", {}).get("nome") or order.get("cliente", {}).get("razao_social", ""),
        order.get("project_name", ""), "aberta", op_items, "",
        now, user["id"], user.get("name", ""),
    )
    await pg_db.execute(
        "UPDATE orders SET op_id=$1, status='em_producao', updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        op_id, now, order_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1", op_id))


# ============ R15: REPRODUZIR PEDIDO ============
@orders_router.post("/{order_id}/reproduzir")
async def reproduzir_pedido(order_id: str, data: ReproduzirInput, request: Request):
    import copy
    user = await get_current_user(request)
    tid = user["tenant_id"]
    if user.get("role") not in {"admin", "vendedor", "sales_ops"}:
        raise HTTPException(status_code=403, detail="Permissão negada. Apenas Comercial e Admin podem reproduzir pedidos.")

    original = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE id=$1 AND tenant_id=$2", order_id, tid
    ))
    if not original:
        raise HTTPException(status_code=404, detail="Pedido original não encontrado")
    if original.get("status") not in STATUSES_IMUTAVEL:
        raise HTTPException(status_code=422, detail="Só é possível reproduzir pedidos Confirmados, Em Produção ou Concluídos.")

    items = copy.deepcopy(original.get("items") or [])
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
    ap = _eval_aprovacao_comercial(totals)
    numero = await _generate_order_number(tid)
    frete = copy.deepcopy(original.get("frete") or {})
    if data.endereco_entrega is not None:
        frete["endereco"] = data.endereco_entrega

    checklist_default = [
        {"categoria": c, "ativo": False, "origem": "kuryos", "status": "pendente",
         "responsavel": "", "data_prevista": None, "observacoes": ""}
        for c in CATEGORIAS_INSUMO
    ]
    ts = _now()
    new_order_id = new_id()

    await pg_db.execute(
        """INSERT INTO orders (
            id, tenant_id, pd_request_id, kickoff_id, client_card_id,
            numero_pedido, data_pedido, status, tipo_servico, nivel_formalizacao,
            project_name, cliente, frete, items, condicoes, insumos, checklist_insumos,
            total_pedido, total_bruto, total_desconto, desconto_pct_medio,
            observacoes, cgi_status, cgi_assinado_em, cgi_assinado_por,
            aprovacao_cliente, aprovacao_cliente_obs, aprovacao_cliente_em, aprovacao_cliente_por,
            aprovacao_comercial, aprovacao_comercial_nivel,
            aprovacao_comercial_por, aprovacao_comercial_em, aprovacao_comercial_obs,
            op_id, auto_created, reproducao_de, followups,
            created_at, updated_at, created_by, created_by_name
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
            $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,
            $31,$32,$33,$34,$35,$36,$37,$38,$39,$40,$41,$42
        )""",
        new_order_id, tid, original.get("pd_request_id"), original.get("kickoff_id"), original.get("client_card_id"),
        numero, ts, "confirmado", original.get("tipo_servico", "producao"), original.get("nivel_formalizacao", 1),
        original.get("project_name", ""),
        copy.deepcopy(original.get("cliente") or {}),
        frete, items,
        copy.deepcopy(original.get("condicoes") or {}),
        [], checklist_default,
        totals["total_pedido"], totals["total_bruto"], totals["total_desconto"], totals["desconto_pct_medio"],
        data.observacoes or "", "assinado", ts, user.get("name", ""),
        "aprovado", f"Reprodução do pedido #{original.get('numero_pedido', '')}", ts, user.get("name", ""),
        ap["aprovacao_comercial"], ap["aprovacao_comercial_nivel"],
        None, None, "",
        None, False, order_id, [],
        ts, ts, user["id"], user.get("name", ""),
    )
    new_order = _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", new_order_id))

    numero_op = await _generate_op_number(tid)
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
    op_id = new_id()
    await pg_db.execute(
        """INSERT INTO ops (id, tenant_id, numero_op, pedido_id, pedido_numero,
           cliente_nome, project_name, status, items, observacoes,
           created_at, updated_at, created_by, created_by_name)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$11,$12,$13)""",
        op_id, tid, numero_op, new_order_id, numero,
        (new_order.get("cliente") or {}).get("nome") or (new_order.get("cliente") or {}).get("razao_social", ""),
        new_order.get("project_name", ""), "aberta", op_items, "",
        ts, user["id"], user.get("name", ""),
    )
    await pg_db.execute(
        "UPDATE orders SET op_id=$1, status='em_producao', updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        op_id, ts, new_order_id, tid,
    )
    op = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1", op_id))
    new_order = _row(await pg_db.fetch_one("SELECT * FROM orders WHERE id=$1", new_order_id))
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
    order = _row(await pg_db.fetch_one(
        "SELECT * FROM orders WHERE id=$1 AND tenant_id=$2", order_id, user["tenant_id"]
    ))
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
    note_style = ParagraphStyle(
        "Note", parent=styles["Normal"],
        fontSize=7.5, fontName="Helvetica", textColor=rl_colors.HexColor("#444444"),
    )

    elements: List[Any] = []

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

    def render_section(num: str, title: str, rows: List[List[str]], col_widths: List[float] = None):
        hdr = Table([[Paragraph(f"<b>{num})</b>", section_num),
                     Paragraph(f"<b>{title}</b>", section_title)]],
                    colWidths=[10 * mm, 170 * mm])
        hdr.setStyle(TableStyle([
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(hdr)
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

    cliente = order.get("cliente") or {}
    render_section("2", "DADOS DO CLIENTE", [
        ["Razão Social", cliente.get("razao_social", "") or "-"],
        ["CNPJ", cliente.get("cnpj", "") or "-"],
        ["Cidade / UF", cliente.get("cidade_uf", "") or "-"],
        ["Responsável", cliente.get("responsavel", "") or "-"],
        ["Telefone", cliente.get("telefone", "") or "-"],
        ["e-mail", cliente.get("email", "") or "-"],
    ])

    frete = order.get("frete") or {}
    render_section("3", "FRETE", [
        ["Tipo de Frete", frete.get("tipo", "FOB") or "-"],
        ["Endereço", frete.get("endereco", "") or "-"],
        ["Cidade / UF", frete.get("cidade_uf", "") or "-"],
        ["Prazo p/ Coleta", frete.get("prazo_coleta", "") or "-"],
    ])

    elements.append(Table([[Paragraph("<b>4)</b>", section_num),
                            Paragraph("<b>PEDIDO</b>", section_title)]],
                          colWidths=[10 * mm, 170 * mm]))

    items_header = ["#", "Código Kuryos", "Código Cliente", "Item", "Prazo de Entrega²",
                    "Valor Unitário", "Qtd.", "Valor Total"]
    items_rows = [items_header]
    items_list = order.get("items") or []
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

    cond = order.get("condicoes") or {}
    render_section("5", "CONDIÇÕES DE PRAZO E PAGAMENTO", [
        ["Prazo", cond.get("prazo", "") or "-"],
        ["Forma de Pgto", cond.get("forma_pgto", "") or "-"],
    ])

    elements.append(Table([[Paragraph("<b>6)</b>", section_num),
                            Paragraph("<b>INSUMOS À SEREM ENVIADOS</b>", section_title)]],
                          colWidths=[10 * mm, 170 * mm]))
    insumos = order.get("insumos") or []
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
    tid = user["tenant_id"]
    clauses = ["tenant_id=$1"]
    vals: list = [tid]
    i = 2
    if status:
        clauses.append(f"status=${i}")
        vals.append(status)
        i += 1
    if q:
        clauses.append(
            f"(numero_op ILIKE ${i} OR cliente_nome ILIKE ${i} OR project_name ILIKE ${i})"
        )
        vals.append(f"%{q}%")
        i += 1
    rows = await pg_db.fetch_all(
        f"SELECT * FROM ops WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 1000",
        *vals,
    )
    return [_row(r) for r in rows]


@ops_router.get("/{op_id}")
async def get_op(op_id: str, request: Request):
    user = await get_current_user(request)
    op = _row(await pg_db.fetch_one(
        "SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", op_id, user["tenant_id"]
    ))
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    return op


@ops_router.put("/{op_id}")
async def update_op(op_id: str, data: OPUpdate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    op = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", op_id, tid))
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    payload = data.model_dump(exclude_unset=True)
    if "status" in payload and payload["status"] not in OP_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido. Permitidos: {OP_STATUSES}")

    update_fields: Dict[str, Any] = {k: v for k, v in payload.items() if v is not None or k == "observacoes"}
    update_fields["updated_at"] = _now()

    cols = []
    vals: list = []
    i = 1
    for key, val in update_fields.items():
        cols.append(f"{key}=${i}")
        vals.append(val)
        i += 1
    await pg_db.execute(
        f"UPDATE ops SET {', '.join(cols)} WHERE id=${i} AND tenant_id=${i+1}",
        *vals, op_id, tid,
    )
    updated = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1", op_id))

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
            t0 = datetime.fromisoformat(horarios[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(horarios[-1].replace("Z", "+00:00"))
            raw_h = (t1 - t0).total_seconds() / 3600
            pause_h = sum(p.get("duracao_min", 0) for p in (op.get("pausas") or [])) / 60
            duracao_h = max(raw_h - pause_h, 0.0)

        if duracao_h <= 0:
            return
        unh = round(total_produzido / duracao_h, 1)

        items = op.get("items") or []
        codigo_kuryos = items[0].get("codigo_kuryos", "") if items else ""
        if not codigo_kuryos:
            return
        sku = _row(await pg_db.fetch_one(
            "SELECT id, tenant_id FROM skus WHERE codigo_interno=$1 AND tenant_id=$2",
            codigo_kuryos, op["tenant_id"],
        ))
        if not sku:
            return

        new_entry = {
            "op_id": op["id"],
            "op_numero": op.get("numero_op"),
            "data": _now(),
            "qtd_produzida": total_produzido,
            "duracao_h": round(duracao_h, 2),
            "unh": unh,
        }
        await pg_db.execute(
            """UPDATE skus SET medias_producao = jsonb_set(
                COALESCE(medias_producao, '{}'),
                '{historico_producao}',
                COALESCE(medias_producao->'historico_producao', '[]') || $1::jsonb
            ), updated_at = NOW() WHERE id=$2""",
            [new_entry], sku["id"],
        )
        await recalc_sku_averages(op["tenant_id"], sku["id"])
    except Exception:
        pass


# ─── Apontamento de produção ─────────────────────────────────────────────────
class ApontamentoCreate(BaseModel):
    item_idx: int = 0
    qtd_produzida: float
    turno: str = "integral"
    horario: Optional[str] = None
    observacoes: str = ""


@ops_router.post("/{op_id}/apontar")
async def apontar_producao(op_id: str, data: ApontamentoCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    op = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", op_id, tid))
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if op["status"] not in ("em_processo", "aberta"):
        raise HTTPException(status_code=422, detail="Apontamento só é permitido em OPs abertas ou em processo")
    if data.qtd_produzida <= 0:
        raise HTTPException(status_code=400, detail="Quantidade produzida deve ser positiva")

    items = list(op.get("items") or [])
    if data.item_idx >= len(items):
        raise HTTPException(status_code=400, detail=f"item_idx {data.item_idx} inválido")

    now = _now()
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
    items[data.item_idx]["qtd_produzida"] = (
        float(items[data.item_idx].get("qtd_produzida") or 0) + data.qtd_produzida
    )
    await pg_db.execute(
        "UPDATE ops SET apontamentos = apontamentos || $1::jsonb, items = $2, updated_at = $3 WHERE id=$4 AND tenant_id=$5",
        [apontamento], items, now, op_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1", op_id))


# ─── Pausa / Retomada ─────────────────────────────────────────────────────────
class PausaCreate(BaseModel):
    motivo: str
    tipo: str = "outro"
    horario_inicio: Optional[str] = None


@ops_router.post("/{op_id}/pausar")
async def pausar_op(op_id: str, data: PausaCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    op = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", op_id, tid))
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if op["status"] != "em_processo":
        raise HTTPException(status_code=422, detail="Só é possível pausar OPs em processo")
    pausas = op.get("pausas") or []
    if any(p.get("horario_fim") is None for p in pausas):
        raise HTTPException(status_code=409, detail="Há uma pausa em aberto — retome antes de pausar novamente")

    now = _now()
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
    await pg_db.execute(
        "UPDATE ops SET pausas = pausas || $1::jsonb, status='pausada', updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        [pausa], now, op_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1", op_id))


@ops_router.post("/{op_id}/retomar")
async def retomar_op(op_id: str, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    op = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", op_id, tid))
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if op["status"] != "pausada":
        raise HTTPException(status_code=422, detail="OP não está pausada")

    now = _now()
    pausas = list(op.get("pausas") or [])
    for p in reversed(pausas):
        if p.get("horario_fim") is None:
            try:
                inicio = datetime.fromisoformat(p["horario_inicio"].replace("Z", "+00:00"))
                fim = datetime.now(timezone.utc)
                p["duracao_min"] = int((fim - inicio).total_seconds() / 60)
            except Exception:
                p["duracao_min"] = None
            p["horario_fim"] = now
            break

    await pg_db.execute(
        "UPDATE ops SET pausas=$1, status='em_processo', updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        pausas, now, op_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1", op_id))


# ─── Registro de perdas ───────────────────────────────────────────────────────
class PerdaCreate(BaseModel):
    item_idx: int = 0
    tipo: str = "processo"
    quantidade: float
    unidade: str = "un"
    motivo: str = ""


@ops_router.post("/{op_id}/perda")
async def registrar_perda(op_id: str, data: PerdaCreate, request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    op = _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1 AND tenant_id=$2", op_id, tid))
    if not op:
        raise HTTPException(status_code=404, detail="OP não encontrada")
    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade de perda deve ser positiva")

    items = list(op.get("items") or [])
    item_nome = items[data.item_idx].get("item", "") if data.item_idx < len(items) else ""

    now = _now()
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
    await pg_db.execute(
        "UPDATE ops SET perdas = perdas || $1::jsonb, updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        [perda], now, op_id, tid,
    )
    return _row(await pg_db.fetch_one("SELECT * FROM ops WHERE id=$1", op_id))
