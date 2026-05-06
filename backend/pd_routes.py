"""
P&D (Pesquisa & Desenvolvimento) Module - Complete Routes
Collections: pd_requests, pd_request_status_history, pd_developments,
             pd_formulas, pd_formula_items, pd_tests, pd_samples,
             pd_approvals, pd_costs, pd_documents
"""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid
import io
import logging
import asyncio
from validation_utils import clean_text, normalize_cnpj, normalize_email, normalize_phone, is_valid_cnpj, is_valid_email, is_valid_phone
from workflow_engine import create_workflow_task, audit_log, get_blocking_tasks
from rbac import (
    require_roles,
    has_role,
    can_view_formula_composition,
    can_view_live_document_revisions,
    PD_READ,
    PD_FULL,
    PD_WRITE,
    HOMOLOGACAO_WRITE,
    HOMOLOGACAO_APPROVE,
    DOC_REVIEWERS,
    QA_APPROVERS,
    ADMIN_ONLY,
)

logger = logging.getLogger(__name__)

pd_router = APIRouter(prefix="/api/pd")

# Will be set from server.py
db = None
get_current_user = None
new_id_func = None
now_iso_func = None
put_object_func = None

def init_pd(database, auth_func, id_func, iso_func, storage_func=None):
    global db, get_current_user, new_id_func, now_iso_func, put_object_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func
    put_object_func = storage_func

def new_id():
    return new_id_func()

def now_iso():
    return now_iso_func()


def _validate_supplier_payload(payload: dict) -> dict:
    payload["razao_social"] = clean_text(payload.get("razao_social", ""))
    payload["nome_fantasia"] = clean_text(payload.get("nome_fantasia", ""))
    payload["contato_nome"] = clean_text(payload.get("contato_nome", ""))
    payload["contato_email"] = normalize_email(payload.get("contato_email", ""))
    payload["contato_telefone"] = normalize_phone(payload.get("contato_telefone", ""))
    payload["cnpj"] = clean_text(payload.get("cnpj", ""))
    payload["cnpj_normalized"] = normalize_cnpj(payload.get("cnpj", ""))

    if not payload["razao_social"]:
        raise HTTPException(status_code=400, detail="Razao social obrigatoria")
    if payload["cnpj_normalized"] and not is_valid_cnpj(payload["cnpj_normalized"]):
        raise HTTPException(status_code=400, detail="CNPJ do fornecedor invalido")
    if payload["contato_email"] and not is_valid_email(payload["contato_email"]):
        raise HTTPException(status_code=400, detail="E-mail do fornecedor invalido")
    if payload["contato_telefone"] and not is_valid_phone(payload["contato_telefone"]):
        raise HTTPException(status_code=400, detail="Telefone do fornecedor invalido")

    return payload

# ============ STATUS DEFINITIONS ============

VALID_STATUSES = ["OPEN", "IN_PROGRESS", "IN_TESTS", "WAITING_APPROVAL", "APPROVED", "COMPLETED", "REJECTED"]

ALLOWED_TRANSITIONS = {
    "OPEN": ["IN_PROGRESS"],
    "IN_PROGRESS": ["IN_TESTS"],
    "IN_TESTS": ["WAITING_APPROVAL"],
    "WAITING_APPROVAL": ["APPROVED", "REJECTED"],
    "APPROVED": ["COMPLETED"],
    "REJECTED": ["IN_PROGRESS"],
    "COMPLETED": [],
}

STATUS_LABELS = {
    "OPEN": "Aberto",
    "IN_PROGRESS": "Em Desenvolvimento",
    "IN_TESTS": "Em Testes",
    "WAITING_APPROVAL": "Aguardando Aprovação",
    "APPROVED": "Aprovado",
    "COMPLETED": "Concluído",
    "REJECTED": "Rejeitado",
}

# ============ PYDANTIC MODELS ============

class PDRequestCreate(BaseModel):
    client_card_id: Optional[str] = None
    client_name: Optional[str] = None
    project_name: str
    technical_name: Optional[str] = None
    commercial_name: Optional[str] = None
    internal_code: Optional[str] = None
    request_type: str = "Produto Novo"
    category: Optional[str] = None
    description: Optional[str] = None
    references: Optional[str] = None
    restrictions: Optional[str] = None
    volume: Optional[str] = None
    packaging: Optional[str] = None
    priority: str = "Normal"
    deadline: Optional[str] = None
    is_internal_research: bool = False
    kickoff_completed: bool = False

class PDRequestUpdate(BaseModel):
    project_name: Optional[str] = None
    technical_name: Optional[str] = None
    commercial_name: Optional[str] = None
    internal_code: Optional[str] = None
    request_type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    references: Optional[str] = None
    restrictions: Optional[str] = None
    volume: Optional[str] = None
    packaging: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None
    sku: Optional[str] = None
    kickoff_completed: Optional[bool] = None

class StatusTransition(BaseModel):
    new_status: str
    comment: Optional[str] = None

class FormulaCreate(BaseModel):
    name: str
    notes: Optional[str] = None
    volume: Optional[float] = None
    volume_unit: Optional[str] = "mL"
    indice_perdas: Optional[float] = 0
    cotacao_usd: Optional[float] = 6.00

class FormulaUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    volume: Optional[float] = None
    volume_unit: Optional[str] = None
    indice_perdas: Optional[float] = None
    cotacao_usd: Optional[float] = None

class FormulaItemCreate(BaseModel):
    ingredient_name: str
    percentage: float
    price_per_kg: float = 0.0
    fornecedor: Optional[str] = ""
    phase: Optional[str] = None
    function: Optional[str] = None
    catalog_id: Optional[str] = None  # Link to cost catalog

class FormulaItemUpdate(BaseModel):
    ingredient_name: Optional[str] = None
    percentage: Optional[float] = None
    price_per_kg: Optional[float] = None
    fornecedor: Optional[str] = None
    phase: Optional[str] = None
    function: Optional[str] = None
    catalog_id: Optional[str] = None

class TestCreate(BaseModel):
    test_type: str
    status: str = "PENDING"
    # Structured test data
    dados: Optional[Dict[str, Any]] = None

class TestUpdate(BaseModel):
    status: Optional[str] = None
    dados: Optional[Dict[str, Any]] = None

class SampleCreate(BaseModel):
    formula_version: int
    sent_to_client: bool = False
    feedback: Optional[str] = None

class SampleUpdate(BaseModel):
    sent_to_client: Optional[bool] = None
    feedback: Optional[str] = None

class ApprovalCreate(BaseModel):
    approved_by_client: bool = False
    approved_by_internal: bool = False
    notes: Optional[str] = None

class CostCreate(BaseModel):
    ingredient_cost: float = 0.0
    packaging_cost: float = 0.0
    labor_cost: float = 0.0

class DocumentCreate(BaseModel):
    doc_type: str
    file_url: str
    file_name: Optional[str] = None


class LiveDocumentGenerate(BaseModel):
    reason: str = ""
    changed_fields: List[str] = []


LIVE_DOCUMENT_TYPES = {"ficha_tecnica", "epa"}
LIVE_DOCUMENT_REVIEW_ROLES = {"admin", "gestor", "lider_pd", "qa", "formulador", "engenharia_produto"}

# Status liberados: homologada (aprovada), pendente, rejeitada, suspensa (bloqueio temporario por nao conformidade)
MP_BLOCKED_STATUSES = {"rejeitada", "suspensa"}
MP_OK_STATUSES = {"homologada"}

STABILITY_CONDITIONS = [
    {"code": "ambient", "label": "Ambiente", "temperature": "25C", "humidity": "60% UR", "protected_from_light": False},
    {"code": "climate_30_75", "label": "Climatizada 30C/75%", "temperature": "30C", "humidity": "75% UR", "protected_from_light": False},
    {"code": "oven_40", "label": "Estufa 40C", "temperature": "40C", "humidity": "Controlada", "protected_from_light": False},
    {"code": "oven_45", "label": "Estufa 45C", "temperature": "45C", "humidity": "Controlada", "protected_from_light": False},
    {"code": "refrigerated_5", "label": "Geladeira 5C", "temperature": "5C", "humidity": "N/A", "protected_from_light": False},
    {"code": "freezer_minus5", "label": "Freezer -5C", "temperature": "-5C", "humidity": "N/A", "protected_from_light": False},
    {"code": "light_exposure", "label": "Exposicao a luz", "temperature": "25C", "humidity": "60% UR", "protected_from_light": False},
    {"code": "dark_storage", "label": "Abrigo de luz", "temperature": "25C", "humidity": "60% UR", "protected_from_light": True},
    {"code": "freeze_thaw", "label": "Ciclo Freeze/Thaw", "temperature": "-5C <-> 40C", "humidity": "Ciclico", "protected_from_light": False},
]

STABILITY_PARAMETERS = [
    {"code": "appearance", "label": "Aspecto"},
    {"code": "color", "label": "Cor"},
    {"code": "odor", "label": "Odor"},
    {"code": "ph", "label": "pH"},
    {"code": "viscosity", "label": "Viscosidade"},
    {"code": "density", "label": "Densidade"},
    {"code": "spreadability", "label": "Espalhabilidade"},
    {"code": "separation", "label": "Separacao de fases"},
    {"code": "precipitation", "label": "Precipitacao"},
    {"code": "microbiology", "label": "Microbiologia"},
    {"code": "package_compatibility", "label": "Compatibilidade com embalagem"},
    {"code": "mass_variation", "label": "Variacao de massa"},
]

STABILITY_CHECKPOINTS = [0, 7, 15, 30, 45, 60, 90]
STABILITY_OPEN_STATUSES = {"ativo", "em_revisao"}


class StabilityReadingCreate(BaseModel):
    condition_code: str
    day_offset: int = Field(ge=0, le=365)
    reading_at: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    photo_urls: List[str] = Field(default_factory=list)


def _stability_condition_map() -> Dict[str, Dict[str, Any]]:
    return {condition["code"]: condition for condition in STABILITY_CONDITIONS}


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_after_days(base_iso: str, days: int) -> str:
    base_dt = _parse_iso_datetime(base_iso) or datetime.now(timezone.utc)
    return (base_dt + timedelta(days=days)).isoformat()


def _build_stability_conditions(started_at: str) -> List[Dict[str, Any]]:
    conditions = []
    for condition in STABILITY_CONDITIONS:
        conditions.append({
            **condition,
            "checkpoints": list(STABILITY_CHECKPOINTS),
            "completed_day_offsets": [],
            "next_due_day_offset": STABILITY_CHECKPOINTS[0],
            "next_due_at": _iso_after_days(started_at, STABILITY_CHECKPOINTS[0]),
            "last_reading_at": None,
            "status": "pending_d0",
        })
    return conditions


def _normalize_stability_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {item["code"] for item in STABILITY_PARAMETERS}
    cleaned: Dict[str, Any] = {}
    for key, value in (parameters or {}).items():
        normalized_key = clean_text(str(key)).lower().replace(" ", "_")
        if normalized_key in allowed and value not in (None, ""):
            cleaned[normalized_key] = value
    return cleaned


def _summarize_stability_conditions(study: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    condition_summaries: List[Dict[str, Any]] = []
    counts = {"pending_d0": 0, "due_soon": 0, "overdue": 0, "completed": 0, "on_track": 0}

    for condition in study.get("conditions", []):
        next_due_at = _parse_iso_datetime(condition.get("next_due_at"))
        completed = list(condition.get("completed_day_offsets") or [])
        checkpoints = list(condition.get("checkpoints") or [])
        if len(completed) >= len(checkpoints):
            status = "completed"
        elif not study.get("d0_completed"):
            status = "pending_d0"
        elif next_due_at and next_due_at < now:
            status = "overdue"
        elif next_due_at and next_due_at <= now + timedelta(days=2):
            status = "due_soon"
        else:
            status = "on_track"

        counts[status] += 1
        condition_summaries.append({
            **condition,
            "status": status,
        })

    if counts["overdue"]:
        overall_status = "critico"
    elif not study.get("d0_completed"):
        overall_status = "pendente_d0"
    elif counts["due_soon"]:
        overall_status = "atencao"
    elif counts["completed"] == len(condition_summaries) and condition_summaries:
        overall_status = "concluido"
    else:
        overall_status = "em_dia"

    next_due_candidates = [
        _parse_iso_datetime(condition.get("next_due_at"))
        for condition in condition_summaries
        if condition.get("status") in {"due_soon", "on_track", "overdue"}
    ]
    next_due_candidates = [item for item in next_due_candidates if item is not None]

    return {
        "conditions": condition_summaries,
        "summary": {
            "overall_status": overall_status,
            "counts": counts,
            "next_due_at": min(next_due_candidates).isoformat() if next_due_candidates else None,
            "completed_conditions": counts["completed"],
            "total_conditions": len(condition_summaries),
        },
    }


async def _recalculate_stability_study(study_id: str) -> Dict[str, Any]:
    study = await db.pd_stability_studies.find_one({"id": study_id}, {"_id": 0})
    if not study:
        raise HTTPException(status_code=404, detail="Estudo de estabilidade nao encontrado")

    recalculated = _summarize_stability_conditions(study)
    status = study.get("status", "ativo")
    if recalculated["summary"]["overall_status"] == "concluido":
        status = "concluido"

    await db.pd_stability_studies.update_one(
        {"id": study_id},
        {
            "$set": {
                "conditions": recalculated["conditions"],
                "summary": recalculated["summary"],
                "status": status,
                "updated_at": now_iso(),
            }
        },
    )
    return await db.pd_stability_studies.find_one({"id": study_id}, {"_id": 0})


async def _ensure_stability_study_for_pd_card(card: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    existing = await db.pd_stability_studies.find_one(
        {"tenant_id": user["tenant_id"], "pd_card_id": card["id"]},
        {"_id": 0},
    )
    if existing:
        return existing

    started_at = now_iso()
    study = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "pd_card_id": card["id"],
        "amostra_id": card.get("amostra_id"),
        "amostra_variacao_id": card.get("amostra_variacao_id"),
        "amostra_numero": card.get("amostra_numero", ""),
        "numero_completo": card.get("numero_completo", ""),
        "produto": card.get("produto", ""),
        "cliente": card.get("cliente", ""),
        "cliente_id": card.get("cliente_id"),
        "projeto_id": card.get("projeto_id"),
        "projeto_nome": card.get("projeto_nome", ""),
        "status": "ativo",
        "d0_completed": False,
        "started_at": started_at,
        "conditions": _build_stability_conditions(started_at),
        "summary": {},
        "created_at": started_at,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "updated_at": started_at,
    }
    summary = _summarize_stability_conditions(study)
    study["conditions"] = summary["conditions"]
    study["summary"] = summary["summary"]
    await db.pd_stability_studies.insert_one(study)
    study.pop("_id", None)

    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="stability_study_auto_created",
        entity_type="stability_study",
        entity_id=study["id"],
        after={
            "pd_card_id": card["id"],
            "numero_completo": card.get("numero_completo", ""),
            "conditions": len(study["conditions"]),
        },
    )
    return study


async def _create_stability_alert_task(
    *,
    study: Dict[str, Any],
    condition: Dict[str, Any],
    alert_kind: str,
) -> Optional[Dict[str, Any]]:
    next_due_day = condition.get("next_due_day_offset")
    if next_due_day in (None, 0):
        return None

    alert_key = f"{alert_kind}:{condition['code']}:{next_due_day}"
    existing = await db.workflow_tasks.find_one(
        {
            "tenant_id": study["tenant_id"],
            "entity_type": "stability_study",
            "entity_id": study["id"],
            "status": {"$in": ["pendente", "em_andamento", "em_atraso"]},
            "metadata.alert_key": alert_key,
        },
        {"_id": 0},
    )
    if existing:
        return None

    due_at = _parse_iso_datetime(condition.get("next_due_at")) or datetime.now(timezone.utc)
    due_in_days = max(0, int((due_at - datetime.now(timezone.utc)).total_seconds() // 86400))
    title = (
        f"Registrar leitura de estabilidade D{next_due_day} - {condition['label']}"
        if alert_kind == "d_minus_2"
        else f"Leitura de estabilidade atrasada D{next_due_day} - {condition['label']}"
    )
    description = (
        f"Amostra {study.get('numero_completo') or study.get('amostra_numero', '')} em {condition['label']}."
    )
    return await create_workflow_task(
        tenant_id=study["tenant_id"],
        entity_type="stability_study",
        entity_id=study["id"],
        title=title,
        description=description,
        category="pd_dev",
        blocking=False,
        due_in_days=due_in_days,
        created_by={"id": "system", "name": "System Scheduler"},
        metadata={
            "trigger": "stability_scheduler",
            "alert_kind": alert_kind,
            "alert_key": alert_key,
            "condition_code": condition["code"],
            "day_offset": next_due_day,
            "pd_card_id": study.get("pd_card_id"),
            "priority": "alta" if alert_kind == "overdue" else "media",
        },
    )


async def check_stability_alerts_for_tenant(tenant_id: str) -> int:
    studies = await db.pd_stability_studies.find(
        {"tenant_id": tenant_id, "status": {"$in": list(STABILITY_OPEN_STATUSES)}},
        {"_id": 0},
    ).to_list(2000)
    created = 0
    now = datetime.now(timezone.utc)

    for study in studies:
        refreshed = _summarize_stability_conditions(study)
        for condition in refreshed["conditions"]:
            next_due_at = _parse_iso_datetime(condition.get("next_due_at"))
            if not next_due_at or condition.get("next_due_day_offset") in (None, 0):
                continue
            if next_due_at <= now:
                task = await _create_stability_alert_task(study=study, condition=condition, alert_kind="overdue")
                created += 1 if task else 0
            elif next_due_at <= now + timedelta(days=2):
                task = await _create_stability_alert_task(study=study, condition=condition, alert_kind="d_minus_2")
                created += 1 if task else 0

    return created


async def run_stability_scheduler():
    await asyncio.sleep(60)
    while True:
        try:
            tenants = await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(500)
            for tenant in tenants:
                await check_stability_alerts_for_tenant(tenant["id"])
        except Exception as exc:  # pragma: no cover
            logger.error(f"Stability scheduler error: {exc}")
        await asyncio.sleep(21600)

# ============ HELPER: Calculate formula item costs ============

def calc_item_costs(percentage: float, price_per_kg: float, cotacao_usd: float):
    """Calculate derived cost fields for a formula item"""
    cost_brl = (percentage / 100.0) * price_per_kg if percentage and price_per_kg else 0.0
    cost_kg_usd = price_per_kg / cotacao_usd if cotacao_usd and cotacao_usd > 0 else 0.0
    return round(cost_brl, 4), round(cost_kg_usd, 4)


def _document_label(doc_type: str) -> str:
    return "Ficha Técnica" if doc_type == "ficha_tecnica" else "EPA"


def _document_version_code(doc_type: str, version_number: int) -> str:
    prefix = "FT" if doc_type == "ficha_tecnica" else "EPA"
    return f"{prefix}-V{version_number:03d}"


async def _get_pd_request_context(req_id: str, tenant_id: str) -> Dict[str, Any]:
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": tenant_id}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    dev = await db.pd_developments.find_one({"pd_request_id": req_id, "tenant_id": tenant_id}, {"_id": 0})
    approval = None
    lab_results = {}
    latest_formula = None
    formula_items = []
    if dev:
        approval = await db.pd_approvals.find_one({"development_id": dev["id"]}, {"_id": 0})
        lab_results = await db.pd_lab_results.find_one({"development_id": dev["id"]}, {"_id": 0}) or {}
        latest_formula = await db.pd_formulas.find_one(
            {"development_id": dev["id"]},
            {"_id": 0},
            sort=[("version", -1)]
        )
        if latest_formula:
            formula_items = await db.pd_formula_items.find({"formula_id": latest_formula["id"]}, {"_id": 0}).to_list(500)

    return {
        "request": pd_req,
        "development": dev,
        "approval": approval,
        "lab_results": lab_results,
        "formula": latest_formula,
        "formula_items": formula_items,
    }


async def _enrich_formula_items(tenant_id: str, formula_items: List[Dict[str, Any]], formula: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    catalog_ids = [item.get("catalog_id") for item in formula_items if item.get("catalog_id")]
    catalog_map: Dict[str, Dict[str, Any]] = {}
    if catalog_ids:
        catalog_docs = await db.pd_catalog.find(
            {"tenant_id": tenant_id, "id": {"$in": catalog_ids}},
            {"_id": 0}
        ).to_list(1000)
        catalog_map = {doc["id"]: doc for doc in catalog_docs if doc.get("id")}

    base_volume = (formula or {}).get("volume", 0) or 0
    volume_unit = (formula or {}).get("volume_unit", "mL")
    volume_factor = base_volume / 1000.0 if volume_unit == "mL" else base_volume

    enriched = []
    for item in formula_items:
        catalog = catalog_map.get(item.get("catalog_id"))
        percentage = item.get("percentage", 0) or 0
        qty = round(volume_factor * (percentage / 100.0), 6) if volume_factor else 0
        enriched.append({
            **item,
            "nome_tecnico": catalog.get("nome") if catalog else item.get("ingredient_name", ""),
            "nome_comercial": catalog.get("nome") if catalog else item.get("ingredient_name", ""),
            "inci": catalog.get("inci", "") if catalog else "",
            "fornecedor": catalog.get("fornecedor", "") if catalog else "",
            "unidade_lote": "kg" if volume_unit == "L" else volume_unit,
            "quantidade_lote_padrao": qty,
        })
    return enriched


def _is_ficha_tecnica_eligible(ctx: Dict[str, Any]) -> bool:
    approval = ctx.get("approval") or {}
    return bool(approval.get("approved_by_client")) and bool(ctx.get("formula"))


def _is_epa_eligible(ctx: Dict[str, Any]) -> bool:
    req = ctx.get("request") or {}
    approval = ctx.get("approval") or {}
    return bool(req.get("kickoff_completed")) and bool(approval.get("approved_by_client")) and bool(ctx.get("formula"))


async def _build_live_document_snapshot(req_id: str, doc_type: str, tenant_id: str) -> Dict[str, Any]:
    ctx = await _get_pd_request_context(req_id, tenant_id)
    req = ctx["request"]
    formula = ctx.get("formula") or {}
    approval = ctx.get("approval") or {}
    lab_results = ctx.get("lab_results") or {}
    enriched_items = await _enrich_formula_items(tenant_id, ctx.get("formula_items") or [], formula)

    if doc_type == "ficha_tecnica":
        if not _is_ficha_tecnica_eligible(ctx):
            raise HTTPException(status_code=400, detail="Ficha Técnica só pode ser gerada após aprovação do cliente e fórmula disponível.")
        return {
            "identificacao": {
                "nome_tecnico": req.get("technical_name") or formula.get("name") or req.get("project_name"),
                "nome_comercial": req.get("commercial_name") or req.get("project_name"),
                "codigo_interno": req.get("internal_code") or req.get("sku") or "",
                "versao_formula": formula.get("version"),
                "data_snapshot": now_iso(),
                "formulador": formula.get("created_by_name", ""),
                "cliente": req.get("client_name") or "Portfólio Kuryos",
            },
            "composicao_completa": enriched_items,
            "modo_preparo": {
                "resumo": formula.get("notes", ""),
                "temperatura_processo": lab_results.get("ph", {}).get("temperatura", ""),
                "equipamento": "",
                "rpm": lab_results.get("viscosidade", {}).get("spindle", ""),
                "alertas_processo": lab_results.get("compatibilidade", {}).get("observacoes", ""),
            },
            "parametros_in_process": {
                "ph_esperado": lab_results.get("ph", {}).get("faixa_aceitavel", ""),
                "ph_medido": lab_results.get("ph", {}).get("valor_medido", ""),
                "viscosidade_esperada": lab_results.get("viscosidade", {}).get("valor_medido", ""),
                "criterios_bulk": lab_results.get("estabilidade", {}).get("aspecto", ""),
                "ativos_termossensiveis": "",
            },
            "rendimento_teorico": {
                "lote_padrao": formula.get("volume", 0),
                "unidade": formula.get("volume_unit", "mL"),
                "fator_perdas_percentual": formula.get("indice_perdas", 0),
            },
            "observacoes_tecnicas": {
                "gerais": formula.get("notes", ""),
                "compatibilidade": lab_results.get("compatibilidade", {}).get("resultado", ""),
                "substituicoes_permitidas": "",
                "substituicoes_nao_permitidas": "",
            },
        }

    if not _is_epa_eligible(ctx):
        raise HTTPException(status_code=400, detail="EPA só pode ser gerado após kickoff concluído, aprovação do cliente e fórmula disponível.")

    return {
        "identificacao_produto": {
            "nome_comercial": req.get("commercial_name") or req.get("project_name"),
            "codigo_interno": req.get("internal_code") or req.get("sku") or "",
            "cliente": req.get("client_name") or "Portfólio Kuryos",
            "sku": req.get("sku", ""),
            "data_snapshot": now_iso(),
        },
        "bom_bulk_formula": {
            "formula_referencia": formula.get("name", ""),
            "versao": formula.get("version"),
            "quantidade_bulk_unidade": formula.get("volume", 0),
            "unidade": formula.get("volume_unit", "mL"),
            "composicao": enriched_items,
        },
        "bom_embalagem_primaria": {
            "descricao": req.get("packaging", ""),
        },
        "bom_embalagem_secundaria": {
            "descricao": "",
        },
        "especificacoes_produto_acabado": {
            "ph": lab_results.get("ph", {}),
            "viscosidade": lab_results.get("viscosidade", {}),
            "densidade": {},
            "aspecto": lab_results.get("sensorial", {}).get("aspecto", ""),
            "cor": lab_results.get("sensorial", {}).get("cor", ""),
            "odor": lab_results.get("sensorial", {}).get("odor", ""),
            "estabilidade": lab_results.get("estabilidade", {}),
        },
        "especificacoes_embalagem": {
            "volume_nominal": formula.get("volume", 0),
            "volume_enchimento": formula.get("volume", 0),
            "torque_fechamento": "",
            "teste_vedacao": "",
        },
        "etapas_producao_resumidas": [
            "Pesagem",
            "Manipulação",
            "Envase",
            "Rotulagem",
            "Finalização",
        ],
        "informacoes_rotulo": {
            "inci": ", ".join([item.get("inci", "") for item in enriched_items if item.get("inci")]),
            "modo_uso": "",
            "advertencias": "",
            "prazo_validade": "",
            "lote": "",
            "armazenamento": "",
        },
        "referencia_anvisa": {
            "numero": "",
            "validade": "",
            "responsavel_tecnico": "",
        },
        "criterios_liberacao_lote": {
            "cq_checklist": [
                "Conferir especificações físico-químicas",
                "Conferir aspecto visual e odor",
                "Conferir embalagem, lote e rotulagem",
            ]
        },
    }


async def _create_document_approval_tasks(doc_version: Dict[str, Any], user: dict, reason: str, changed_fields: List[str], source_changes: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    task_ids: List[str] = []
    base_metadata = {
        "module_origin": "documentos_internos",
        "document_type": doc_version["doc_type"],
        "document_version_id": doc_version["id"],
        "changed_fields": changed_fields,
        "source_changes": source_changes or [],
        "generation_reason": reason,
        "task_type": "approval",
        "priority": "alta",
    }

    if doc_version["doc_type"] == "ficha_tecnica":
        main_task = await create_workflow_task(
            tenant_id=doc_version["tenant_id"],
            entity_type="pd_document",
            entity_id=doc_version["id"],
            title=f"Aprovar {_document_label(doc_version['doc_type'])} {doc_version['version_code']}",
            description="Registrar aprovação formal da nova versão da Ficha Técnica.",
            category="documentacao",
            blocking=True,
            due_in_days=2,
            created_by=user,
            metadata={**base_metadata, "approver_role": "lider_pd"},
        )
        task_ids.append(main_task["id"])
        needs_qa = any(field in {"modo_preparo", "ordem_adicao", "parametros_in_process"} for field in changed_fields)
        if needs_qa:
            qa_task = await create_workflow_task(
                tenant_id=doc_version["tenant_id"],
                entity_type="pd_document",
                entity_id=doc_version["id"],
                title=f"Revisão CQ da Ficha Técnica {doc_version['version_code']}",
                description="Alteração de processo exige revisão adicional do CQ.",
                category="qa",
                blocking=True,
                due_in_days=2,
                created_by=user,
                metadata={**base_metadata, "approver_role": "cq"},
            )
            task_ids.append(qa_task["id"])
        return task_ids

    for title, category, approver_role in [
        (f"Aprovar EPA {doc_version['version_code']} - CQ", "qa", "cq"),
        (f"Aprovar EPA {doc_version['version_code']} - Líder P&D", "pd_dev", "lider_pd"),
        (f"Aprovar EPA {doc_version['version_code']} - Engenharia de Produto", "engenharia_produto", "engenharia_produto"),
    ]:
        task = await create_workflow_task(
            tenant_id=doc_version["tenant_id"],
            entity_type="pd_document",
            entity_id=doc_version["id"],
            title=title,
            description="Registrar aprovação formal da nova versão do EPA.",
            category=category,
            blocking=True,
            due_in_days=2,
            created_by=user,
            metadata={**base_metadata, "approver_role": approver_role},
        )
        task_ids.append(task["id"])
    return task_ids


async def _generate_live_document_version(
    req_id: str,
    doc_type: str,
    user: dict,
    reason: str = "",
    changed_fields: Optional[List[str]] = None,
    trigger: str = "manual",
    source_changes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if doc_type not in LIVE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de documento vivo inválido")

    changed_fields = changed_fields or []
    snapshot = await _build_live_document_snapshot(req_id, doc_type, user["tenant_id"])
    current_versions = await db.pd_document_versions.find(
        {"tenant_id": user["tenant_id"], "pd_request_id": req_id, "doc_type": doc_type},
        {"_id": 0, "version_number": 1}
    ).sort("version_number", -1).to_list(1)
    next_version = (current_versions[0]["version_number"] + 1) if current_versions else 1

    doc_version = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "pd_request_id": req_id,
        "doc_type": doc_type,
        "version_number": next_version,
        "version_code": _document_version_code(doc_type, next_version),
        "status": "em_revisao",
        "active_for_operation": False,
        "snapshot": snapshot,
        "reason": reason or f"Nova versão de {_document_label(doc_type)}",
        "changed_fields": changed_fields,
        "source_trigger": trigger,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "approved_at": None,
        "approval_task_ids": [],
    }
    await db.pd_document_versions.insert_one(doc_version)
    approval_task_ids = await _create_document_approval_tasks(doc_version, user, reason, changed_fields, source_changes)
    await db.pd_document_versions.update_one(
        {"id": doc_version["id"]},
        {"$set": {"approval_task_ids": approval_task_ids}}
    )
    doc_version["approval_task_ids"] = approval_task_ids
    return doc_version


async def _try_auto_generate_document(
    req_id: str,
    doc_type: str,
    user: dict,
    trigger: str,
    changed_fields: Optional[List[str]] = None,
    source_changes: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    ctx = await _get_pd_request_context(req_id, user["tenant_id"])
    eligible = _is_ficha_tecnica_eligible(ctx) if doc_type == "ficha_tecnica" else _is_epa_eligible(ctx)
    if not eligible:
        return None
    return await _generate_live_document_version(
        req_id=req_id,
        doc_type=doc_type,
        user=user,
        reason=f"Atualização automática por {trigger}",
        changed_fields=changed_fields or [],
        trigger=trigger,
        source_changes=source_changes or [],
    )


def _user_can_review_live_documents(user: dict) -> bool:
    return can_view_live_document_revisions(user)


def _build_source_changes(
    before: Optional[Dict[str, Any]],
    after_updates: Dict[str, Any],
    labels: Optional[Dict[str, str]] = None,
    *,
    ignored_fields: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    before = before or {}
    labels = labels or {}
    ignored = set(ignored_fields or [])
    changes: List[Dict[str, Any]] = []
    for field, after_value in after_updates.items():
        if field in ignored:
            continue
        before_value = before.get(field)
        if before_value == after_value:
            continue
        changes.append({
            "field": field,
            "label": labels.get(field, field),
            "before": before_value,
            "after": after_value,
        })
    return changes


async def _auto_generate_documents_for_request(
    req_id: str,
    user: dict,
    trigger: str,
    *,
    ficha_changed_fields: Optional[List[str]] = None,
    epa_changed_fields: Optional[List[str]] = None,
    source_changes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    generated: List[Dict[str, Any]] = []
    if ficha_changed_fields:
        doc = await _try_auto_generate_document(
            req_id=req_id,
            doc_type="ficha_tecnica",
            user=user,
            trigger=trigger,
            changed_fields=ficha_changed_fields,
            source_changes=source_changes,
        )
        if doc:
            generated.append(doc)
    if epa_changed_fields:
        doc = await _try_auto_generate_document(
            req_id=req_id,
            doc_type="epa",
            user=user,
            trigger=trigger,
            changed_fields=epa_changed_fields,
            source_changes=source_changes,
        )
        if doc:
            generated.append(doc)
    return generated


async def _auto_generate_documents_for_development(
    dev_id: str,
    user: dict,
    trigger: str,
    *,
    ficha_changed_fields: Optional[List[str]] = None,
    epa_changed_fields: Optional[List[str]] = None,
    source_changes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]}, {"_id": 0, "pd_request_id": 1})
    if not dev or not dev.get("pd_request_id"):
        return []
    return await _auto_generate_documents_for_request(
        dev["pd_request_id"],
        user,
        trigger,
        ficha_changed_fields=ficha_changed_fields,
        epa_changed_fields=epa_changed_fields,
        source_changes=source_changes,
    )


async def _request_ids_from_formula_ids(formula_ids: List[str], tenant_id: str) -> List[str]:
    if not formula_ids:
        return []
    formulas = await db.pd_formulas.find(
        {"id": {"$in": formula_ids}},
        {"_id": 0, "development_id": 1}
    ).to_list(1000)
    dev_ids = [formula.get("development_id") for formula in formulas if formula.get("development_id")]
    if not dev_ids:
        return []
    devs = await db.pd_developments.find(
        {"tenant_id": tenant_id, "id": {"$in": dev_ids}},
        {"_id": 0, "pd_request_id": 1}
    ).to_list(1000)
    return list({dev.get("pd_request_id") for dev in devs if dev.get("pd_request_id")})


async def _auto_generate_documents_for_catalog_items(
    catalog_ids: List[str],
    user: dict,
    trigger: str,
    *,
    ficha_changed_fields: Optional[List[str]] = None,
    epa_changed_fields: Optional[List[str]] = None,
    source_changes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if not catalog_ids:
        return []
    formula_items = await db.pd_formula_items.find(
        {"catalog_id": {"$in": catalog_ids}},
        {"_id": 0, "formula_id": 1}
    ).to_list(5000)
    formula_ids = list({item.get("formula_id") for item in formula_items if item.get("formula_id")})
    request_ids = await _request_ids_from_formula_ids(formula_ids, user["tenant_id"])
    generated: List[Dict[str, Any]] = []
    for req_id in request_ids:
        generated.extend(await _auto_generate_documents_for_request(
            req_id,
            user,
            trigger,
            ficha_changed_fields=ficha_changed_fields,
            epa_changed_fields=epa_changed_fields,
            source_changes=source_changes,
        ))
    return generated


async def _get_live_document_version(version_id: str, user: dict) -> Dict[str, Any]:
    query = {"id": version_id, "tenant_id": user["tenant_id"]}
    if not _user_can_review_live_documents(user):
        query["status"] = "aprovado"
        query["active_for_operation"] = True
    doc_version = await db.pd_document_versions.find_one(query, {"_id": 0})
    if not doc_version:
        raise HTTPException(status_code=404, detail="Versao de documento nao encontrada")
    approval_tasks = await db.workflow_tasks.find(
        {"tenant_id": user["tenant_id"], "entity_type": "pd_document", "entity_id": version_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(50)
    doc_version["approval_tasks"] = approval_tasks
    return doc_version

# ============ CRM CLIENT SEARCH ============

@pd_router.get("/clients/search")
async def search_clients(request: Request, q: str = ""):
    user = await get_current_user(request)
    query = {"tenant_id": user["tenant_id"]}
    if q:
        query["nome_cliente"] = {"$regex": q, "$options": "i"}
    cards = await db.cards.find(query, {"_id": 0}).to_list(20)
    return cards

# ============ PD REQUESTS CRUD ============

@pd_router.post("/requests")
async def create_pd_request(data: PDRequestCreate, request: Request):
    user = await get_current_user(request)
    req_id = new_id()
    
    pd_request = {
        "id": req_id,
        "tenant_id": user["tenant_id"],
        "client_card_id": data.client_card_id,
        "client_name": data.client_name or "",
        "project_name": data.project_name,
        "technical_name": data.technical_name or data.project_name,
        "commercial_name": data.commercial_name or data.project_name,
        "internal_code": data.internal_code or "",
        "request_type": data.request_type,
        "category": data.category or "",
        "description": data.description or "",
        "references": data.references or "",
        "restrictions": data.restrictions or "",
        "volume": data.volume or "",
        "packaging": data.packaging or "",
        "priority": data.priority,
        "deadline": data.deadline,
        "status": "OPEN",
        "is_internal_research": data.is_internal_research or False,
        "kickoff_completed": data.kickoff_completed or False,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    
    await db.pd_requests.insert_one(pd_request)
    pd_request.pop("_id", None)
    
    # Log initial status
    await db.pd_request_status_history.insert_one({
        "id": new_id(),
        "pd_request_id": req_id,
        "from_status": None,
        "to_status": "OPEN",
        "changed_by": user["id"],
        "changed_by_name": user["name"],
        "comment": "Solicitação criada",
        "created_at": now_iso(),
    })
    
    return pd_request

@pd_router.get("/requests")
async def list_pd_requests(request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    query = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    
    requests_list = await db.pd_requests.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return requests_list

@pd_router.get("/requests/{req_id}")
async def get_pd_request(req_id: str, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    return pd_req

@pd_router.put("/requests/{req_id}")
async def update_pd_request(req_id: str, data: PDRequestUpdate, request: Request):
    user = await get_current_user(request)
    existing = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Solicitacao nao encontrada")
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    source_changes = _build_source_changes(
        existing,
        update_fields,
        {
            "technical_name": "Nome tecnico",
            "commercial_name": "Nome comercial",
            "internal_code": "Codigo interno",
            "client_name": "Cliente",
            "packaging": "Embalagem",
            "kickoff_completed": "Kickoff concluido",
        },
    )

    update_fields["updated_at"] = now_iso()
    result = await db.pd_requests.update_one(
        {"id": req_id, "tenant_id": user["tenant_id"]},
        {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    
    pd_req = await db.pd_requests.find_one({"id": req_id}, {"_id": 0})
    ficha_changed_fields: List[str] = []
    epa_changed_fields: List[str] = []
    if any(field in update_fields for field in ("technical_name", "commercial_name", "internal_code", "client_name")):
        ficha_changed_fields.append("identificacao")
    if any(field in update_fields for field in ("commercial_name", "internal_code", "client_name")):
        epa_changed_fields.append("identificacao_produto")
    if "packaging" in update_fields:
        epa_changed_fields.append("bom_embalagem_primaria")
    if update_fields.get("kickoff_completed") is True:
        epa_changed_fields.append("kickoff")
    if ficha_changed_fields or epa_changed_fields:
        await _auto_generate_documents_for_request(
            req_id,
            user,
            "atualizacao_request",
            ficha_changed_fields=ficha_changed_fields,
            epa_changed_fields=epa_changed_fields,
            source_changes=source_changes,
        )
    return pd_req

@pd_router.delete("/requests/{req_id}")
async def delete_pd_request(req_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.pd_requests.delete_one({"id": req_id, "tenant_id": user["tenant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    # Clean up related data
    dev = await db.pd_developments.find_one({"pd_request_id": req_id}, {"_id": 0})
    if dev:
        dev_id = dev["id"]
        formula_ids = [f["id"] for f in await db.pd_formulas.find({"development_id": dev_id}, {"id": 1, "_id": 0}).to_list(100)]
        if formula_ids:
            await db.pd_formula_items.delete_many({"formula_id": {"$in": formula_ids}})
        await db.pd_formulas.delete_many({"development_id": dev_id})
        await db.pd_tests.delete_many({"development_id": dev_id})
        await db.pd_samples.delete_many({"development_id": dev_id})
        await db.pd_approvals.delete_many({"development_id": dev_id})
        await db.pd_costs.delete_many({"development_id": dev_id})
        await db.pd_documents.delete_many({"development_id": dev_id})
        await db.pd_developments.delete_one({"id": dev_id})
    await db.pd_request_status_history.delete_many({"pd_request_id": req_id})
    return {"message": "Solicitação removida"}

# ============ STATUS TRANSITIONS ============

@pd_router.put("/requests/{req_id}/status")
async def transition_status(req_id: str, data: StatusTransition, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    
    current = pd_req["status"]
    new_status = data.new_status
    
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido: {new_status}")
    
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Transição não permitida: {current} → {new_status}. Permitidas: {allowed}")

    # RN-PD-02: Block IN_TESTS if formula without ingredients
    if new_status == "IN_TESTS":
        dev_check = await db.pd_developments.find_one({"pd_request_id": req_id}, {"_id": 0})
        if not dev_check:
            raise HTTPException(status_code=400, detail="Inicie o desenvolvimento antes de avançar para Em Testes.")
        formula_check = await db.pd_formulas.find_one(
            {"development_id": dev_check["id"]}, {"_id": 0}, sort=[("version", -1)]
        )
        if not formula_check:
            raise HTTPException(status_code=400, detail="Registre a fórmula antes de avançar para Em Testes (RN-PD-02).")
        items_check = await db.pd_formula_items.find({"formula_id": formula_check["id"]}, {"_id": 0}).to_list(200)
        if not items_check:
            raise HTTPException(status_code=400, detail="Adicione ingredientes à fórmula antes de avançar para Em Testes (RN-PD-02).")
        total_pct = sum(it.get("percentage", 0) for it in items_check)
        if abs(total_pct - 100.0) > 0.5:
            raise HTTPException(
                status_code=400,
                detail=f"O total da fórmula deve ser 100% (atual: {total_pct:.2f}%). Ajuste os ingredientes antes de avançar (RN-PD-02)."
            )

    # Check blocking workflow tasks
    if new_status not in ("IN_PROGRESS", "REJECTED"):
        blocking = await get_blocking_tasks(
            tenant_id=user["tenant_id"],
            entity_type="pd_card",
            entity_id=req_id,
            target_stage=new_status,
        )
        if blocking:
            titles = " | ".join(t.get("title", "") for t in blocking[:3])
            raise HTTPException(status_code=409, detail=f"Existem tarefas bloqueantes pendentes: {titles}")

    # Check approval requirements for APPROVED status
    if new_status == "APPROVED":
        dev = await db.pd_developments.find_one({"pd_request_id": req_id}, {"_id": 0})
        if dev:
            tests = await db.pd_tests.find({"development_id": dev["id"]}, {"_id": 0}).to_list(100)
            failed_tests = [t for t in tests if t["status"] == "FAILED"]
            if failed_tests:
                raise HTTPException(status_code=400, detail="Existem testes com falha. Corrija antes de aprovar.")
            approval = await db.pd_approvals.find_one({"development_id": dev["id"]}, {"_id": 0})
            if not approval:
                raise HTTPException(status_code=400, detail="Registre uma aprovação antes de mover para APROVADO.")
    
    await db.pd_requests.update_one(
        {"id": req_id},
        {"$set": {"status": new_status, "updated_at": now_iso()}}
    )
    
    await db.pd_request_status_history.insert_one({
        "id": new_id(),
        "pd_request_id": req_id,
        "from_status": current,
        "to_status": new_status,
        "changed_by": user["id"],
        "changed_by_name": user["name"],
        "comment": data.comment or f"Status alterado de {STATUS_LABELS.get(current, current)} para {STATUS_LABELS.get(new_status, new_status)}",
        "created_at": now_iso(),
    })
    
    # Auto-create development when moving to IN_PROGRESS
    if new_status == "IN_PROGRESS":
        existing_dev = await db.pd_developments.find_one({"pd_request_id": req_id})
        if not existing_dev:
            dev_id = new_id()
            await db.pd_developments.insert_one({
                "id": dev_id,
                "pd_request_id": req_id,
                "tenant_id": user["tenant_id"],
                "assigned_to": user["id"],
                "assigned_to_name": user["name"],
                "lab_responsible": None,
                "current_version": 0,
                "status": "active",
                "started_at": now_iso(),
                "completed_at": None,
            })
    
    if new_status == "COMPLETED":
        await db.pd_developments.update_one(
            {"pd_request_id": req_id},
            {"$set": {"status": "completed", "completed_at": now_iso()}}
        )
    
    updated = await db.pd_requests.find_one({"id": req_id}, {"_id": 0})
    return updated

@pd_router.get("/requests/{req_id}/history")
async def get_status_history(req_id: str, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    
    history = await db.pd_request_status_history.find(
        {"pd_request_id": req_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return history

# ============ DEVELOPMENTS ============

@pd_router.get("/requests/{req_id}/development")
async def get_development(req_id: str, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    
    dev = await db.pd_developments.find_one({"pd_request_id": req_id}, {"_id": 0})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento ainda não iniciado")
    return dev

# ============ FORMULAS (with Manipulação structure) ============

@pd_router.post("/developments/{dev_id}/formulas")
async def create_formula(dev_id: str, data: FormulaCreate, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    last_formula = await db.pd_formulas.find(
        {"development_id": dev_id}
    ).sort("version", -1).to_list(1)
    next_version = (last_formula[0]["version"] + 1) if last_formula else 1
    
    formula_id = new_id()
    formula = {
        "id": formula_id,
        "development_id": dev_id,
        "version": next_version,
        "name": data.name,
        "notes": data.notes or "",
        "volume": data.volume or 0,
        "volume_unit": data.volume_unit or "mL",
        "indice_perdas": data.indice_perdas or 0,
        "cotacao_usd": data.cotacao_usd or 6.00,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
    }
    await db.pd_formulas.insert_one(formula)
    formula.pop("_id", None)
    
    await db.pd_developments.update_one(
        {"id": dev_id},
        {"$set": {"current_version": next_version}}
    )

    await _auto_generate_documents_for_request(
        dev["pd_request_id"],
        user,
        "nova_formula",
        ficha_changed_fields=["identificacao", "composicao_completa", "modo_preparo", "rendimento_teorico"],
        epa_changed_fields=["bom_bulk_formula", "especificacoes_embalagem"],
        source_changes=[{
            "field": "formula_version",
            "label": "Versao da formula",
            "before": next_version - 1 if next_version > 1 else None,
            "after": next_version,
        }],
    )

    return formula

@pd_router.put("/formulas/{formula_id}")
async def update_formula(formula_id: str, data: FormulaUpdate, request: Request):
    user = await get_current_user(request)
    existing = await db.pd_formulas.find_one({"id": formula_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Formula nao encontrada")
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    source_changes = _build_source_changes(
        existing,
        update_fields,
        {
            "name": "Nome da formula",
            "notes": "Modo de preparo / observacoes",
            "volume": "Volume do lote padrao",
            "volume_unit": "Unidade do lote padrao",
            "indice_perdas": "Fator de perdas",
            "cotacao_usd": "Cotacao USD",
        },
    )

    result = await db.pd_formulas.update_one({"id": formula_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fórmula não encontrada")
    
    # If cotacao_usd changed, recalculate all items
    if "cotacao_usd" in update_fields:
        formula = await db.pd_formulas.find_one({"id": formula_id}, {"_id": 0})
        cotacao = formula.get("cotacao_usd", 6.00)
        items = await db.pd_formula_items.find({"formula_id": formula_id}, {"_id": 0}).to_list(200)
        for item in items:
            cost_brl, cost_kg_usd = calc_item_costs(
                item.get("percentage", 0),
                item.get("price_per_kg", 0),
                cotacao
            )
            await db.pd_formula_items.update_one(
                {"id": item["id"]},
                {"$set": {"cost_brl": cost_brl, "cost_kg_usd": cost_kg_usd}}
            )
    
    formula = await db.pd_formulas.find_one({"id": formula_id}, {"_id": 0})
    ficha_changed_fields: List[str] = []
    epa_changed_fields: List[str] = []
    if "name" in update_fields:
        ficha_changed_fields.append("identificacao")
        epa_changed_fields.append("bom_bulk_formula")
    if "notes" in update_fields:
        ficha_changed_fields.extend(["modo_preparo", "observacoes_tecnicas"])
    if any(field in update_fields for field in ("volume", "volume_unit", "indice_perdas")):
        ficha_changed_fields.append("rendimento_teorico")
        epa_changed_fields.extend(["bom_bulk_formula", "especificacoes_embalagem"])
    if ficha_changed_fields or epa_changed_fields:
        await _auto_generate_documents_for_development(
            formula["development_id"],
            user,
            "atualizacao_formula",
            ficha_changed_fields=list(dict.fromkeys(ficha_changed_fields)),
            epa_changed_fields=list(dict.fromkeys(epa_changed_fields)),
            source_changes=source_changes,
        )
    return formula

@pd_router.get("/developments/{dev_id}/formulas")
async def list_formulas(dev_id: str, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    formulas = await db.pd_formulas.find({"development_id": dev_id}, {"_id": 0}).sort("version", -1).to_list(100)
    for f in formulas:
        items = await db.pd_formula_items.find({"formula_id": f["id"]}, {"_id": 0}).to_list(200)
        # Calculate cost_percentage for each item based on total
        total_cost = sum(it.get("cost_brl", 0) for it in items)
        for it in items:
            it["cost_percentage"] = round((it.get("cost_brl", 0) / total_cost * 100), 2) if total_cost > 0 else 0
        f["items"] = items
        # Calculate custo_unitario
        volume = f.get("volume", 0) or 0
        volume_unit = f.get("volume_unit", "mL")
        volume_kg = volume / 1000.0 if volume_unit == "mL" else volume  # mL to kg (density~1)
        f["custo_unitario"] = round(total_cost * volume_kg, 2) if volume_kg > 0 else round(total_cost, 2)
        f["total_cost_per_kg"] = round(total_cost, 4)
    return formulas


@pd_router.get("/formulas/bank")
async def formula_bank(
    request: Request,
    q: Optional[str] = None,
    origem: Optional[str] = None,
    somente_registradas: bool = False,
):
    """Banco global de formulas do P&D com contexto de projeto e aprovacoes.

    Visibilidade RBAC:
      - Perfis P&D/CQ/Eng/Doc Reviewers: composicao completa.
      - Comercial (vendedor/sales_ops/sucesso_cliente): apenas metadados (sem composicao nem custos).
    """
    user = await get_current_user(request)
    require_roles(user, PD_READ | {"vendedor", "sales_ops", "sucesso_cliente"})
    show_full = can_view_formula_composition(user)
    tenant_id = user["tenant_id"]

    developments = await db.pd_developments.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "pd_request_id": 1}
    ).to_list(5000)
    if not developments:
        return []

    dev_ids = [d["id"] for d in developments if d.get("id")]
    req_ids = [d["pd_request_id"] for d in developments if d.get("pd_request_id")]
    dev_map = {d["id"]: d for d in developments if d.get("id")}

    requests_docs = await db.pd_requests.find(
        {"tenant_id": tenant_id, "id": {"$in": req_ids}},
        {
            "_id": 0,
            "id": 1,
            "project_name": 1,
            "client_name": 1,
            "status": 1,
            "is_internal_research": 1,
            "created_at": 1,
            "updated_at": 1,
        }
    ).to_list(5000)
    requests_map = {r["id"]: r for r in requests_docs if r.get("id")}

    approvals = await db.pd_approvals.find(
        {"development_id": {"$in": dev_ids}},
        {
            "_id": 0,
            "development_id": 1,
            "approved_by_client": 1,
            "approved_by_internal": 1,
            "notes": 1,
        }
    ).to_list(5000)
    approvals_map = {a["development_id"]: a for a in approvals if a.get("development_id")}

    formulas = await db.pd_formulas.find(
        {"development_id": {"$in": dev_ids}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(10000)
    if not formulas:
        return []

    formula_ids = [f["id"] for f in formulas if f.get("id")]
    items = await db.pd_formula_items.find(
        {"formula_id": {"$in": formula_ids}},
        {"_id": 0}
    ).to_list(20000)
    items_by_formula: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        items_by_formula.setdefault(item.get("formula_id"), []).append(item)

    latest_by_dev: Dict[str, Dict[str, Any]] = {}
    for formula in formulas:
        dev_id = formula.get("development_id")
        existing = latest_by_dev.get(dev_id)
        if not existing or formula.get("version", 0) > existing.get("version", 0):
            latest_by_dev[dev_id] = formula

    result = []
    for formula in formulas:
        dev_id = formula.get("development_id")
        req = requests_map.get(dev_map.get(dev_id, {}).get("pd_request_id"))
        if not req:
            continue

        formula_items = items_by_formula.get(formula.get("id"), [])
        approval = approvals_map.get(dev_id, {})
        approved_by_client = bool(approval.get("approved_by_client"))
        approved_by_internal = bool(approval.get("approved_by_internal"))
        is_registered = approved_by_client and approved_by_internal
        origin_label = req.get("client_name") or "Portfólio Kuryos"
        origin_type = "portfolio" if req.get("is_internal_research") or not req.get("client_name") else "cliente"

        if origem and origin_type != origem:
            continue
        if somente_registradas and not is_registered:
            continue

        total_cost_per_kg = round(sum((it.get("cost_brl") or 0) for it in formula_items), 4)
        total_percentage = round(sum((it.get("percentage") or 0) for it in formula_items), 4)

        row = {
            "id": formula.get("id"),
            "development_id": dev_id,
            "pd_request_id": req.get("id"),
            "name": formula.get("name"),
            "version": formula.get("version", 1),
            "is_latest_version": formula.get("id") == latest_by_dev.get(dev_id, {}).get("id"),
            "notes": formula.get("notes", "") if show_full else "",
            "created_at": formula.get("created_at"),
            "created_by_name": formula.get("created_by_name", ""),
            "project_name": req.get("project_name", ""),
            "client_name": req.get("client_name", ""),
            "origin_label": origin_label,
            "origin_type": origin_type,
            "request_status": req.get("status"),
            "approved_by_client": approved_by_client,
            "approved_by_internal": approved_by_internal,
            "is_registered": is_registered,
            "item_count": len(formula_items),
            "total_percentage": total_percentage if show_full else None,
            "total_cost_per_kg": total_cost_per_kg if show_full else None,
            "volume": formula.get("volume", 0),
            "volume_unit": formula.get("volume_unit", "mL"),
            "items": (sorted(
                formula_items,
                key=lambda item: (
                    str(item.get("phase", "")),
                    -(item.get("percentage") or 0),
                    str(item.get("ingredient_name", "")),
                )
            ) if show_full else []),
            "restricted_view": not show_full,
        }

        if q:
            search_blob = " ".join([
                str(row.get("name", "")),
                str(row.get("project_name", "")),
                str(row.get("client_name", "")),
                str(row.get("origin_label", "")),
                str(row.get("created_by_name", "")),
                " ".join(str(it.get("ingredient_name", "")) for it in (row.get("items") or [])),
            ]).lower()
            if q.lower() not in search_blob:
                continue

        result.append(row)

    result.sort(
        key=lambda row: (
            row.get("created_at") or "",
            row.get("version", 0),
            row.get("name") or "",
        ),
        reverse=True,
    )
    return result

@pd_router.post("/formulas/{formula_id}/items")
async def add_formula_item(formula_id: str, data: FormulaItemCreate, request: Request):
    user = await get_current_user(request)
    formula = await db.pd_formulas.find_one({"id": formula_id}, {"_id": 0})
    if not formula:
        raise HTTPException(status_code=404, detail="Fórmula não encontrada")
    
    cotacao = formula.get("cotacao_usd", 6.00) or 6.00
    cost_brl, cost_kg_usd = calc_item_costs(data.percentage, data.price_per_kg, cotacao)
    
    item_id = new_id()
    item = {
        "id": item_id,
        "formula_id": formula_id,
        "ingredient_name": data.ingredient_name,
        "percentage": data.percentage,
        "price_per_kg": data.price_per_kg,
        "cost_brl": cost_brl,
        "cost_kg_usd": cost_kg_usd,
        "fornecedor": data.fornecedor or "",
        "phase": data.phase or "",
        "function": data.function or "",
        "catalog_id": data.catalog_id or None,
    }
    await db.pd_formula_items.insert_one(item)
    item.pop("_id", None)
    await _auto_generate_documents_for_development(
        formula["development_id"],
        user,
        "novo_item_formula",
        ficha_changed_fields=["composicao_completa"],
        epa_changed_fields=["bom_bulk_formula"],
        source_changes=[{
            "field": "formula_item",
            "label": "Composicao da formula",
            "before": None,
            "after": {
                "ingredient_name": item["ingredient_name"],
                "percentage": item["percentage"],
                "catalog_id": item.get("catalog_id"),
            },
        }],
    )
    return item

@pd_router.put("/formula-items/{item_id}")
async def update_formula_item(item_id: str, data: FormulaItemUpdate, request: Request):
    user = await get_current_user(request)
    existing = await db.pd_formula_items.find_one({"id": item_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    
    # Recalculate costs if percentage or price changed
    pct = update_fields.get("percentage", existing.get("percentage", 0))
    ppk = update_fields.get("price_per_kg", existing.get("price_per_kg", 0))
    
    formula = await db.pd_formulas.find_one({"id": existing["formula_id"]}, {"_id": 0})
    cotacao = formula.get("cotacao_usd", 6.00) if formula else 6.00
    
    cost_brl, cost_kg_usd = calc_item_costs(pct, ppk, cotacao)
    update_fields["cost_brl"] = cost_brl
    update_fields["cost_kg_usd"] = cost_kg_usd

    source_changes = _build_source_changes(
        existing,
        update_fields,
        {
            "ingredient_name": "Ingrediente",
            "percentage": "Concentracao",
            "phase": "Fase",
            "function": "Funcao",
            "catalog_id": "Item do catalogo",
        },
        ignored_fields=["cost_brl", "cost_kg_usd"],
    )
    await db.pd_formula_items.update_one({"id": item_id}, {"$set": update_fields})
    item = await db.pd_formula_items.find_one({"id": item_id}, {"_id": 0})
    if any(field in update_fields for field in ("ingredient_name", "percentage", "phase", "function", "catalog_id")):
        await _auto_generate_documents_for_development(
            formula["development_id"],
            user,
            "atualizacao_item_formula",
            ficha_changed_fields=["composicao_completa"],
            epa_changed_fields=["bom_bulk_formula"],
            source_changes=source_changes,
        )
    return item

@pd_router.delete("/formula-items/{item_id}")
async def delete_formula_item(item_id: str, request: Request):
    user = await get_current_user(request)
    existing = await db.pd_formula_items.find_one({"id": item_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Item nao encontrado")
    result = await db.pd_formula_items.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    formula = await db.pd_formulas.find_one({"id": existing["formula_id"]}, {"_id": 0})
    if formula:
        await _auto_generate_documents_for_development(
            formula["development_id"],
            user,
            "remocao_item_formula",
            ficha_changed_fields=["composicao_completa"],
            epa_changed_fields=["bom_bulk_formula"],
            source_changes=[{
                "field": "formula_item",
                "label": "Composicao da formula",
                "before": {
                    "ingredient_name": existing.get("ingredient_name"),
                    "percentage": existing.get("percentage"),
                    "catalog_id": existing.get("catalog_id"),
                },
                "after": None,
            }],
        )
    return {"message": "Ingrediente removido"}

@pd_router.get("/formulas/{formula_id}/items")
async def list_formula_items(formula_id: str, request: Request):
    user = await get_current_user(request)
    items = await db.pd_formula_items.find({"formula_id": formula_id}, {"_id": 0}).to_list(200)
    return items

# ============ FORMULA COST REPORT ============

@pd_router.get("/formulas/{formula_id}/cost-report")
async def formula_cost_report(formula_id: str, request: Request):
    """Returns full cost breakdown for a formula - Relatório de Custo Acabado"""
    user = await get_current_user(request)
    formula = await db.pd_formulas.find_one({"id": formula_id}, {"_id": 0})
    if not formula:
        raise HTTPException(status_code=404, detail="Fórmula não encontrada")
    
    items = await db.pd_formula_items.find({"formula_id": formula_id}, {"_id": 0}).to_list(200)
    
    total_percentage = sum(it.get("percentage", 0) for it in items)
    total_cost_per_kg = sum(it.get("cost_brl", 0) for it in items)
    total_price_sum = sum(it.get("price_per_kg", 0) for it in items)
    cotacao = formula.get("cotacao_usd", 6.00) or 6.00
    
    volume = formula.get("volume", 0) or 0
    volume_unit = formula.get("volume_unit", "mL")
    volume_kg = volume / 1000.0 if volume_unit == "mL" else volume
    indice_perdas = formula.get("indice_perdas", 0) or 0
    
    custo_unitario = total_cost_per_kg * volume_kg if volume_kg > 0 else total_cost_per_kg
    custo_com_perdas = custo_unitario * (1 + indice_perdas / 100.0) if indice_perdas > 0 else custo_unitario
    
    # Calculate cost_percentage for each item
    for it in items:
        it["cost_percentage"] = round((it.get("cost_brl", 0) / total_cost_per_kg * 100), 2) if total_cost_per_kg > 0 else 0
    
    return {
        "formula": formula,
        "items": items,
        "totals": {
            "total_percentage": round(total_percentage, 3),
            "total_price_sum": round(total_price_sum, 2),
            "total_cost_per_kg": round(total_cost_per_kg, 4),
            "custo_unitario": round(custo_unitario, 2),
            "custo_com_perdas": round(custo_com_perdas, 2),
            "cotacao_usd": cotacao,
            "volume": volume,
            "volume_unit": volume_unit,
            "indice_perdas": indice_perdas,
        }
    }

# ============ TESTS (Structured) ============

@pd_router.post("/developments/{dev_id}/tests")
async def create_test(dev_id: str, data: TestCreate, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    test_id = new_id()
    test = {
        "id": test_id,
        "development_id": dev_id,
        "test_type": data.test_type,
        "dados": data.dados or {},
        "status": data.status,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.pd_tests.insert_one(test)
    test.pop("_id", None)
    return test

@pd_router.get("/developments/{dev_id}/tests")
async def list_tests(dev_id: str, request: Request):
    user = await get_current_user(request)
    tests = await db.pd_tests.find({"development_id": dev_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return tests

@pd_router.put("/tests/{test_id}")
async def update_test(test_id: str, data: TestUpdate, request: Request):
    user = await get_current_user(request)
    update_fields = {}
    if data.status is not None:
        update_fields["status"] = data.status
    if data.dados is not None:
        update_fields["dados"] = data.dados
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    
    update_fields["updated_at"] = now_iso()
    result = await db.pd_tests.update_one({"id": test_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Teste não encontrado")
    
    test = await db.pd_tests.find_one({"id": test_id}, {"_id": 0})
    return test

@pd_router.delete("/tests/{test_id}")
async def delete_test(test_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.pd_tests.delete_one({"id": test_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Teste não encontrado")
    return {"message": "Teste removido"}

# ============ LAB RESULTS (Unified - all test types at once) ============

class LabResultsUpdate(BaseModel):
    estabilidade: Optional[Dict[str, Any]] = None
    ph: Optional[Dict[str, Any]] = None
    viscosidade: Optional[Dict[str, Any]] = None
    sensorial: Optional[Dict[str, Any]] = None
    compatibilidade: Optional[Dict[str, Any]] = None

@pd_router.get("/developments/{dev_id}/lab-results")
async def get_lab_results(dev_id: str, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    results = await db.pd_lab_results.find_one({"development_id": dev_id}, {"_id": 0})
    if not results:
        return {
            "development_id": dev_id,
            "estabilidade": {},
            "ph": {},
            "viscosidade": {},
            "sensorial": {},
            "compatibilidade": {},
        }
    return results

@pd_router.put("/developments/{dev_id}/lab-results")
async def save_lab_results(dev_id: str, data: LabResultsUpdate, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    update_data = {}
    if data.estabilidade is not None:
        update_data["estabilidade"] = data.estabilidade
    if data.ph is not None:
        update_data["ph"] = data.ph
    if data.viscosidade is not None:
        update_data["viscosidade"] = data.viscosidade
    if data.sensorial is not None:
        update_data["sensorial"] = data.sensorial
    if data.compatibilidade is not None:
        update_data["compatibilidade"] = data.compatibilidade
    
    update_data["updated_at"] = now_iso()
    update_data["updated_by"] = user["id"]
    update_data["updated_by_name"] = user["name"]

    existing = await db.pd_lab_results.find_one({"development_id": dev_id})
    source_changes = _build_source_changes(
        existing or {},
        update_data,
        {
            "estabilidade": "Estabilidade",
            "ph": "pH",
            "viscosidade": "Viscosidade",
            "sensorial": "Sensorial",
            "compatibilidade": "Compatibilidade",
        },
        ignored_fields=["updated_at", "updated_by", "updated_by_name"],
    )
    if existing:
        await db.pd_lab_results.update_one(
            {"development_id": dev_id},
            {"$set": update_data}
        )
    else:
        doc = {
            "id": new_id(),
            "development_id": dev_id,
            "estabilidade": data.estabilidade or {},
            "ph": data.ph or {},
            "viscosidade": data.viscosidade or {},
            "sensorial": data.sensorial or {},
            "compatibilidade": data.compatibilidade or {},
            "updated_at": now_iso(),
            "updated_by": user["id"],
            "updated_by_name": user["name"],
            "created_at": now_iso(),
        }
        await db.pd_lab_results.insert_one(doc)
    
    results = await db.pd_lab_results.find_one({"development_id": dev_id}, {"_id": 0})
    ficha_changed_fields: List[str] = []
    epa_changed_fields: List[str] = []
    if any(field in update_data for field in ("ph", "viscosidade", "estabilidade", "compatibilidade")):
        ficha_changed_fields.append("parametros_in_process")
    if "sensorial" in update_data:
        epa_changed_fields.append("especificacoes_produto_acabado")
    if any(field in update_data for field in ("ph", "viscosidade", "estabilidade", "compatibilidade")):
        epa_changed_fields.extend(["especificacoes_produto_acabado", "criterios_liberacao_lote"])
    if ficha_changed_fields or epa_changed_fields:
        await _auto_generate_documents_for_development(
            dev_id,
            user,
            "lab_results",
            ficha_changed_fields=list(dict.fromkeys(ficha_changed_fields)),
            epa_changed_fields=list(dict.fromkeys(epa_changed_fields)),
            source_changes=source_changes,
        )
    return results

# ============ STABILITY STUDIES ============

@pd_router.get("/stability/constants")
async def get_stability_constants(request: Request):
    await get_current_user(request)
    return {
        "conditions": STABILITY_CONDITIONS,
        "parameters": STABILITY_PARAMETERS,
        "checkpoints": STABILITY_CHECKPOINTS,
    }


@pd_router.get("/stability/studies")
async def list_stability_studies(
    request: Request,
    status: Optional[str] = None,
    pd_card_id: Optional[str] = None,
    sample_id: Optional[str] = None,
    variacao_id: Optional[str] = None,
):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if pd_card_id:
        query["pd_card_id"] = pd_card_id
    if sample_id:
        query["amostra_id"] = sample_id
    if variacao_id:
        query["amostra_variacao_id"] = variacao_id

    studies = await db.pd_stability_studies.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return studies


@pd_router.get("/stability/studies/{study_id}")
async def get_stability_study(study_id: str, request: Request):
    user = await get_current_user(request)
    study = await db.pd_stability_studies.find_one(
        {"id": study_id, "tenant_id": user["tenant_id"]},
        {"_id": 0},
    )
    if not study:
        raise HTTPException(status_code=404, detail="Estudo de estabilidade nao encontrado")
    return study


@pd_router.get("/stability/studies/{study_id}/readings")
async def list_stability_readings(study_id: str, request: Request):
    user = await get_current_user(request)
    study = await db.pd_stability_studies.find_one(
        {"id": study_id, "tenant_id": user["tenant_id"]},
        {"_id": 0, "id": 1},
    )
    if not study:
        raise HTTPException(status_code=404, detail="Estudo de estabilidade nao encontrado")
    readings = await db.pd_stability_readings.find(
        {"study_id": study_id, "tenant_id": user["tenant_id"]},
        {"_id": 0},
    ).sort([("day_offset", 1), ("created_at", 1)]).to_list(5000)
    return readings


@pd_router.post("/stability/studies/{study_id}/readings")
async def create_stability_reading(study_id: str, data: StabilityReadingCreate, request: Request):
    user = await get_current_user(request)
    study = await db.pd_stability_studies.find_one(
        {"id": study_id, "tenant_id": user["tenant_id"]},
        {"_id": 0},
    )
    if not study:
        raise HTTPException(status_code=404, detail="Estudo de estabilidade nao encontrado")
    if study.get("status") == "concluido":
        raise HTTPException(status_code=400, detail="Estudo concluido nao aceita novas leituras")

    condition_map = _stability_condition_map()
    condition_template = condition_map.get(data.condition_code)
    if not condition_template:
        raise HTTPException(status_code=400, detail="Condicao de estabilidade invalida")

    parameters = _normalize_stability_parameters(data.parameters)
    if not parameters:
        raise HTTPException(status_code=400, detail="Informe ao menos um parametro valido da leitura")

    if data.day_offset != 0 and not study.get("d0_completed"):
        raise HTTPException(status_code=400, detail="D0 obrigatorio antes de registrar leituras posteriores")

    existing = await db.pd_stability_readings.find_one(
        {
            "study_id": study_id,
            "tenant_id": user["tenant_id"],
            "condition_code": data.condition_code,
            "day_offset": data.day_offset,
        },
        {"_id": 0},
    )
    if existing:
        raise HTTPException(status_code=409, detail="Ja existe leitura registrada para esta condicao e checkpoint")

    reading_at = data.reading_at or now_iso()
    reading = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "study_id": study_id,
        "pd_card_id": study.get("pd_card_id"),
        "amostra_id": study.get("amostra_id"),
        "amostra_variacao_id": study.get("amostra_variacao_id"),
        "condition_code": data.condition_code,
        "condition_label": condition_template["label"],
        "day_offset": data.day_offset,
        "reading_at": reading_at,
        "parameters": parameters,
        "notes": clean_text(data.notes),
        "photo_urls": [clean_text(url) for url in data.photo_urls if clean_text(url)],
        "created_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
    }
    await db.pd_stability_readings.insert_one(reading)

    updated_conditions: List[Dict[str, Any]] = []
    for condition in study.get("conditions", []):
        if condition.get("code") != data.condition_code:
            updated_conditions.append(condition)
            continue

        completed = sorted(set(list(condition.get("completed_day_offsets") or []) + [data.day_offset]))
        pending = [checkpoint for checkpoint in condition.get("checkpoints", []) if checkpoint not in completed]
        updated_conditions.append({
            **condition,
            "completed_day_offsets": completed,
            "next_due_day_offset": pending[0] if pending else None,
            "next_due_at": _iso_after_days(study["started_at"], pending[0]) if pending else None,
            "last_reading_at": reading_at,
        })

    await db.pd_stability_studies.update_one(
        {"id": study_id, "tenant_id": user["tenant_id"]},
        {
            "$set": {
                "conditions": updated_conditions,
                "d0_completed": study.get("d0_completed") or data.day_offset == 0,
                "updated_at": now_iso(),
            }
        },
    )
    refreshed = await _recalculate_stability_study(study_id)

    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="stability_reading_created",
        entity_type="stability_study",
        entity_id=study_id,
        after={
            "condition_code": data.condition_code,
            "day_offset": data.day_offset,
            "parameters": list(parameters.keys()),
        },
    )
    return {
        "reading": reading,
        "study": refreshed,
    }


@pd_router.get("/stability/dashboard")
async def get_stability_dashboard(request: Request):
    user = await get_current_user(request)
    studies = await db.pd_stability_studies.find(
        {"tenant_id": user["tenant_id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(2000)

    counts = {"critico": 0, "atencao": 0, "em_dia": 0, "pendente_d0": 0, "concluido": 0}
    for study in studies:
        status = (study.get("summary") or {}).get("overall_status", "em_dia")
        counts[status] = counts.get(status, 0) + 1

    return {
        "counts": counts,
        "studies": studies,
    }


@pd_router.post("/stability/admin/check-alerts")
async def trigger_stability_alert_check(request: Request):
    user = await get_current_user(request)
    if user.get("role") not in ("admin", "gestor"):
        raise HTTPException(status_code=403, detail="Apenas admin/gestor podem executar a varredura de alertas")
    created = await check_stability_alerts_for_tenant(user["tenant_id"])
    return {"tasks_created": created}

# ============ SAMPLES ============

@pd_router.post("/developments/{dev_id}/samples")
async def create_sample(dev_id: str, data: SampleCreate, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    sample_id = new_id()
    sample = {
        "id": sample_id,
        "development_id": dev_id,
        "formula_version": data.formula_version,
        "sent_to_client": data.sent_to_client,
        "sent_at": now_iso() if data.sent_to_client else None,
        "feedback": data.feedback or "",
        "created_at": now_iso(),
    }
    await db.pd_samples.insert_one(sample)
    sample.pop("_id", None)
    return sample

@pd_router.get("/developments/{dev_id}/samples")
async def list_samples(dev_id: str, request: Request):
    user = await get_current_user(request)
    samples = await db.pd_samples.find({"development_id": dev_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return samples

@pd_router.put("/samples/{sample_id}")
async def update_sample(sample_id: str, data: SampleUpdate, request: Request):
    user = await get_current_user(request)
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    
    if update_fields.get("sent_to_client") == True:
        update_fields["sent_at"] = now_iso()
    
    result = await db.pd_samples.update_one({"id": sample_id}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")
    
    sample = await db.pd_samples.find_one({"id": sample_id}, {"_id": 0})
    return sample

# ============ APPROVALS ============

@pd_router.post("/developments/{dev_id}/approval")
async def create_approval(dev_id: str, data: ApprovalCreate, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    existing = await db.pd_approvals.find_one({"development_id": dev_id})
    source_changes = _build_source_changes(
        existing or {},
        {
            "approved_by_client": data.approved_by_client,
            "approved_by_internal": data.approved_by_internal,
            "notes": data.notes or "",
        },
        {
            "approved_by_client": "Aprovacao do cliente",
            "approved_by_internal": "Aprovacao interna",
            "notes": "Observacoes da aprovacao",
        },
    )
    if existing:
        await db.pd_approvals.update_one(
            {"development_id": dev_id},
            {"$set": {
                "approved_by_client": data.approved_by_client,
                "approved_by_internal": data.approved_by_internal,
                "notes": data.notes or "",
                "approval_date": now_iso(),
                "approved_by_user": user["id"],
                "approved_by_user_name": user["name"],
            }}
        )
        approval = await db.pd_approvals.find_one({"development_id": dev_id}, {"_id": 0})
    else:
        approval_id = new_id()
        approval = {
            "id": approval_id,
            "development_id": dev_id,
            "approved_by_client": data.approved_by_client,
            "approved_by_internal": data.approved_by_internal,
            "approval_date": now_iso(),
            "notes": data.notes or "",
            "approved_by_user": user["id"],
            "approved_by_user_name": user["name"],
        }
        await db.pd_approvals.insert_one(approval)
        approval.pop("_id", None)
    
    if data.approved_by_client:
        await _auto_generate_documents_for_request(
            dev["pd_request_id"],
            user,
            "aprovacao_cliente",
            ficha_changed_fields=["aprovacao_cliente"],
            epa_changed_fields=["aprovacao_cliente"],
            source_changes=source_changes,
        )
    return approval

@pd_router.get("/developments/{dev_id}/approval")
async def get_approval(dev_id: str, request: Request):
    user = await get_current_user(request)
    approval = await db.pd_approvals.find_one({"development_id": dev_id}, {"_id": 0})
    if not approval:
        return None
    return approval

# ============ COSTS (auto-calculated from formula) ============

@pd_router.post("/developments/{dev_id}/costs")
async def save_costs(dev_id: str, data: CostCreate, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    total = data.ingredient_cost + data.packaging_cost + data.labor_cost
    
    existing = await db.pd_costs.find_one({"development_id": dev_id})
    if existing:
        await db.pd_costs.update_one(
            {"development_id": dev_id},
            {"$set": {
                "ingredient_cost": data.ingredient_cost,
                "packaging_cost": data.packaging_cost,
                "labor_cost": data.labor_cost,
                "total_cost": total,
                "updated_at": now_iso(),
            }}
        )
        cost = await db.pd_costs.find_one({"development_id": dev_id}, {"_id": 0})
    else:
        cost_id = new_id()
        cost = {
            "id": cost_id,
            "development_id": dev_id,
            "ingredient_cost": data.ingredient_cost,
            "packaging_cost": data.packaging_cost,
            "labor_cost": data.labor_cost,
            "total_cost": total,
            "updated_at": now_iso(),
        }
        await db.pd_costs.insert_one(cost)
        cost.pop("_id", None)
    
    return cost

@pd_router.get("/developments/{dev_id}/costs")
async def get_costs(dev_id: str, request: Request):
    user = await get_current_user(request)
    cost = await db.pd_costs.find_one({"development_id": dev_id}, {"_id": 0})
    if not cost:
        return {"ingredient_cost": 0, "packaging_cost": 0, "labor_cost": 0, "total_cost": 0}
    return cost

# ============ COSTS AUTO-CALCULATE FROM FORMULA ============

@pd_router.get("/developments/{dev_id}/formula-costs")
async def get_formula_costs(dev_id: str, request: Request):
    """Auto-calculate costs from the latest formula"""
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    # Get latest formula
    formulas = await db.pd_formulas.find({"development_id": dev_id}, {"_id": 0}).sort("version", -1).to_list(1)
    if not formulas:
        return {"formula": None, "items": [], "totals": None}
    
    formula = formulas[0]
    items = await db.pd_formula_items.find({"formula_id": formula["id"]}, {"_id": 0}).to_list(200)
    
    total_percentage = sum(it.get("percentage", 0) for it in items)
    total_cost_per_kg = sum(it.get("cost_brl", 0) for it in items)
    total_price_sum = sum(it.get("price_per_kg", 0) for it in items)
    cotacao = formula.get("cotacao_usd", 6.00) or 6.00
    
    volume = formula.get("volume", 0) or 0
    volume_unit = formula.get("volume_unit", "mL")
    volume_kg = volume / 1000.0 if volume_unit == "mL" else volume
    indice_perdas = formula.get("indice_perdas", 0) or 0
    
    custo_unitario = total_cost_per_kg * volume_kg if volume_kg > 0 else total_cost_per_kg
    custo_com_perdas = custo_unitario * (1 + indice_perdas / 100.0) if indice_perdas > 0 else custo_unitario
    
    for it in items:
        it["cost_percentage"] = round((it.get("cost_brl", 0) / total_cost_per_kg * 100), 2) if total_cost_per_kg > 0 else 0
    
    return {
        "formula": formula,
        "items": items,
        "totals": {
            "total_percentage": round(total_percentage, 3),
            "total_price_sum": round(total_price_sum, 2),
            "total_cost_per_kg": round(total_cost_per_kg, 4),
            "custo_unitario": round(custo_unitario, 2),
            "custo_com_perdas": round(custo_com_perdas, 2),
            "cotacao_usd": cotacao,
            "volume": volume,
            "volume_unit": volume_unit,
            "indice_perdas": indice_perdas,
        }
    }

# ============ DOCUMENTS ============

@pd_router.post("/developments/{dev_id}/documents")
async def add_document(dev_id: str, data: DocumentCreate, request: Request):
    user = await get_current_user(request)
    dev = await db.pd_developments.find_one({"id": dev_id, "tenant_id": user["tenant_id"]})
    if not dev:
        raise HTTPException(status_code=404, detail="Desenvolvimento não encontrado")
    
    doc_id = new_id()
    doc = {
        "id": doc_id,
        "development_id": dev_id,
        "doc_type": data.doc_type,
        "file_url": data.file_url,
        "file_name": data.file_name or "",
        "uploaded_by": user["id"],
        "uploaded_by_name": user["name"],
        "uploaded_at": now_iso(),
    }
    await db.pd_documents.insert_one(doc)
    doc.pop("_id", None)
    return doc

@pd_router.get("/developments/{dev_id}/documents")
async def list_documents(dev_id: str, request: Request):
    user = await get_current_user(request)
    docs = await db.pd_documents.find({"development_id": dev_id}, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
    return docs

@pd_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.pd_documents.delete_one({"id": doc_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return {"message": "Documento removido"}


@pd_router.post("/requests/{req_id}/live-documents/{doc_type}/generate")
async def generate_live_document(req_id: str, doc_type: str, data: LiveDocumentGenerate, request: Request):
    user = await get_current_user(request)
    if doc_type not in LIVE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de documento vivo invalido")
    return await _generate_live_document_version(
        req_id=req_id,
        doc_type=doc_type,
        user=user,
        reason=data.reason,
        changed_fields=data.changed_fields or [doc_type],
        trigger="manual",
        source_changes=[],
    )


@pd_router.get("/requests/{req_id}/live-documents/{doc_type}/versions")
async def list_live_document_versions(req_id: str, doc_type: str, request: Request):
    user = await get_current_user(request)
    if doc_type not in LIVE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de documento vivo invalido")
    query = {"tenant_id": user["tenant_id"], "pd_request_id": req_id, "doc_type": doc_type}
    if not _user_can_review_live_documents(user):
        query["status"] = "aprovado"
        query["active_for_operation"] = True
    return await db.pd_document_versions.find(query, {"_id": 0}).sort("version_number", -1).to_list(100)


@pd_router.get("/requests/{req_id}/live-documents/{doc_type}/current")
async def get_current_live_document(req_id: str, doc_type: str, request: Request):
    user = await get_current_user(request)
    if doc_type not in LIVE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de documento vivo invalido")
    base_query = {"tenant_id": user["tenant_id"], "pd_request_id": req_id, "doc_type": doc_type}
    query = dict(base_query)
    if not _user_can_review_live_documents(user):
        query["status"] = "aprovado"
        query["active_for_operation"] = True
    doc_version = await db.pd_document_versions.find_one(query, {"_id": 0}, sort=[("version_number", -1)])
    if not doc_version and _user_can_review_live_documents(user):
        doc_version = await db.pd_document_versions.find_one(base_query, {"_id": 0}, sort=[("version_number", -1)])
    if not doc_version:
        raise HTTPException(status_code=404, detail="Documento vivo nao encontrado")
    return await _get_live_document_version(doc_version["id"], user)


@pd_router.get("/document-versions/{version_id}")
async def get_live_document_version(version_id: str, request: Request):
    user = await get_current_user(request)
    return await _get_live_document_version(version_id, user)


@pd_router.get("/document-versions/{version_id}/pdf")
async def export_live_document_pdf(version_id: str, request: Request):
    """Exporta PDF da versao do documento vivo (FT/EPA). Aplica watermark 'EM REVISAO' quando ainda nao aprovado."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfgen import canvas as rl_canvas

    user = await get_current_user(request)
    doc_version = await _get_live_document_version(version_id, user)
    snapshot = doc_version.get("snapshot") or {}
    tenant = await db.tenants.find_one({"id": user["tenant_id"]}, {"_id": 0})
    org_name = tenant["name"] if tenant else "Kuryos"
    is_approved = doc_version.get("status") == "aprovado" and doc_version.get("active_for_operation")
    label = _document_label(doc_version["doc_type"])

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4, topMargin=22*mm, bottomMargin=18*mm, leftMargin=18*mm, rightMargin=18*mm, title=f"{label} {doc_version.get('version_code', '')}")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("LDTitle", parent=styles["Title"], fontSize=22, textColor=rl_colors.HexColor("#0A0A0B"), spaceAfter=4)
    sub_style = ParagraphStyle("LDSub", parent=styles["Normal"], fontSize=11, textColor=rl_colors.HexColor("#737373"), spaceAfter=10)
    h_style = ParagraphStyle("LDHead", parent=styles["Heading2"], fontSize=13, textColor=rl_colors.HexColor("#0A0A0B"), spaceBefore=12, spaceAfter=6)
    n_style = ParagraphStyle("LDNorm", parent=styles["Normal"], fontSize=9.5, leading=13)
    s_style = ParagraphStyle("LDSm", parent=styles["Normal"], fontSize=8, textColor=rl_colors.HexColor("#737373"))

    elements: List[Any] = []
    elements.append(Paragraph(label.upper(), title_style))
    elements.append(Paragraph(f"{org_name} - Documento Vivo (versionado)", sub_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor("#E5E5E5")))

    meta_rows = [
        ["Codigo:", doc_version.get("version_code", "")],
        ["Versao:", str(doc_version.get("version_number", ""))],
        ["Status:", "APROVADO E VIGENTE" if is_approved else "EM REVISAO (NAO LIBERADO PARA PRODUCAO)"],
        ["Gerado em:", doc_version.get("created_at", "")],
        ["Por:", doc_version.get("created_by_name", "")],
        ["Motivo:", doc_version.get("reason", "")],
    ]
    meta_table = Table(meta_rows, colWidths=[35*mm, 140*mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), rl_colors.HexColor("#737373")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(Spacer(1, 4*mm))
    elements.append(meta_table)

    def render_section(title: str, data: Any):
        elements.append(Paragraph(title, h_style))
        if isinstance(data, dict):
            rows = []
            for k, v in data.items():
                if isinstance(v, (list, dict)):
                    continue
                rows.append([str(k).replace("_", " ").capitalize() + ":", str(v) if v not in (None, "") else "-"])
            if rows:
                t = Table(rows, colWidths=[55*mm, 120*mm])
                t.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (0, -1), rl_colors.HexColor("#737373")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                elements.append(t)
            for k, v in data.items():
                if isinstance(v, list) and v:
                    if all(isinstance(it, dict) for it in v):
                        keys = list({key for it in v for key in it.keys()})
                        keys = [k for k in keys if k in ("ingredient_name", "nome_tecnico", "nome_comercial", "inci", "fornecedor", "phase", "function", "percentage", "price_per_kg", "cost_brl", "quantidade_lote_padrao", "unidade_lote")]
                        if keys:
                            header = [k.replace("_", " ").capitalize() for k in keys]
                            rows = [header]
                            for it in v[:200]:
                                rows.append([str(it.get(k, "") or "") for k in keys])
                            tab = Table(rows, repeatRows=1)
                            tab.setStyle(TableStyle([
                                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#0A0A0B")),
                                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                                ("GRID", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#E5E5E5")),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ]))
                            elements.append(Paragraph(k.replace("_", " ").capitalize(), s_style))
                            elements.append(tab)
                    else:
                        elements.append(Paragraph(", ".join(str(it) for it in v), n_style))

    for section_key, section_value in snapshot.items():
        render_section(section_key.replace("_", " ").upper(), section_value)

    elements.append(Spacer(1, 14*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.HexColor("#E5E5E5"), spaceAfter=4))
    elements.append(Paragraph(
        f"Documento gerado automaticamente em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC - {org_name}",
        s_style,
    ))

    def watermark(canvas: rl_canvas.Canvas, _doc):
        if not is_approved:
            canvas.saveState()
            canvas.setFillColorRGB(0.85, 0.0, 0.0, alpha=0.18)
            canvas.setFont("Helvetica-Bold", 80)
            canvas.translate(297, 421)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "EM REVISAO")
            canvas.restoreState()

    pdf.build(elements, onFirstPage=watermark, onLaterPages=watermark)
    buffer.seek(0)
    safe_code = (doc_version.get("version_code") or "doc").replace("/", "_")
    filename = f"{label.replace(' ', '_').lower()}_{safe_code}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# ============ FULL DETAIL VIEW ============

@pd_router.get("/requests/{req_id}/full")
async def get_pd_full_detail(req_id: str, request: Request):
    """Get complete P&D request with all related data"""
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    
    history = await db.pd_request_status_history.find(
        {"pd_request_id": req_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    dev = await db.pd_developments.find_one({"pd_request_id": req_id}, {"_id": 0})
    
    formulas = []
    tests = []
    samples = []
    approval = None
    costs = {"ingredient_cost": 0, "packaging_cost": 0, "labor_cost": 0, "total_cost": 0}
    documents = []
    formula_cost_data = None
    lab_results_doc = None
    
    if dev:
        formulas = await db.pd_formulas.find({"development_id": dev["id"]}, {"_id": 0}).sort("version", -1).to_list(100)
        for f in formulas:
            items = await db.pd_formula_items.find({"formula_id": f["id"]}, {"_id": 0}).to_list(200)
            total_cost = sum(it.get("cost_brl", 0) for it in items)
            for it in items:
                it["cost_percentage"] = round((it.get("cost_brl", 0) / total_cost * 100), 2) if total_cost > 0 else 0
            f["items"] = items
            volume = f.get("volume", 0) or 0
            volume_unit = f.get("volume_unit", "mL")
            volume_kg = volume / 1000.0 if volume_unit == "mL" else volume
            f["custo_unitario"] = round(total_cost * volume_kg, 2) if volume_kg > 0 else round(total_cost, 2)
            f["total_cost_per_kg"] = round(total_cost, 4)
        
        tests = await db.pd_tests.find({"development_id": dev["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
        samples = await db.pd_samples.find({"development_id": dev["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
        approval = await db.pd_approvals.find_one({"development_id": dev["id"]}, {"_id": 0})
        cost_doc = await db.pd_costs.find_one({"development_id": dev["id"]}, {"_id": 0})
        if cost_doc:
            costs = cost_doc
        documents = await db.pd_documents.find({"development_id": dev["id"]}, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
        
        # Get unified lab results
        lab_results_doc = await db.pd_lab_results.find_one({"development_id": dev["id"]}, {"_id": 0})
        
        # Calculate formula cost data from latest formula
        if formulas:
            latest = formulas[0]
            items = latest.get("items", [])
            total_cost_per_kg = sum(it.get("cost_brl", 0) for it in items)
            total_price_sum = sum(it.get("price_per_kg", 0) for it in items)
            cotacao = latest.get("cotacao_usd", 6.00) or 6.00
            vol = latest.get("volume", 0) or 0
            vu = latest.get("volume_unit", "mL")
            vkg = vol / 1000.0 if vu == "mL" else vol
            ip = latest.get("indice_perdas", 0) or 0
            cu = total_cost_per_kg * vkg if vkg > 0 else total_cost_per_kg
            cp = cu * (1 + ip / 100.0) if ip > 0 else cu
            formula_cost_data = {
                "total_cost_per_kg": round(total_cost_per_kg, 4),
                "total_price_sum": round(total_price_sum, 2),
                "custo_unitario": round(cu, 2),
                "custo_com_perdas": round(cp, 2),
                "cotacao_usd": cotacao,
                "volume": vol,
                "volume_unit": vu,
                "indice_perdas": ip,
            }
    
    # Get client info from CRM if linked
    client_info = None
    if pd_req.get("client_card_id"):
        client_info = await db.cards.find_one({"id": pd_req["client_card_id"]}, {"_id": 0})

    # Get updates + pending (new feature: Atualizações)
    updates_list = await db.pd_updates.find(
        {"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    pending_list = await db.pd_pending_items.find(
        {"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    now_dt = datetime.now(timezone.utc)
    for it in pending_list:
        if it["status"] == "pendente" and it.get("data_prevista"):
            try:
                dp = datetime.fromisoformat(it["data_prevista"].replace("Z", "+00:00")) if isinstance(it["data_prevista"], str) else it["data_prevista"]
                if dp.tzinfo is None:
                    dp = dp.replace(tzinfo=timezone.utc)
                it["status_calc"] = "atrasado" if dp < now_dt else "pendente"
            except Exception:
                it["status_calc"] = "pendente"
        else:
            it["status_calc"] = it["status"]

    return {
        "request": pd_req,
        "history": history,
        "development": dev,
        "formulas": formulas,
        "tests": tests,
        "samples": samples,
        "approval": approval,
        "costs": costs,
        "documents": documents,
        "client_info": client_info,
        "formula_cost_data": formula_cost_data,
        "lab_results": lab_results_doc if dev else None,
        "updates": updates_list,
        "pending": pending_list,
        "blocking_tasks": await get_blocking_tasks(
            tenant_id=user["tenant_id"],
            entity_type="pd_card",
            entity_id=req_id,
        ),
    }

# ============ DASHBOARD METRICS ============

@pd_router.get("/metrics")
async def pd_metrics(request: Request):
    user = await get_current_user(request)
    tid = user["tenant_id"]
    
    total = await db.pd_requests.count_documents({"tenant_id": tid})
    by_status = {}
    for status in VALID_STATUSES:
        by_status[status] = await db.pd_requests.count_documents({"tenant_id": tid, "status": status})
    
    by_priority = {}
    for prio in ["Baixa", "Normal", "Alta", "Urgente"]:
        by_priority[prio] = await db.pd_requests.count_documents({"tenant_id": tid, "priority": prio})
    
    return {
        "total": total,
        "by_status": by_status,
        "by_priority": by_priority,
    }

# ============ FICHA TÉCNICA - UI DATA (analise laboratorial) ============

class FichaTecnicaParam(BaseModel):
    especificacao: str = ""
    resultado: str = ""
    pa: str = ""  # "Conforme" | "Não Conforme" | ""

class FichaTecnicaAnaliseUpsert(BaseModel):
    produto: Optional[str] = None
    lote: Optional[str] = None
    data_fabricacao: Optional[str] = None
    validade: Optional[str] = None
    quantidade: Optional[str] = None
    aspecto: Optional[FichaTecnicaParam] = None
    cor: Optional[FichaTecnicaParam] = None
    densidade: Optional[FichaTecnicaParam] = None
    odor: Optional[FichaTecnicaParam] = None
    ph: Optional[FichaTecnicaParam] = None
    teor_alcool: Optional[FichaTecnicaParam] = None
    elaboracao: Optional[str] = None
    resp_tecnico: Optional[str] = None
    status_aprovacao: Optional[str] = None  # "aprovado" | "reprovado"

@pd_router.get("/requests/{req_id}/ficha-tecnica-ui")
async def get_ficha_tecnica_ui(req_id: str, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    dev = await db.pd_developments.find_one({"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    formula = None
    items = []
    if dev:
        formula = await db.pd_formulas.find_one({"development_id": dev["id"]}, {"_id": 0}, sort=[("version", -1)])
        if formula:
            items = await db.pd_formula_items.find({"formula_id": formula["id"]}, {"_id": 0}).to_list(200)
    analise = await db.pd_ficha_tecnica.find_one({"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0}) or {}
    return {
        "request": pd_req,
        "development": dev,
        "formula": formula,
        "formula_items": items,
        "analise": analise,
    }

@pd_router.put("/requests/{req_id}/ficha-tecnica-ui")
async def save_ficha_tecnica_ui(req_id: str, data: FichaTecnicaAnaliseUpsert, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    dev = await db.pd_developments.find_one({"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    update_data = {}
    for field in ["produto", "lote", "data_fabricacao", "validade", "quantidade", "elaboracao", "resp_tecnico", "status_aprovacao"]:
        val = getattr(data, field, None)
        if val is not None:
            update_data[field] = val
    for param in ["aspecto", "cor", "densidade", "odor", "ph", "teor_alcool"]:
        val = getattr(data, param, None)
        if val is not None:
            update_data[param] = val.model_dump()
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    update_data.update({
        "updated_at": now_iso(),
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    })
    existing = await db.pd_ficha_tecnica.find_one({"pd_request_id": req_id, "tenant_id": user["tenant_id"]})
    if existing:
        await db.pd_ficha_tecnica.update_one({"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"$set": update_data})
    else:
        update_data.update({
            "id": new_id(),
            "pd_request_id": req_id,
            "development_id": dev["id"] if dev else None,
            "tenant_id": user["tenant_id"],
            "created_at": now_iso(),
        })
        await db.pd_ficha_tecnica.insert_one(update_data)
    result = await db.pd_ficha_tecnica.find_one({"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    return result


# ============ FICHA TÉCNICA PDF GENERATION ============

@pd_router.get("/requests/{req_id}/ficha-tecnica")
async def generate_ficha_tecnica(req_id: str, request: Request):
    """Generate a professional technical sheet PDF for a P&D development"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    dev = await db.pd_developments.find_one({"pd_request_id": req_id}, {"_id": 0})
    
    formulas = []
    tests = []
    approval = None
    cost_data = None
    
    if dev:
        formulas = await db.pd_formulas.find({"development_id": dev["id"]}, {"_id": 0}).sort("version", -1).to_list(100)
        for f in formulas:
            f["items"] = await db.pd_formula_items.find({"formula_id": f["id"]}, {"_id": 0}).to_list(200)
        tests = await db.pd_tests.find({"development_id": dev["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
        approval = await db.pd_approvals.find_one({"development_id": dev["id"]}, {"_id": 0})
        cost_data = await db.pd_costs.find_one({"development_id": dev["id"]}, {"_id": 0})

    # Get client info
    client_info = None
    if pd_req.get("client_card_id"):
        client_info = await db.cards.find_one({"id": pd_req["client_card_id"]}, {"_id": 0})

    tenant = await db.tenants.find_one({"id": user["tenant_id"]}, {"_id": 0})
    org_name = tenant["name"] if tenant else "Kuryos"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=25*mm, bottomMargin=20*mm, leftMargin=20*mm, rightMargin=20*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('FTTitle', parent=styles['Title'], fontSize=22, spaceAfter=4, textColor=rl_colors.HexColor('#0A0A0B'))
    subtitle_style = ParagraphStyle('FTSubtitle', parent=styles['Normal'], fontSize=12, textColor=rl_colors.HexColor('#737373'), spaceAfter=8)
    heading_style = ParagraphStyle('FTHeading', parent=styles['Heading2'], fontSize=13, spaceAfter=6, spaceBefore=14, textColor=rl_colors.HexColor('#0A0A0B'))
    normal_style = ParagraphStyle('FTNormal', parent=styles['Normal'], fontSize=9.5, spaceAfter=3, leading=13)
    small_style = ParagraphStyle('FTSmall', parent=styles['Normal'], fontSize=8, textColor=rl_colors.HexColor('#737373'))
    
    elements = []

    elements.append(Paragraph("FICHA TÉCNICA", title_style))
    elements.append(Paragraph(f"{org_name} — Pesquisa & Desenvolvimento", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor('#E5E5E5'), spaceAfter=8))

    # Product Info
    elements.append(Paragraph("1. IDENTIFICAÇÃO DO PRODUTO", heading_style))
    info_data = [
        ["Projeto:", pd_req["project_name"]],
        ["Tipo:", pd_req.get("request_type", "—")],
        ["Cliente:", pd_req.get("client_name", "—")],
        ["Prioridade:", pd_req.get("priority", "—")],
        ["Status:", STATUS_LABELS.get(pd_req["status"], pd_req["status"])],
    ]
    
    info_table = Table(info_data, colWidths=[40*mm, 130*mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('TEXTCOLOR', (0, 0), (0, -1), rl_colors.HexColor('#737373')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)

    # Briefing from CRM
    if client_info:
        elements.append(Paragraph("2. BRIEFING DO PROJETO", heading_style))
        briefing_data = []
        if client_info.get("produto"):
            briefing_data.append(["Produto:", client_info["produto"]])
        if client_info.get("objetivo_projeto"):
            briefing_data.append(["Objetivo:", client_info["objetivo_projeto"]])
        if client_info.get("aplicacoes_desenvolver"):
            briefing_data.append(["Aplicações:", client_info["aplicacoes_desenvolver"]])
        if client_info.get("textura_esperada"):
            briefing_data.append(["Textura:", client_info["textura_esperada"]])
        if client_info.get("sensorial"):
            briefing_data.append(["Sensorial:", client_info["sensorial"]])
        if client_info.get("ph"):
            briefing_data.append(["pH:", client_info["ph"]])
        if client_info.get("orcamento_projeto"):
            briefing_data.append(["Orçamento:", client_info["orcamento_projeto"]])
        if briefing_data:
            bt = Table(briefing_data, colWidths=[40*mm, 130*mm])
            bt.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9.5),
                ('TEXTCOLOR', (0, 0), (0, -1), rl_colors.HexColor('#737373')),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(bt)

    # Formula with costs
    section_num = 3
    if formulas:
        latest = formulas[0]
        elements.append(Paragraph(f"{section_num}. MANIPULAÇÃO / FORMULAÇÃO (v{latest['version']})", heading_style))
        
        if latest.get("items"):
            formula_header = ["Formulação", "%Fórmula", "Preço R$(Kg)", "Custo R$", "Custo Kg/U$", "% de Custo"]
            formula_rows = [formula_header]
            total_pct = 0
            total_cost = 0
            total_price = 0
            for item in latest["items"]:
                pct = item.get("percentage", 0)
                ppk = item.get("price_per_kg", 0)
                cb = item.get("cost_brl", 0)
                cku = item.get("cost_kg_usd", 0)
                total_pct += pct
                total_cost += cb
                total_price += ppk
                formula_rows.append([
                    item["ingredient_name"],
                    f"{pct:.3f}",
                    f"{ppk:.2f}",
                    f"{cb:.2f}",
                    f"{cku:.2f}",
                    "",  # will be filled after total
                ])
            # Fill cost percentages
            for i in range(1, len(formula_rows)):
                cb = float(formula_rows[i][3])
                cp = (cb / total_cost * 100) if total_cost > 0 else 0
                formula_rows[i][5] = f"{cp:.1f}%"
            
            vol = latest.get("volume", 0) or 0
            vu = latest.get("volume_unit", "mL")
            vkg = vol / 1000.0 if vu == "mL" else vol
            cu = total_cost * vkg if vkg > 0 else total_cost
            
            formula_rows.append(["Custo Unit.", f"{total_pct:.2f}", f"{total_price:.2f}", f"R$ {cu:.2f}", "", "100,00%"])

            ft = Table(formula_rows, colWidths=[35*mm, 22*mm, 25*mm, 22*mm, 25*mm, 22*mm])
            ft.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#0A0A0B')),
                ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('GRID', (0, 0), (-1, -2), 0.5, rl_colors.HexColor('#E5E5E5')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('TOPPADDING', (0, -1), (-1, -1), 8),
                ('LINEABOVE', (0, -1), (-1, -1), 1, rl_colors.HexColor('#0A0A0B')),
                ('BACKGROUND', (3, -1), (3, -1), rl_colors.HexColor('#E5E5E5')),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
            ]))
            elements.append(ft)
        section_num += 1

    # Tests
    if tests:
        elements.append(Paragraph(f"{section_num}. RESULTADOS DE TESTES", heading_style))
        status_label = {"PENDING": "Pendente", "RUNNING": "Em andamento", "APPROVED": "Aprovado", "FAILED": "Reprovado"}
        for t in tests:
            dados = t.get("dados", {})
            result_text = ""
            if dados:
                for k, v in dados.items():
                    if v:
                        result_text += f"{k}: {v}; "
            elements.append(Paragraph(f"<b>{t['test_type']}</b> — {status_label.get(t['status'], t['status'])}", normal_style))
            if result_text:
                elements.append(Paragraph(result_text.rstrip("; "), small_style))
        section_num += 1

    # Footer
    elements.append(Spacer(1, 20*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.HexColor('#E5E5E5'), spaceAfter=4))
    elements.append(Paragraph(
        f"Documento gerado automaticamente em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC — {org_name}",
        small_style
    ))

    doc.build(elements)
    buffer.seek(0)

    safe_name = pd_req["project_name"].replace(" ", "_").replace("/", "-")
    filename = f"ficha_tecnica_{safe_name}.pdf"
    return StreamingResponse(buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# ============================================================
# EXTENSÕES P&D: CATALOG, INTERNAL RESEARCH, STOCK, UPDATES
# ============================================================

# ----------- MODELS ------------

class CatalogItemCreate(BaseModel):
    nome: str
    inci: Optional[str] = None
    fornecedor: Optional[str] = None
    preco_rs_kg: float = 0.0
    moeda: str = "BRL"  # BRL or USD
    unidade: str = "kg"  # kg, L
    categoria: Optional[str] = None  # ativo, solvente, conservante, fragrância, espessante, etc
    observacoes: Optional[str] = None

class CatalogItemUpdate(BaseModel):
    nome: Optional[str] = None
    inci: Optional[str] = None
    fornecedor: Optional[str] = None
    preco_rs_kg: Optional[float] = None
    moeda: Optional[str] = None
    unidade: Optional[str] = None
    categoria: Optional[str] = None
    observacoes: Optional[str] = None

class InternalResearchCreate(BaseModel):
    project_name: str
    description: Optional[str] = None
    category: Optional[str] = None
    references: Optional[str] = None
    objectives: Optional[str] = None
    priority: str = "Normal"
    deadline: Optional[str] = None

class StockItemCreate(BaseModel):
    categoria: str  # mp, insumo, amostra_acabada
    nome: str
    codigo_interno: Optional[str] = None
    unidade_medida: str = "kg"  # kg, g, mL, L, un
    quantidade_atual: float = 0.0
    quantidade_minima: float = 0.0
    lote: Optional[str] = None
    validade: Optional[str] = None  # ISO date string
    localizacao: Optional[str] = None  # gaveta/prateleira/local
    custo_unitario: float = 0.0
    fornecedor: Optional[str] = None
    observacoes: Optional[str] = None
    catalog_id: Optional[str] = None  # Link to catalog (for MPs)
    # For amostra_acabada
    formula_ref: Optional[str] = None  # e.g., "Body Splash La Vie 3% fragrância"
    fragrancia_percentual: Optional[float] = None
    linked_pd_request_id: Optional[str] = None
    linked_formula_id: Optional[str] = None

class StockItemUpdate(BaseModel):
    nome: Optional[str] = None
    codigo_interno: Optional[str] = None
    unidade_medida: Optional[str] = None
    quantidade_minima: Optional[float] = None
    lote: Optional[str] = None
    validade: Optional[str] = None
    localizacao: Optional[str] = None
    custo_unitario: Optional[float] = None
    fornecedor: Optional[str] = None
    observacoes: Optional[str] = None
    catalog_id: Optional[str] = None
    formula_ref: Optional[str] = None
    fragrancia_percentual: Optional[float] = None

class StockMovementCreate(BaseModel):
    tipo: str  # entrada, saida, ajuste
    quantidade: float
    motivo: Optional[str] = None
    lote: Optional[str] = None
    linked_dev_id: Optional[str] = None
    linked_pd_request_id: Optional[str] = None

class UpdateCreate(BaseModel):
    mensagem: str
    tipo: Optional[str] = "observacao"  # observacao, status, pendencia_resolvida, chegada_material
    visivel_comercial: bool = True

class PendingItemCreate(BaseModel):
    tipo: str  # fragrancia, mp, insumo, amostra, outro
    descricao: str
    data_prevista: Optional[str] = None  # ISO date
    fornecedor: Optional[str] = None
    observacoes: Optional[str] = None

class PendingItemUpdate(BaseModel):
    tipo: Optional[str] = None
    descricao: Optional[str] = None
    data_prevista: Optional[str] = None
    fornecedor: Optional[str] = None
    observacoes: Optional[str] = None
    status: Optional[str] = None  # pendente, recebido, atrasado, cancelado


# ============ 1) BANCO DE CUSTOS (CATALOG) ============

@pd_router.post("/catalog")
async def create_catalog_item(data: CatalogItemCreate, request: Request):
    user = await get_current_user(request)
    item_id = new_id()
    item = {
        "id": item_id,
        "tenant_id": user["tenant_id"],
        "nome": data.nome.strip(),
        "inci": (data.inci or "").strip(),
        "fornecedor": (data.fornecedor or "").strip(),
        "preco_rs_kg": float(data.preco_rs_kg or 0),
        "moeda": data.moeda or "BRL",
        "unidade": data.unidade or "kg",
        "categoria": (data.categoria or "").strip(),
        "observacoes": (data.observacoes or "").strip(),
        "ultima_atualizacao": now_iso(),
        "atualizado_por": user["name"],
        "atualizado_por_id": user["id"],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
    }
    await db.pd_catalog.insert_one(item)
    item.pop("_id", None)
    return item

@pd_router.get("/catalog")
async def list_catalog(request: Request, q: Optional[str] = None, categoria: Optional[str] = None):
    user = await get_current_user(request)
    query = {"tenant_id": user["tenant_id"]}
    if q:
        query["$or"] = [
            {"nome": {"$regex": q, "$options": "i"}},
            {"inci": {"$regex": q, "$options": "i"}},
            {"fornecedor": {"$regex": q, "$options": "i"}},
        ]
    if categoria:
        query["categoria"] = categoria
    items = await db.pd_catalog.find(query, {"_id": 0}).sort("nome", 1).to_list(1000)
    return items

@pd_router.get("/catalog/{item_id}")
async def get_catalog_item(item_id: str, request: Request):
    user = await get_current_user(request)
    item = await db.pd_catalog.find_one({"id": item_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Ingrediente não encontrado no banco de custos")
    return item

@pd_router.put("/catalog/{item_id}")
async def update_catalog_item(item_id: str, data: CatalogItemUpdate, request: Request):
    user = await get_current_user(request)
    existing = await db.pd_catalog.find_one({"id": item_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Ingrediente não encontrado")

    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Track price change history if preco changed
    if "preco_rs_kg" in update_fields and update_fields["preco_rs_kg"] != existing.get("preco_rs_kg"):
        history_entry = {
            "id": new_id(),
            "catalog_item_id": item_id,
            "preco_anterior": existing.get("preco_rs_kg", 0),
            "preco_novo": update_fields["preco_rs_kg"],
            "moeda": update_fields.get("moeda") or existing.get("moeda", "BRL"),
            "atualizado_por": user["name"],
            "atualizado_por_id": user["id"],
            "created_at": now_iso(),
        }
        await db.pd_catalog_price_history.insert_one(history_entry)

    update_fields["ultima_atualizacao"] = now_iso()
    update_fields["atualizado_por"] = user["name"]
    update_fields["atualizado_por_id"] = user["id"]
    source_changes = _build_source_changes(
        existing,
        update_fields,
        {
            "nome": "Nome tecnico",
            "inci": "INCI",
            "fornecedor": "Fornecedor homologado",
        },
        ignored_fields=["preco_rs_kg", "moeda", "unidade", "categoria", "observacoes", "ultima_atualizacao", "atualizado_por", "atualizado_por_id"],
    )

    await db.pd_catalog.update_one({"id": item_id}, {"$set": update_fields})
    item = await db.pd_catalog.find_one({"id": item_id}, {"_id": 0})
    if any(field in update_fields for field in ("nome", "inci", "fornecedor")):
        ficha_fields = ["composicao_completa"]
        epa_fields = ["bom_bulk_formula"]
        if "inci" in update_fields:
            epa_fields.append("informacoes_rotulo")
        await _auto_generate_documents_for_catalog_items(
            [item_id],
            user,
            "catalogo_mp",
            ficha_changed_fields=ficha_fields,
            epa_changed_fields=epa_fields,
            source_changes=source_changes,
        )
    return item

@pd_router.delete("/catalog/{item_id}")
async def delete_catalog_item(item_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.pd_catalog.delete_one({"id": item_id, "tenant_id": user["tenant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ingrediente não encontrado")
    # Do not delete formula items referring to catalog - just unset catalog_id
    await db.pd_formula_items.update_many({"catalog_id": item_id}, {"$set": {"catalog_id": None}})
    return {"message": "Ingrediente removido do banco de custos"}

@pd_router.get("/catalog/{item_id}/price-history")
async def catalog_price_history(item_id: str, request: Request):
    user = await get_current_user(request)
    await get_catalog_item(item_id, request)  # tenant check
    history = await db.pd_catalog_price_history.find(
        {"catalog_item_id": item_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return history


# ============ 2) PESQUISA INTERNA (INTERNAL RESEARCH) ============

@pd_router.post("/requests/internal-research")
async def create_internal_research(data: InternalResearchCreate, request: Request):
    """Cria um desenvolvimento iniciado pelo lab (sem cliente / sem CRM)"""
    user = await get_current_user(request)
    req_id = new_id()

    # Monta briefing
    briefing_parts = []
    if data.objectives:
        briefing_parts.append(f"Objetivo da Pesquisa: {data.objectives}")
    if data.description:
        briefing_parts.append(f"Descrição: {data.description}")
    if data.references:
        briefing_parts.append(f"Referências: {data.references}")
    description = "\n".join(briefing_parts) if briefing_parts else (data.description or "")

    pd_request = {
        "id": req_id,
        "tenant_id": user["tenant_id"],
        "client_card_id": None,
        "client_name": "— Pesquisa Interna —",
        "project_name": data.project_name,
        "request_type": "Pesquisa Interna",
        "category": data.category or "",
        "description": description,
        "references": data.references or "",
        "restrictions": "",
        "volume": "",
        "packaging": "",
        "priority": data.priority or "Normal",
        "deadline": data.deadline,
        "status": "IN_PROGRESS",  # start directly as in-progress
        "is_internal_research": True,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.pd_requests.insert_one(pd_request)
    pd_request.pop("_id", None)

    # Status history
    await db.pd_request_status_history.insert_one({
        "id": new_id(),
        "pd_request_id": req_id,
        "from_status": None,
        "to_status": "OPEN",
        "changed_by": user["id"],
        "changed_by_name": user["name"],
        "comment": "Pesquisa Interna iniciada pelo lab",
        "created_at": now_iso(),
    })
    await db.pd_request_status_history.insert_one({
        "id": new_id(),
        "pd_request_id": req_id,
        "from_status": "OPEN",
        "to_status": "IN_PROGRESS",
        "changed_by": user["id"],
        "changed_by_name": user["name"],
        "comment": "Auto-iniciado como Pesquisa Interna",
        "created_at": now_iso(),
    })

    # Auto-create development
    dev_id = new_id()
    await db.pd_developments.insert_one({
        "id": dev_id,
        "pd_request_id": req_id,
        "tenant_id": user["tenant_id"],
        "assigned_to": user["id"],
        "assigned_to_name": user["name"],
        "lab_responsible": user["name"],
        "current_version": 0,
        "status": "active",
        "started_at": now_iso(),
        "completed_at": None,
        "is_internal_research": True,
    })

    # Auto-create pd_card so it shows on Pipeline P&D kanban
    card_id = new_id()
    # Generate PI-XXX number
    existing_pi = await db.pd_cards.count_documents({
        "tenant_id": user["tenant_id"],
        "numero_completo": {"$regex": "^PI-"}
    })
    numero = f"PI-{(existing_pi + 1):03d}"
    await db.pd_cards.insert_one({
        "id": card_id,
        "tenant_id": user["tenant_id"],
        "tipo": "pesquisa_interna",
        "numero_completo": numero,
        "produto": data.project_name,
        "cliente": "— Pesquisa Interna —",
        "cliente_id": None,
        "descricao_aplicacao": data.objectives or data.description or "",
        "briefing_base": data.description or "",
        "observacoes_especificas": data.references or "",
        "responsavel_pd": user["name"],
        "data_solicitacao": now_iso(),
        "prazo_prometido": data.deadline,
        "status_pd": "em_desenvolvimento",  # skip "solicitado", start in dev
        "amostra_id": None,
        "amostra_variacao_id": None,
        "pd_request_id": req_id,  # NEW: link to pd_request for navigation
        "is_internal_research": True,
        "historico_movimentacoes": [{
            "de": "",
            "para": "em_desenvolvimento",
            "data": now_iso(),
            "usuario": user["name"],
            "usuario_id": user["id"],
            "observacao": "Pesquisa Interna iniciada"
        }],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })

    # Also link pd_request with pd_card_id for reverse navigation
    await db.pd_requests.update_one(
        {"id": req_id},
        {"$set": {"pd_card_id": card_id}}
    )

    pd_request["pd_card_id"] = card_id
    return pd_request


# ============ 3) ESTOQUE DO LAB (STOCK) ============

VALID_STOCK_CATEGORIES = ["mp", "insumo", "amostra_acabada"]

@pd_router.post("/stock")
async def create_stock_item(data: StockItemCreate, request: Request):
    user = await get_current_user(request)
    if data.categoria not in VALID_STOCK_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Categoria inválida. Use: {VALID_STOCK_CATEGORIES}")

    item_id = new_id()
    item = {
        "id": item_id,
        "tenant_id": user["tenant_id"],
        "categoria": data.categoria,
        "nome": data.nome.strip(),
        "codigo_interno": (data.codigo_interno or "").strip(),
        "unidade_medida": data.unidade_medida or "kg",
        "quantidade_atual": float(data.quantidade_atual or 0),
        "quantidade_minima": float(data.quantidade_minima or 0),
        "lote": (data.lote or "").strip(),
        "validade": data.validade,
        "localizacao": (data.localizacao or "").strip(),
        "custo_unitario": float(data.custo_unitario or 0),
        "fornecedor": (data.fornecedor or "").strip(),
        "observacoes": (data.observacoes or "").strip(),
        "catalog_id": data.catalog_id,
        "formula_ref": (data.formula_ref or "").strip(),
        "fragrancia_percentual": data.fragrancia_percentual,
        "linked_pd_request_id": data.linked_pd_request_id,
        "linked_formula_id": data.linked_formula_id,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.pd_stock_items.insert_one(item)
    item.pop("_id", None)

    # Initial movement (entrada) if quantity > 0
    if item["quantidade_atual"] > 0:
        await db.pd_stock_movements.insert_one({
            "id": new_id(),
            "tenant_id": user["tenant_id"],
            "stock_item_id": item_id,
            "tipo": "entrada",
            "quantidade": item["quantidade_atual"],
            "quantidade_antes": 0.0,
            "quantidade_depois": item["quantidade_atual"],
            "motivo": "Estoque inicial",
            "lote": item.get("lote") or None,
            "user_id": user["id"],
            "user_name": user["name"],
            "created_at": now_iso(),
        })

    return item

@pd_router.get("/stock")
async def list_stock(request: Request, categoria: Optional[str] = None, q: Optional[str] = None, low_stock: bool = False):
    user = await get_current_user(request)
    query = {"tenant_id": user["tenant_id"]}
    if categoria:
        query["categoria"] = categoria
    if q:
        query["$or"] = [
            {"nome": {"$regex": q, "$options": "i"}},
            {"codigo_interno": {"$regex": q, "$options": "i"}},
            {"formula_ref": {"$regex": q, "$options": "i"}},
        ]
    items = await db.pd_stock_items.find(query, {"_id": 0}).sort("nome", 1).to_list(2000)
    if low_stock:
        items = [it for it in items if it.get("quantidade_atual", 0) <= it.get("quantidade_minima", 0) and it.get("quantidade_minima", 0) > 0]
    return items

@pd_router.get("/stock/alerts")
async def stock_alerts(request: Request):
    """Items below minimum stock or expiring soon"""
    user = await get_current_user(request)
    items = await db.pd_stock_items.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).to_list(5000)
    low_stock = []
    expiring = []
    now_dt = datetime.now(timezone.utc)
    soon = now_dt + timedelta(days=30)
    for it in items:
        qa = it.get("quantidade_atual", 0) or 0
        qm = it.get("quantidade_minima", 0) or 0
        if qm > 0 and qa <= qm:
            low_stock.append(it)
        val = it.get("validade")
        if val:
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00")) if isinstance(val, str) else val
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt <= soon:
                    expiring.append(it)
            except Exception:
                pass
    return {"low_stock": low_stock, "expiring": expiring}

@pd_router.get("/stock/{item_id}")
async def get_stock_item(item_id: str, request: Request):
    user = await get_current_user(request)
    item = await db.pd_stock_items.find_one({"id": item_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    return item

@pd_router.put("/stock/{item_id}")
async def update_stock_item(item_id: str, data: StockItemUpdate, request: Request):
    user = await get_current_user(request)
    existing = await db.pd_stock_items.find_one({"id": item_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    update_fields["updated_at"] = now_iso()
    await db.pd_stock_items.update_one({"id": item_id}, {"$set": update_fields})
    item = await db.pd_stock_items.find_one({"id": item_id}, {"_id": 0})
    return item

@pd_router.delete("/stock/{item_id}")
async def delete_stock_item(item_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.pd_stock_items.delete_one({"id": item_id, "tenant_id": user["tenant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    await db.pd_stock_movements.delete_many({"stock_item_id": item_id})
    return {"message": "Item removido"}

@pd_router.post("/stock/{item_id}/movements")
async def create_stock_movement(item_id: str, data: StockMovementCreate, request: Request):
    user = await get_current_user(request)
    item = await db.pd_stock_items.find_one({"id": item_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    if data.tipo not in ["entrada", "saida", "ajuste"]:
        raise HTTPException(status_code=400, detail="Tipo deve ser entrada, saida ou ajuste")
    if data.quantidade is None or data.quantidade < 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser positiva")

    current = float(item.get("quantidade_atual", 0) or 0)
    qty = float(data.quantidade)

    if data.tipo == "entrada":
        new_qty = current + qty
    elif data.tipo == "saida":
        if qty > current:
            raise HTTPException(status_code=400, detail=f"Saída de {qty} maior que estoque atual ({current})")
        new_qty = current - qty
    else:  # ajuste: set absolute qty
        new_qty = qty

    move_id = new_id()
    movement = {
        "id": move_id,
        "tenant_id": user["tenant_id"],
        "stock_item_id": item_id,
        "tipo": data.tipo,
        "quantidade": qty,
        "quantidade_antes": current,
        "quantidade_depois": new_qty,
        "motivo": data.motivo or "",
        "lote": data.lote or item.get("lote") or None,
        "linked_dev_id": data.linked_dev_id,
        "linked_pd_request_id": data.linked_pd_request_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "created_at": now_iso(),
    }
    await db.pd_stock_movements.insert_one(movement)
    movement.pop("_id", None)

    await db.pd_stock_items.update_one(
        {"id": item_id},
        {"$set": {"quantidade_atual": new_qty, "updated_at": now_iso()}}
    )

    return movement

@pd_router.get("/stock/{item_id}/movements")
async def list_stock_movements(item_id: str, request: Request):
    user = await get_current_user(request)
    await get_stock_item(item_id, request)
    movements = await db.pd_stock_movements.find(
        {"stock_item_id": item_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return movements


# ============ 4) ATUALIZAÇÕES DA AMOSTRA (UPDATES + PENDING) ============

@pd_router.post("/requests/{req_id}/updates")
async def create_update(req_id: str, data: UpdateCreate, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    up_id = new_id()
    upd = {
        "id": up_id,
        "pd_request_id": req_id,
        "tenant_id": user["tenant_id"],
        "tipo": data.tipo or "observacao",
        "mensagem": data.mensagem.strip(),
        "visivel_comercial": bool(data.visivel_comercial),
        "user_id": user["id"],
        "user_name": user["name"],
        "user_role": user.get("role", ""),
        "created_at": now_iso(),
    }
    await db.pd_updates.insert_one(upd)
    upd.pop("_id", None)
    return upd

@pd_router.get("/requests/{req_id}/updates")
async def list_updates(req_id: str, request: Request):
    user = await get_current_user(request)
    updates = await db.pd_updates.find(
        {"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return updates

@pd_router.delete("/updates/{up_id}")
async def delete_update(up_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.pd_updates.delete_one({"id": up_id, "tenant_id": user["tenant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Atualização não encontrada")
    return {"message": "Atualização removida"}

# Pending items (aguardando fragrância/MP/insumo etc)

@pd_router.post("/requests/{req_id}/pending")
async def create_pending(req_id: str, data: PendingItemCreate, request: Request):
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    p_id = new_id()
    pending = {
        "id": p_id,
        "pd_request_id": req_id,
        "tenant_id": user["tenant_id"],
        "tipo": data.tipo,
        "descricao": data.descricao.strip(),
        "data_solicitacao": now_iso(),
        "data_prevista": data.data_prevista,
        "data_recebido": None,
        "fornecedor": (data.fornecedor or "").strip(),
        "observacoes": (data.observacoes or "").strip(),
        "status": "pendente",  # pendente, recebido, atrasado, cancelado
        "user_id": user["id"],
        "user_name": user["name"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.pd_pending_items.insert_one(pending)
    pending.pop("_id", None)

    # Also log as update (visible to commercial)
    await db.pd_updates.insert_one({
        "id": new_id(),
        "pd_request_id": req_id,
        "tenant_id": user["tenant_id"],
        "tipo": "pendencia_criada",
        "mensagem": f"Solicitado(a) {data.tipo}: {data.descricao}" + (f" — previsão {data.data_prevista}" if data.data_prevista else ""),
        "visivel_comercial": True,
        "user_id": user["id"],
        "user_name": user["name"],
        "user_role": user.get("role", ""),
        "pending_item_id": p_id,
        "created_at": now_iso(),
    })
    return pending

@pd_router.get("/requests/{req_id}/pending")
async def list_pending(req_id: str, request: Request, status: Optional[str] = None):
    user = await get_current_user(request)
    query = {"pd_request_id": req_id, "tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    items = await db.pd_pending_items.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    # Calculate if atrasado
    now_dt = datetime.now(timezone.utc)
    for it in items:
        if it["status"] == "pendente" and it.get("data_prevista"):
            try:
                dp = datetime.fromisoformat(it["data_prevista"].replace("Z", "+00:00")) if isinstance(it["data_prevista"], str) else it["data_prevista"]
                if dp.tzinfo is None:
                    dp = dp.replace(tzinfo=timezone.utc)
                if dp < now_dt:
                    it["status_calc"] = "atrasado"
                else:
                    it["status_calc"] = "pendente"
            except Exception:
                it["status_calc"] = "pendente"
        else:
            it["status_calc"] = it["status"]
    return items

@pd_router.put("/pending/{p_id}")
async def update_pending(p_id: str, data: PendingItemUpdate, request: Request):
    user = await get_current_user(request)
    existing = await db.pd_pending_items.find_one({"id": p_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    # Mark recebido date
    if update_fields.get("status") == "recebido" and existing.get("status") != "recebido":
        update_fields["data_recebido"] = now_iso()
        # Log as update
        await db.pd_updates.insert_one({
            "id": new_id(),
            "pd_request_id": existing["pd_request_id"],
            "tenant_id": user["tenant_id"],
            "tipo": "pendencia_resolvida",
            "mensagem": f"Recebido(a): {existing['descricao']}",
            "visivel_comercial": True,
            "user_id": user["id"],
            "user_name": user["name"],
            "user_role": user.get("role", ""),
            "pending_item_id": p_id,
            "created_at": now_iso(),
        })
    update_fields["updated_at"] = now_iso()
    await db.pd_pending_items.update_one({"id": p_id}, {"$set": update_fields})
    it = await db.pd_pending_items.find_one({"id": p_id}, {"_id": 0})
    return it

@pd_router.delete("/pending/{p_id}")
async def delete_pending(p_id: str, request: Request):
    user = await get_current_user(request)
    result = await db.pd_pending_items.delete_one({"id": p_id, "tenant_id": user["tenant_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")
    return {"message": "Pendência removida"}

# ------ CRM-facing view: aggregate pending + updates by pd_request ------

@pd_router.get("/requests/{req_id}/activity")
async def get_activity_for_crm(req_id: str, request: Request):
    """Endpoint que o CRM comercial usa para ver o que o lab está fazendo.
    Retorna updates visíveis + pendências."""
    user = await get_current_user(request)
    pd_req = await db.pd_requests.find_one({"id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not pd_req:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    updates = await db.pd_updates.find(
        {"pd_request_id": req_id, "tenant_id": user["tenant_id"], "visivel_comercial": True}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    pending = await db.pd_pending_items.find(
        {"pd_request_id": req_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    # Calculate atrasado
    now_dt = datetime.now(timezone.utc)
    for it in pending:
        if it["status"] == "pendente" and it.get("data_prevista"):
            try:
                dp = datetime.fromisoformat(it["data_prevista"].replace("Z", "+00:00")) if isinstance(it["data_prevista"], str) else it["data_prevista"]
                if dp.tzinfo is None:
                    dp = dp.replace(tzinfo=timezone.utc)
                it["status_calc"] = "atrasado" if dp < now_dt else "pendente"
            except Exception:
                it["status_calc"] = "pendente"
        else:
            it["status_calc"] = it["status"]
    return {"updates": updates, "pending": pending}


# ============ HELPER: list all internal research requests for Pipeline P&D view ============

@pd_router.get("/requests/internal-research/list")
async def list_internal_research(request: Request):
    user = await get_current_user(request)
    items = await db.pd_requests.find(
        {"tenant_id": user["tenant_id"], "is_internal_research": True}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return items



# =========================================================================
#  HOMOLOGAÇÕES — MPs e FORNECEDORES
# =========================================================================


# ----- HELPERS: Bloqueio de formulas com insumos nao homologados/suspensos ----

async def _evaluate_formula_homologacao(formula_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Inspeciona todos os itens de uma formula e classifica o status de homologacao
    de cada MP usada (via catalog -> homologacao_mps por nome+inci).
    Retorna estrutura: {ok: bool, blocked: [..], pending: [..], total_items: int, summary: str}
    """
    items = await db.pd_formula_items.find({"formula_id": formula_id}, {"_id": 0}).to_list(2000)
    if not items:
        return {"ok": True, "blocked": [], "pending": [], "total_items": 0, "summary": "Formula sem itens"}

    catalog_ids = [it["catalog_id"] for it in items if it.get("catalog_id")]
    catalogs: Dict[str, Dict[str, Any]] = {}
    if catalog_ids:
        docs = await db.pd_catalog.find(
            {"tenant_id": tenant_id, "id": {"$in": catalog_ids}}, {"_id": 0}
        ).to_list(2000)
        catalogs = {d["id"]: d for d in docs if d.get("id")}

    mp_index: Dict[str, Dict[str, Any]] = {}
    mps = await db.homologacao_mps.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(5000)
    for mp in mps:
        for key in (mp.get("nome", ""), mp.get("inci", ""), mp.get("codigo_interno", "")):
            normalized = (key or "").strip().lower()
            if normalized:
                mp_index.setdefault(normalized, mp)

    blocked: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []

    for item in items:
        ingredient = (item.get("ingredient_name") or "").strip()
        catalog = catalogs.get(item.get("catalog_id")) or {}
        candidate_keys = [
            (catalog.get("nome") or "").strip().lower(),
            (catalog.get("inci") or "").strip().lower(),
            ingredient.lower(),
        ]
        mp_doc = next((mp_index[k] for k in candidate_keys if k and k in mp_index), None)
        if not mp_doc:
            pending.append({
                "ingredient_name": ingredient or catalog.get("nome", ""),
                "reason": "MP nao cadastrada em Homologacoes",
                "status": "ausente",
            })
            continue
        status = mp_doc.get("status", "pendente")
        if status in MP_BLOCKED_STATUSES:
            blocked.append({
                "ingredient_name": ingredient or mp_doc.get("nome", ""),
                "mp_id": mp_doc.get("id"),
                "fornecedor_nome": mp_doc.get("fornecedor_nome", ""),
                "status": status,
                "parecer": mp_doc.get("parecer_homologacao", ""),
            })
        elif status not in MP_OK_STATUSES:
            pending.append({
                "ingredient_name": ingredient or mp_doc.get("nome", ""),
                "mp_id": mp_doc.get("id"),
                "fornecedor_nome": mp_doc.get("fornecedor_nome", ""),
                "status": status,
                "reason": "MP em avaliacao",
            })

    summary = f"{len(blocked)} bloqueadas, {len(pending)} pendentes, {len(items)} itens"
    return {
        "ok": len(blocked) == 0,
        "blocked": blocked,
        "pending": pending,
        "total_items": len(items),
        "summary": summary,
    }


async def assert_formula_homologacao_ok(formula_id: str, tenant_id: str, *, allow_pending: bool = True):
    """Raises 409 if formula has insumos reprovados/suspensos. Pending only blocks if allow_pending=False."""
    result = await _evaluate_formula_homologacao(formula_id, tenant_id)
    if result["blocked"]:
        names = ", ".join(item["ingredient_name"] for item in result["blocked"][:5])
        raise HTTPException(
            status_code=409,
            detail=f"Formula bloqueada: {len(result['blocked'])} insumo(s) reprovado(s)/suspenso(s) na Homologacao: {names}",
        )
    if not allow_pending and result["pending"]:
        names = ", ".join(item["ingredient_name"] for item in result["pending"][:5])
        raise HTTPException(
            status_code=409,
            detail=f"Formula bloqueada: {len(result['pending'])} insumo(s) sem homologacao concluida: {names}",
        )


async def assert_pd_card_ready_for_approval(card_id: str, tenant_id: str):
    """Antes de mover para aguardando_aprovacao/aprovado, validar todas as formulas ativas vinculadas."""
    card = await db.pd_cards.find_one({"id": card_id, "tenant_id": tenant_id}, {"_id": 0, "amostra_variacao_id": 1, "amostra_id": 1})
    if not card:
        return
    pd_request = await db.pd_requests.find_one(
        {"tenant_id": tenant_id, "amostra_id": card.get("amostra_id")},
        {"_id": 0, "id": 1},
    )
    if not pd_request:
        return
    dev = await db.pd_developments.find_one(
        {"tenant_id": tenant_id, "pd_request_id": pd_request["id"]},
        {"_id": 0, "id": 1},
    )
    if not dev:
        return
    latest = await db.pd_formulas.find_one(
        {"development_id": dev["id"]},
        {"_id": 0, "id": 1},
        sort=[("version", -1)],
    )
    if not latest:
        return
    await assert_formula_homologacao_ok(latest["id"], tenant_id, allow_pending=True)


@pd_router.get("/formulas/{formula_id}/homologacao-status")
async def formula_homologacao_status(formula_id: str, request: Request):
    """Retorna o status de homologacao agregado para uma formula (bloqueada/pending/ok)."""
    user = await get_current_user(request)
    require_roles(user, PD_READ)
    return await _evaluate_formula_homologacao(formula_id, user["tenant_id"])


# =========================================================================
#  HOMOLOGAÇÕES — MPs e FORNECEDORES (continued)
# =========================================================================

class FornecedorHomologacao(BaseModel):
    razao_social: str
    cnpj: str = ""
    nome_fantasia: str = ""
    contato_nome: str = ""
    contato_email: str = ""
    contato_telefone: str = ""
    endereco: str = ""
    categoria: str = ""  # MP_FORMULACAO, MP_ROTULO, MP_EMBALAGEM, SERVICO, etc
    observacoes: str = ""


class FornecedorUpdate(BaseModel):
    razao_social: Optional[str] = None
    cnpj: Optional[str] = None
    nome_fantasia: Optional[str] = None
    contato_nome: Optional[str] = None
    contato_email: Optional[str] = None
    contato_telefone: Optional[str] = None
    endereco: Optional[str] = None
    categoria: Optional[str] = None
    observacoes: Optional[str] = None


class MPHomologacao(BaseModel):
    nome: str
    codigo_interno: str = ""
    inci: str = ""
    tipo_mp: str  # FORMULACAO, ROTULO, EMBALAGEM
    fornecedor_id: Optional[str] = None
    fornecedor_nome: str = ""  # snapshot se fornecedor não está cadastrado ainda
    funcao: str = ""            # Ex: emulsificante, conservante, ativo
    custo_referencia: Optional[float] = None
    unidade: str = "kg"
    especificacoes_tecnicas: str = ""
    certificados: List[str] = []   # URLs/IDs de laudos/COAs
    msds_url: str = ""
    validade_laudo: Optional[str] = None
    observacoes: str = ""


class MPUpdate(BaseModel):
    nome: Optional[str] = None
    codigo_interno: Optional[str] = None
    inci: Optional[str] = None
    tipo_mp: Optional[str] = None
    fornecedor_id: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    funcao: Optional[str] = None
    custo_referencia: Optional[float] = None
    unidade: Optional[str] = None
    especificacoes_tecnicas: Optional[str] = None
    certificados: Optional[List[str]] = None
    msds_url: Optional[str] = None
    validade_laudo: Optional[str] = None
    observacoes: Optional[str] = None


class HomologarRequest(BaseModel):
    aprovado: bool
    parecer: str = ""


class SuspenderRequest(BaseModel):
    parecer: str = ""


def _serialize_doc(doc):
    if doc:
        doc.pop("_id", None)
    return doc


# ----- FORNECEDORES -----

@pd_router.post("/homologacao/fornecedores")
async def create_fornecedor(data: FornecedorHomologacao, request: Request):
    user = await get_current_user(request)
    require_roles(user, HOMOLOGACAO_WRITE)
    now = now_iso()
    f_id = new_id()
    payload = _validate_supplier_payload(data.model_dump())
    doc = {
        "id": f_id,
        "tenant_id": user["tenant_id"],
        **payload,
        "status": "pendente",  # pendente | homologado | rejeitado
        "parecer_homologacao": "",
        "homologado_por": "",
        "homologado_por_id": "",
        "data_homologacao": None,
        "historico": [{
            "evento": "criado",
            "por": user["name"],
            "por_id": user["id"],
            "data": now,
        }],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.homologacao_fornecedores.insert_one(doc)
    return _serialize_doc(doc)


@pd_router.get("/homologacao/fornecedores")
async def list_fornecedores(request: Request, status: Optional[str] = None, search: Optional[str] = None):
    user = await get_current_user(request)
    q = {"tenant_id": user["tenant_id"]}
    if status:
        q["status"] = status
    if search:
        q["$or"] = [
            {"razao_social": {"$regex": search, "$options": "i"}},
            {"nome_fantasia": {"$regex": search, "$options": "i"}},
            {"cnpj": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.homologacao_fornecedores.find(q, {"_id": 0}).sort("razao_social", 1).to_list(5000)
    return docs


@pd_router.get("/homologacao/fornecedores/{f_id}")
async def get_fornecedor(f_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.homologacao_fornecedores.find_one({"id": f_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    return doc


@pd_router.put("/homologacao/fornecedores/{f_id}")
async def update_fornecedor(f_id: str, data: FornecedorUpdate, request: Request):
    user = await get_current_user(request)
    existing = await db.homologacao_fornecedores.find_one({"id": f_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Fornecedor nÃ£o encontrado")
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    payload = dict(existing)
    payload.update(fields)
    payload = _validate_supplier_payload(payload)
    for field in ("razao_social", "cnpj", "cnpj_normalized", "nome_fantasia", "contato_nome", "contato_email", "contato_telefone"):
        fields[field] = payload[field]
    fields["updated_at"] = now_iso()
    result = await db.homologacao_fornecedores.update_one(
        {"id": f_id, "tenant_id": user["tenant_id"]},
        {"$set": fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    return await db.homologacao_fornecedores.find_one({"id": f_id}, {"_id": 0})


@pd_router.post("/homologacao/fornecedores/{f_id}/homologar")
async def homologar_fornecedor(f_id: str, data: HomologarRequest, request: Request):
    user = await get_current_user(request)
    require_roles(user, HOMOLOGACAO_APPROVE)
    now = now_iso()
    novo_status = "homologado" if data.aprovado else "rejeitado"
    update = {
        "status": novo_status,
        "parecer_homologacao": data.parecer,
        "homologado_por": user["name"],
        "homologado_por_id": user["id"],
        "data_homologacao": now,
        "updated_at": now,
    }
    evento = {
        "evento": "homologado" if data.aprovado else "rejeitado",
        "por": user["name"],
        "por_id": user["id"],
        "data": now,
        "parecer": data.parecer,
    }
    result = await db.homologacao_fornecedores.update_one(
        {"id": f_id, "tenant_id": user["tenant_id"]},
        {"$set": update, "$push": {"historico": evento}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    return await db.homologacao_fornecedores.find_one({"id": f_id}, {"_id": 0})


@pd_router.delete("/homologacao/fornecedores/{f_id}")
async def delete_fornecedor(f_id: str, request: Request):
    user = await get_current_user(request)
    # Bloquear se tem MP vinculada
    mp_count = await db.homologacao_mps.count_documents({"fornecedor_id": f_id, "tenant_id": user["tenant_id"]})
    if mp_count > 0:
        raise HTTPException(status_code=400, detail=f"Fornecedor tem {mp_count} MP(s) vinculada(s). Remova as MPs primeiro.")
    await db.homologacao_fornecedores.delete_one({"id": f_id, "tenant_id": user["tenant_id"]})
    return {"deleted": f_id}


# ----- MPs -----

@pd_router.post("/homologacao/mps")
async def create_mp(data: MPHomologacao, request: Request):
    user = await get_current_user(request)
    require_roles(user, HOMOLOGACAO_WRITE)
    if data.tipo_mp not in ["FORMULACAO", "ROTULO", "EMBALAGEM"]:
        raise HTTPException(status_code=400, detail="tipo_mp inválido (FORMULACAO|ROTULO|EMBALAGEM)")
    now = now_iso()
    mp_id = new_id()

    # Se fornecedor_id fornecido, buscar o nome
    fornecedor_nome = data.fornecedor_nome
    if data.fornecedor_id:
        forn = await db.homologacao_fornecedores.find_one(
            {"id": data.fornecedor_id, "tenant_id": user["tenant_id"]}, {"_id": 0, "razao_social": 1, "nome_fantasia": 1}
        )
        if forn:
            fornecedor_nome = forn.get("nome_fantasia") or forn.get("razao_social") or fornecedor_nome

    doc = {
        "id": mp_id,
        "tenant_id": user["tenant_id"],
        **data.model_dump(),
        "fornecedor_nome": fornecedor_nome,
        "status": "pendente",  # pendente | homologada | rejeitada
        "parecer_homologacao": "",
        "homologado_por": "",
        "homologado_por_id": "",
        "data_homologacao": None,
        "historico": [{
            "evento": "criado",
            "por": user["name"],
            "por_id": user["id"],
            "data": now,
        }],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.homologacao_mps.insert_one(doc)
    return _serialize_doc(doc)


@pd_router.get("/homologacao/mps")
async def list_mps(
    request: Request,
    status: Optional[str] = None,
    tipo_mp: Optional[str] = None,
    fornecedor_id: Optional[str] = None,
    search: Optional[str] = None,
):
    user = await get_current_user(request)
    q = {"tenant_id": user["tenant_id"]}
    if status:
        q["status"] = status
    if tipo_mp:
        q["tipo_mp"] = tipo_mp
    if fornecedor_id:
        q["fornecedor_id"] = fornecedor_id
    if search:
        q["$or"] = [
            {"nome": {"$regex": search, "$options": "i"}},
            {"codigo_interno": {"$regex": search, "$options": "i"}},
            {"inci": {"$regex": search, "$options": "i"}},
            {"fornecedor_nome": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.homologacao_mps.find(q, {"_id": 0}).sort("nome", 1).to_list(5000)
    return docs


@pd_router.get("/homologacao/mps/{mp_id}")
async def get_mp(mp_id: str, request: Request):
    user = await get_current_user(request)
    doc = await db.homologacao_mps.find_one({"id": mp_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="MP não encontrada")
    return doc


@pd_router.put("/homologacao/mps/{mp_id}")
async def update_mp(mp_id: str, data: MPUpdate, request: Request):
    user = await get_current_user(request)
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    fields["updated_at"] = now_iso()
    result = await db.homologacao_mps.update_one(
        {"id": mp_id, "tenant_id": user["tenant_id"]},
        {"$set": fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="MP não encontrada")
    mp_doc = await db.homologacao_mps.find_one({"id": mp_id}, {"_id": 0})
    catalog_docs = await db.pd_catalog.find(
        {
            "tenant_id": user["tenant_id"],
            "$or": [{"nome": mp_doc.get("nome", "")}, {"inci": mp_doc.get("inci", "")}],
        },
        {"_id": 0, "id": 1}
    ).to_list(100)
    if catalog_docs:
        await _auto_generate_documents_for_catalog_items(
            [doc["id"] for doc in catalog_docs if doc.get("id")],
            user,
            "homologacao_mp",
            ficha_changed_fields=["composicao_completa"],
            epa_changed_fields=["bom_bulk_formula", "informacoes_rotulo"],
            source_changes=[{
                "field": "mp_homologacao",
                "label": "Fornecedor homologado",
                "before": None,
                "after": {
                    "nome": mp_doc.get("nome"),
                    "fornecedor_nome": mp_doc.get("fornecedor_nome"),
                    "status": mp_doc.get("status"),
                },
            }],
        )
    return mp_doc


@pd_router.post("/homologacao/mps/{mp_id}/homologar")
async def homologar_mp(mp_id: str, data: HomologarRequest, request: Request):
    user = await get_current_user(request)
    require_roles(user, HOMOLOGACAO_APPROVE)
    now = now_iso()

    # Validar: MP só pode ser homologada se fornecedor vinculado está homologado
    mp = await db.homologacao_mps.find_one({"id": mp_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not mp:
        raise HTTPException(status_code=404, detail="MP não encontrada")

    if data.aprovado and mp.get("fornecedor_id"):
        forn = await db.homologacao_fornecedores.find_one(
            {"id": mp["fornecedor_id"], "tenant_id": user["tenant_id"]}, {"_id": 0, "status": 1}
        )
        if forn and forn.get("status") != "homologado":
            raise HTTPException(
                status_code=400,
                detail="Fornecedor vinculado não está homologado. Homologue o fornecedor antes da MP."
            )

    novo_status = "homologada" if data.aprovado else "rejeitada"
    update = {
        "status": novo_status,
        "parecer_homologacao": data.parecer,
        "homologado_por": user["name"],
        "homologado_por_id": user["id"],
        "data_homologacao": now,
        "updated_at": now,
    }
    evento = {
        "evento": "homologada" if data.aprovado else "rejeitada",
        "por": user["name"],
        "por_id": user["id"],
        "data": now,
        "parecer": data.parecer,
    }
    await db.homologacao_mps.update_one(
        {"id": mp_id, "tenant_id": user["tenant_id"]},
        {"$set": update, "$push": {"historico": evento}}
    )
    return await db.homologacao_mps.find_one({"id": mp_id}, {"_id": 0})


@pd_router.post("/homologacao/mps/{mp_id}/suspender")
async def suspender_mp(mp_id: str, data: SuspenderRequest, request: Request):
    """Suspende uma MP (status `suspensa`). Bloqueia formulas que a usam ate revisao."""
    user = await get_current_user(request)
    require_roles(user, HOMOLOGACAO_APPROVE)
    now = now_iso()
    mp = await db.homologacao_mps.find_one({"id": mp_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not mp:
        raise HTTPException(status_code=404, detail="MP nao encontrada")
    update = {
        "status": "suspensa",
        "parecer_homologacao": data.parecer,
        "homologado_por": user["name"],
        "homologado_por_id": user["id"],
        "data_homologacao": now,
        "updated_at": now,
    }
    evento = {
        "evento": "suspensa",
        "por": user["name"],
        "por_id": user["id"],
        "data": now,
        "parecer": data.parecer,
    }
    await db.homologacao_mps.update_one(
        {"id": mp_id, "tenant_id": user["tenant_id"]},
        {"$set": update, "$push": {"historico": evento}}
    )
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user["name"],
        action="mp_suspensa",
        entity_type="homologacao_mp",
        entity_id=mp_id,
        before={"status": mp.get("status")},
        after={"status": "suspensa", "parecer": data.parecer},
    )
    return await db.homologacao_mps.find_one({"id": mp_id}, {"_id": 0})


@pd_router.post("/homologacao/mps/{mp_id}/reativar")
async def reativar_mp(mp_id: str, data: SuspenderRequest, request: Request):
    """Reativa uma MP suspensa, retornando para 'pendente' (precisa nova homologacao)."""
    user = await get_current_user(request)
    require_roles(user, HOMOLOGACAO_APPROVE)
    now = now_iso()
    mp = await db.homologacao_mps.find_one({"id": mp_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not mp:
        raise HTTPException(status_code=404, detail="MP nao encontrada")
    if mp.get("status") != "suspensa":
        raise HTTPException(status_code=400, detail="MP nao esta suspensa")
    update = {
        "status": "pendente",
        "parecer_homologacao": data.parecer,
        "data_homologacao": None,
        "updated_at": now,
    }
    evento = {
        "evento": "reativada",
        "por": user["name"],
        "por_id": user["id"],
        "data": now,
        "parecer": data.parecer,
    }
    await db.homologacao_mps.update_one(
        {"id": mp_id, "tenant_id": user["tenant_id"]},
        {"$set": update, "$push": {"historico": evento}}
    )
    return await db.homologacao_mps.find_one({"id": mp_id}, {"_id": 0})


@pd_router.delete("/homologacao/mps/{mp_id}")
async def delete_mp(mp_id: str, request: Request):
    user = await get_current_user(request)
    # Bloquear se tem item de estoque vinculado
    est_count = await db.estoque_items.count_documents({"mp_id": mp_id, "tenant_id": user["tenant_id"]})
    if est_count > 0:
        raise HTTPException(status_code=400, detail=f"MP tem {est_count} item(ns) no estoque. Remova do estoque antes.")
    await db.homologacao_mps.delete_one({"id": mp_id, "tenant_id": user["tenant_id"]})
    return {"deleted": mp_id}


@pd_router.get("/homologacao/dashboard")
async def homologacao_dashboard(request: Request):
    user = await get_current_user(request)
    require_roles(user, PD_READ)
    t_id = user["tenant_id"]
    mps_all = await db.homologacao_mps.find({"tenant_id": t_id}, {"_id": 0}).to_list(10000)
    forn_all = await db.homologacao_fornecedores.find({"tenant_id": t_id}, {"_id": 0}).to_list(10000)

    def count_by(lst, key):
        r = {}
        for i in lst:
            v = i.get(key, "")
            r[v] = r.get(v, 0) + 1
        return r

    # Agrupa MPs homologadas por nome para detectar fornecedor unico
    mps_homologadas_por_nome: Dict[str, set] = {}
    for mp in mps_all:
        if mp.get("status") != "homologada":
            continue
        key = (mp.get("nome") or "").strip().lower()
        if not key:
            continue
        mps_homologadas_por_nome.setdefault(key, set()).add(
            mp.get("fornecedor_id") or mp.get("fornecedor_nome") or mp.get("id")
        )

    fornecedor_unico_alerts: List[Dict[str, Any]] = []
    risco_baixo_alerts: List[Dict[str, Any]] = []
    for nome_key, fornecedores in mps_homologadas_por_nome.items():
        nome_display = next(
            (mp.get("nome") for mp in mps_all if (mp.get("nome") or "").strip().lower() == nome_key),
            nome_key,
        )
        if len(fornecedores) <= 1:
            fornecedor_unico_alerts.append({
                "nome": nome_display,
                "fornecedores": list(fornecedores),
                "total_fornecedores": len(fornecedores),
            })
        elif len(fornecedores) < 3:
            risco_baixo_alerts.append({
                "nome": nome_display,
                "fornecedores": list(fornecedores),
                "total_fornecedores": len(fornecedores),
            })

    # MPs com status que bloqueiam producao
    mps_bloqueadas = [mp for mp in mps_all if mp.get("status") in MP_BLOCKED_STATUSES]

    return {
        "mps": {
            "total": len(mps_all),
            "por_status": count_by(mps_all, "status"),
            "por_tipo": count_by(mps_all, "tipo_mp"),
            "bloqueadas_total": len(mps_bloqueadas),
        },
        "fornecedores": {
            "total": len(forn_all),
            "por_status": count_by(forn_all, "status"),
            "por_categoria": count_by(forn_all, "categoria"),
        },
        "alertas": {
            "fornecedor_unico": fornecedor_unico_alerts,
            "risco_fornecimento": risco_baixo_alerts,
            "mps_bloqueadas": [
                {"id": mp.get("id"), "nome": mp.get("nome"), "status": mp.get("status"), "fornecedor_nome": mp.get("fornecedor_nome", "")}
                for mp in mps_bloqueadas[:50]
            ],
        },
    }
