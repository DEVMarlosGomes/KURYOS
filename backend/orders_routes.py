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
from datetime import datetime, timezone
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


# ============ MODELS ============
class OrderItem(BaseModel):
    codigo_kuryos: str = ""
    codigo_cliente: str = ""
    item: str
    prazo_entrega: str = ""
    valor_unitario: float = 0.0
    qtd: float = 0
    valor_total: float = 0.0


class OrderInsumo(BaseModel):
    item: str = ""
    especificacoes: str = ""
    quantidade: str = ""


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


class OrderCreate(BaseModel):
    pd_request_id: Optional[str] = None
    client_card_id: Optional[str] = None
    numero_pedido: Optional[str] = None
    data_pedido: Optional[str] = None
    cliente: ClienteData = Field(default_factory=ClienteData)
    frete: FreteData = Field(default_factory=FreteData)
    items: List[OrderItem] = []
    condicoes: CondicoesData = Field(default_factory=CondicoesData)
    insumos: List[OrderInsumo] = []
    observacoes: str = ""


class OrderUpdate(BaseModel):
    numero_pedido: Optional[str] = None
    data_pedido: Optional[str] = None
    status: Optional[str] = None
    cliente: Optional[ClienteData] = None
    frete: Optional[FreteData] = None
    items: Optional[List[OrderItem]] = None
    condicoes: Optional[CondicoesData] = None
    insumos: Optional[List[OrderInsumo]] = None
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


def _calculate_totals(items: List[Dict[str, Any]]) -> float:
    total = 0.0
    for it in items:
        valor = (it.get("valor_unitario") or 0) * (it.get("qtd") or 0)
        # Use computed valor_total if provided and >0, else recompute
        existing = it.get("valor_total") or 0
        it["valor_total"] = existing if existing > 0 else round(valor, 2)
        total += it["valor_total"]
    return round(total, 2)


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

    order = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "pd_request_id": pd_request_id,
        "client_card_id": pd_req.get("client_card_id"),
        "numero_pedido": numero,
        "data_pedido": now_iso(),
        "status": "rascunho",
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
        },
        "insumos": [],
        "total_pedido": _calculate_totals(items),
        "observacoes": "",
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
    user = await get_current_user(request)
    # Auto-pull CRM data if client_card_id given and cliente not filled
    cliente = data.cliente.model_dump()
    if data.client_card_id and not cliente.get("razao_social"):
        cliente = await _enrich_from_crm(data.client_card_id, user["tenant_id"])

    items = [it.model_dump() for it in data.items]
    if data.pd_request_id and not items:
        items = await _build_items_from_pd(data.pd_request_id, user["tenant_id"])

    numero = data.numero_pedido or await _generate_order_number(user["tenant_id"])

    order = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "pd_request_id": data.pd_request_id,
        "client_card_id": data.client_card_id,
        "numero_pedido": numero,
        "data_pedido": data.data_pedido or now_iso(),
        "status": "rascunho",
        "project_name": "",
        "cliente": cliente,
        "frete": data.frete.model_dump(),
        "items": items,
        "condicoes": data.condicoes.model_dump(),
        "insumos": [it.model_dump() for it in data.insumos],
        "total_pedido": _calculate_totals(items),
        "observacoes": data.observacoes,
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
    user = await get_current_user(request)
    existing = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    update_fields: Dict[str, Any] = {}
    payload = data.model_dump(exclude_unset=True)

    if "status" in payload and payload["status"] not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido. Permitidos: {ORDER_STATUSES}")

    # CQ hard stops — verify CK prerequisites before starting production
    if payload.get("status") == "em_producao":
        op_tipo = existing.get("tipo", "")
        if op_tipo == "manipulacao":
            await cq_verificar_assepsia_manipulacao(db, user["tenant_id"], order_id)
        elif op_tipo == "envase":
            await cq_verificar_assepsia_envase(db, user["tenant_id"], order_id)
            await cq_verificar_setup_linha(db, user["tenant_id"], order_id)

    for key in ("numero_pedido", "data_pedido", "status", "observacoes"):
        if key in payload:
            update_fields[key] = payload[key]

    for key in ("cliente", "frete", "condicoes"):
        if key in payload and payload[key] is not None:
            update_fields[key] = payload[key]

    if "items" in payload and payload["items"] is not None:
        items = payload["items"]
        update_fields["items"] = items
        update_fields["total_pedido"] = _calculate_totals(items)

    if "insumos" in payload and payload["insumos"] is not None:
        update_fields["insumos"] = payload["insumos"]

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    update_fields["updated_at"] = now_iso()
    await db.orders.update_one({"id": order_id, "tenant_id": user["tenant_id"]}, {"$set": update_fields})
    updated = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return updated


@orders_router.delete("/{order_id}")
async def delete_order(order_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.orders.delete_one({"id": order_id, "tenant_id": user["tenant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return {"message": "Pedido removido"}


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
