from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import csv
import io

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import database as pg_db
from rbac import require_roles, has_role
from workflow_engine import audit_log, create_workflow_task, next_sequence


kickoff_router = APIRouter(prefix="/api")

get_current_user = None
new_id_func = None
now_iso_func = None


def init_kickoff(database, auth_func, id_func, iso_func):
    global get_current_user, new_id_func, now_iso_func
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id() -> str:
    return new_id_func()


def now_iso() -> str:
    return now_iso_func()


def _row(r):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} if r else None


KICKOFF_STATUSES = {
    "em_preenchimento",
    "aguardando_aprovacao",
    "aprovado",
    "em_revisao",
    "substituida",
    "arquivado",
}

APPROVAL_SEQUENCE = ["lider_pd", "cq", "eng_produto", "direcao"]
APPROVAL_ROLE_MAP = {
    "lider_pd": {"admin", "lider_pd"},
    "cq": {"admin", "qa"},
    "eng_produto": {"admin", "engenharia_produto"},
    "direcao": {"admin"},
}
APPROVAL_LABELS = {
    "lider_pd": "Lider P&D",
    "cq": "CQ",
    "eng_produto": "Engenharia de Produto",
    "direcao": "Direcao",
}
BLOCK_2_ROLES = {"admin", "vendedor", "sales_ops"}
BLOCK_3_ROLES = {"admin", "formulador", "lider_pd"}
BLOCK_4_ROLES = {"admin", "engenharia_produto"}


EMPRESA_KURYOS = {
    "razao_social": "KURYOS BEAUTY PACKING INDUSTRIAL LTDA",
    "cnpj": "00.767.554/0001-19",
    "endereco": "Rua Lagoa Tai Grande, 1130, Sao Paulo/SP, CEP 08290-425",
    "anvisa": "355030801-206-000078-1-1",
    "foro": "Comarca de Sao Paulo/SP",
}


class KickoffCreateInput(BaseModel):
    projeto_id: str
    formula_id: Optional[str] = None


class KickoffBloco2Input(BaseModel):
    volume_primeiro_pedido: Optional[int] = None
    volume_estimado_mes: Optional[int] = None
    unidade_venda: Optional[str] = None
    quantidade_por_caixa: Optional[int] = None
    data_entrega_contratada: Optional[str] = None
    lead_time_producao_dias_uteis: Optional[int] = None
    prazo_validade_produto_meses: Optional[int] = None
    preco_venda_cliente_rs_un: Optional[float] = None
    condicao_pagamento: Optional[str] = None
    condicao_pagamento_outro: Optional[str] = None
    incoterm: Optional[str] = None
    endereco_entrega: Optional[str] = None
    nota_fiscal_cfop: Optional[str] = None
    contrato_assinado_file_id: Optional[str] = None
    contrato_assinado_data: Optional[str] = None
    numero_pedido_cliente: Optional[str] = None
    observacoes_comerciais: Optional[str] = None


class KickoffBloco3Input(BaseModel):
    nome_tecnico_produto: Optional[str] = None
    nome_comercial_cliente: Optional[str] = None
    categoria_anvisa: Optional[str] = None
    tipo_produto: Optional[str] = None
    forma_apresentacao: Optional[str] = None
    volume_peso_liquido_valor: Optional[float] = None
    volume_peso_liquido_unidade: Optional[str] = None
    aspecto_visual: Optional[str] = None
    foto_amostra_aprovada_file_id: Optional[str] = None
    cor_descricao: Optional[str] = None
    cor_codigo: Optional[str] = None
    odor: Optional[str] = None
    ph_minimo: Optional[float] = None
    ph_maximo: Optional[float] = None
    viscosidade_minima_cp: Optional[float] = None
    viscosidade_maxima_cp: Optional[float] = None
    viscosidade_spindle: Optional[str] = None
    viscosidade_rpm: Optional[str] = None
    densidade_minima: Optional[float] = None
    densidade_maxima: Optional[float] = None
    teor_alcool_minimo: Optional[float] = None
    teor_alcool_maximo: Optional[float] = None
    parametros_microbiologicos: Dict[str, Any] = Field(default_factory=dict)
    estabilidade_minima_comprovada_meses: Optional[int] = None
    restricoes_claims: List[str] = Field(default_factory=list)
    registro_anvisa_numero: Optional[str] = None
    registro_anvisa_file_id: Optional[str] = None
    criterios_fisicoquimicos: List[Dict[str, Any]] = Field(default_factory=list)
    criterios_microbiologicos: List[Dict[str, Any]] = Field(default_factory=list)
    analises_obrigatorias_por_lote: List[str] = Field(default_factory=list)
    plano_amostragem: Optional[str] = None
    quantidade_retencao: Optional[float] = None
    unidade_retencao: Optional[str] = None
    prazo_retencao_meses: Optional[int] = None
    responsavel_liberacao_lote: Optional[str] = None


class KickoffBloco4Input(BaseModel):
    embalagem_primaria_tipo: Optional[str] = None
    embalagem_primaria_material: Optional[str] = None
    embalagem_primaria_volume_nominal: Optional[float] = None
    embalagem_primaria_fornecedor_id: Optional[str] = None
    embalagem_primaria_fornecedor_alternativo_id: Optional[str] = None
    embalagem_primaria_codigo_interno: Optional[str] = None
    embalagem_primaria_cor: Optional[str] = None
    embalagem_primaria_acabamento: Optional[str] = None
    embalagem_primaria_tolerancia_dimensional: Optional[str] = None
    embalagem_primaria_laudo_file_id: Optional[str] = None
    fechamento_tipo: Optional[str] = None
    fechamento_material: Optional[str] = None
    fechamento_cor: Optional[str] = None
    fechamento_rosca_encaixe: Optional[str] = None
    fechamento_fornecedor_id: Optional[str] = None
    fechamento_codigo_interno: Optional[str] = None
    fechamento_quantidade_por_unidade: Optional[int] = None
    fechamento_acessorio: Optional[str] = None
    embalagem_secundaria_tipo: Optional[str] = None
    embalagem_secundaria_material: Optional[str] = None
    embalagem_secundaria_dimensoes: Optional[str] = None
    embalagem_secundaria_gramatura: Optional[float] = None
    embalagem_secundaria_fornecedor_id: Optional[str] = None
    embalagem_secundaria_codigo_interno: Optional[str] = None
    embalagem_secundaria_unidades_por_caixa: Optional[int] = None
    embalagem_secundaria_arte_file_id: Optional[str] = None
    embalagem_secundaria_arte_data_aprovacao: Optional[str] = None
    embalagem_secundaria_arte_aprovador_nome: Optional[str] = None
    embalagem_secundaria_arte_aprovador_email: Optional[str] = None
    caixa_master_tipo: Optional[str] = None
    caixa_master_dimensoes: Optional[str] = None
    caixa_master_unidades: Optional[int] = None
    caixa_master_peso_bruto_kg: Optional[float] = None
    configuracao_palete: Optional[str] = None
    tipo_palete: Optional[str] = None
    filme_stretch: Optional[bool] = None
    caixa_master_codigo_interno: Optional[str] = None
    tipo_rotulagem: Optional[str] = None
    rotulo_material: Optional[str] = None
    rotulo_dimensoes: Optional[str] = None
    rotulo_fornecedor_id: Optional[str] = None
    rotulo_codigo_interno: Optional[str] = None
    rotulo_arte_file_id: Optional[str] = None
    rotulo_arte_data_aprovacao: Optional[str] = None
    rotulo_arte_aprovador: Optional[str] = None
    rotulo_informacoes_obrigatorias_checklist: Dict[str, Any] = Field(default_factory=dict)
    rotulo_quantidade_por_pedido: Optional[int] = None


class KickoffApprovalInput(BaseModel):
    etapa: str
    decisao: str
    justificativa: Optional[str] = None
    observacoes: Optional[str] = None


class BomExportInput(BaseModel):
    formato: str = "csv"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clone_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clone_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone_value(v) for v in value]
    return value


def _version_code(number: int) -> str:
    return f"v{number}"


def _approval_template() -> List[Dict[str, Any]]:
    return [
        {
            "etapa": etapa,
            "label": APPROVAL_LABELS[etapa],
            "status": "pendente",
            "decisao": None,
            "justificativa": "",
            "observacoes": "",
            "decidido_por": None,
            "decidido_por_nome": "",
            "decidido_em": None,
        }
        for etapa in APPROVAL_SEQUENCE
    ]


def _diff_entries(prefix: str, before_doc: Dict[str, Any], after_doc: Dict[str, Any], user: dict) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    keys = set(before_doc.keys()) | set(after_doc.keys())
    for key in sorted(keys):
        before_value = before_doc.get(key)
        after_value = after_doc.get(key)
        if before_value == after_value:
            continue
        entries.append(
            {
                "campo": f"{prefix}.{key}",
                "valor_anterior": before_value,
                "valor_novo": after_value,
                "usuario_id": user["id"],
                "usuario_nome": user.get("name", ""),
                "datetime": now_iso(),
            }
        )
    return entries


def _has_values(data: Dict[str, Any]) -> bool:
    for value in data.values():
        if value not in (None, "", [], {}):
            return True
    return False


def _block2_ready(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing = []
    required = [
        "volume_primeiro_pedido",
        "data_entrega_contratada",
        "preco_venda_cliente_rs_un",
        "condicao_pagamento",
    ]
    for field in required:
        if data.get(field) in (None, "", [], {}):
            missing.append(field)
    return len(missing) == 0, missing


def _block3_ready(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing = []
    required = [
        "nome_tecnico_produto",
        "tipo_produto",
        "forma_apresentacao",
        "categoria_anvisa",
    ]
    for field in required:
        if data.get(field) in (None, "", [], {}):
            missing.append(field)
    return len(missing) == 0, missing


def _block4_ready(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing = []
    required = [
        "embalagem_primaria_tipo",
        "embalagem_primaria_material",
        "tipo_rotulagem",
    ]
    for field in required:
        if data.get(field) in (None, "", [], {}):
            missing.append(field)
    return len(missing) == 0, missing


async def _get_user_for_roles(tenant_id: str, roles: List[str]) -> Optional[Dict[str, Any]]:
    for role in roles:
        doc = _row(await pg_db.fetch_one(
            "SELECT id, name, role FROM users WHERE tenant_id=$1 AND role=$2 LIMIT 1",
            tenant_id, role,
        ))
        if doc:
            return doc
    return None


async def _find_formula_context(formula_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    formula = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_formulas WHERE id=$1 AND tenant_id=$2", formula_id, tenant_id
    ))
    if not formula:
        return None
    development = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_developments WHERE id=$1 AND tenant_id=$2",
        formula.get("development_id"), tenant_id,
    ))
    if not development:
        return None
    pd_request = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_requests WHERE id=$1 AND tenant_id=$2",
        development.get("pd_request_id"), tenant_id,
    ))
    approval = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_approvals WHERE development_id=$1", development["id"]
    ))
    return {
        "formula": formula,
        "development": development,
        "pd_request": pd_request,
        "approval": approval or {},
    }


async def _resolve_registered_formula_for_project(project_id: str, tenant_id: str, explicit_formula_id: Optional[str] = None) -> Dict[str, Any]:
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2", project_id, tenant_id
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado")

    if explicit_formula_id:
        ctx = await _find_formula_context(explicit_formula_id, tenant_id)
        if not ctx:
            raise HTTPException(status_code=404, detail="Formula nao encontrada")
        pd_request = ctx.get("pd_request") or {}
        if pd_request.get("linked_projeto_id") != project_id and pd_request.get("crm_project_id") != project_id:
            raise HTTPException(status_code=400, detail="Formula informada nao pertence ao projeto")
        approval = ctx.get("approval") or {}
        if not (approval.get("approved_by_client") and approval.get("approved_by_internal")):
            raise HTTPException(status_code=400, detail="A formula informada ainda nao esta registrada no Banco P&D.")
        return {"project": project, **ctx}

    requests_rows = await pg_db.fetch_all(
        "SELECT * FROM pd_requests WHERE tenant_id=$1 AND (linked_projeto_id=$2 OR crm_project_id=$2)",
        tenant_id, project_id,
    )
    requests_docs = [_row(r) for r in requests_rows]
    if not requests_docs:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma formula registrada encontrada para este projeto. Registre a formula no Banco P&D antes de avancar.",
        )

    req_map = {req["id"]: req for req in requests_docs if req.get("id")}
    req_ids = list(req_map.keys())
    devs_rows = await pg_db.fetch_all(
        "SELECT * FROM pd_developments WHERE tenant_id=$1 AND pd_request_id = ANY($2::text[])",
        tenant_id, req_ids,
    )
    devs = [_row(r) for r in devs_rows]
    if not devs:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma formula registrada encontrada para este projeto. Registre a formula no Banco P&D antes de avancar.",
        )

    dev_map = {dev["id"]: dev for dev in devs if dev.get("id")}
    dev_ids = list(dev_map.keys())
    approvals_rows = await pg_db.fetch_all(
        "SELECT * FROM pd_approvals WHERE development_id = ANY($1::text[])", dev_ids
    )
    approvals_map = {doc["development_id"]: _row(doc) for doc in approvals_rows if doc.get("development_id")}

    formulas_rows = await pg_db.fetch_all(
        "SELECT * FROM pd_formulas WHERE tenant_id=$1 AND development_id = ANY($2::text[]) ORDER BY version DESC, created_at DESC",
        tenant_id, dev_ids,
    )
    formulas = [_row(r) for r in formulas_rows]

    selected = None
    for formula in formulas:
        approval = approvals_map.get(formula.get("development_id"), {})
        if not (approval.get("approved_by_client") and approval.get("approved_by_internal")):
            continue
        selected = {
            "formula": formula,
            "development": dev_map.get(formula.get("development_id")),
            "pd_request": req_map.get(dev_map.get(formula.get("development_id"), {}).get("pd_request_id")),
            "approval": approval,
        }
        break

    if not selected:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma formula registrada encontrada para este projeto. Registre a formula no Banco P&D antes de avancar.",
        )
    return {"project": project, **selected}


async def _approved_sample_payload(project: dict, pd_request: Optional[dict]) -> Dict[str, Any]:
    sample = None
    variation = None
    tid = project["tenant_id"]

    if pd_request and pd_request.get("linked_amostra_id"):
        sample = _row(await pg_db.fetch_one(
            "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
            pd_request["linked_amostra_id"], tid,
        ))

    if sample and pd_request and pd_request.get("linked_variacao_id"):
        variation = _row(await pg_db.fetch_one(
            "SELECT * FROM crm_sample_variacoes WHERE sample_id=$1 AND id=$2",
            sample["id"], pd_request["linked_variacao_id"],
        ))

    if not sample:
        sample = _row(await pg_db.fetch_one(
            "SELECT * FROM crm_samples WHERE projeto_id=$1 AND tenant_id=$2 ORDER BY updated_at DESC LIMIT 1",
            project["id"], tid,
        ))
        if sample:
            variation = _row(await pg_db.fetch_one(
                "SELECT * FROM crm_sample_variacoes WHERE sample_id=$1 AND (status='aprovada' OR gera_sku=TRUE) LIMIT 1",
                sample["id"],
            ))

    approved_code = ""
    feedback = ""
    if variation:
        approved_code = variation.get("codigo", "")
        feedback = variation.get("observacoes_especificas") or variation.get("descricao_aplicacao") or ""
    elif sample:
        approved_code = str(sample.get("numero_amostra", ""))
        feedback = sample.get("feedback_cliente", "") or sample.get("briefing_especifico", "") or ""
    return {
        "amostra_aprovada": approved_code,
        "feedback_cliente": feedback,
    }


async def _build_kickoff_auto_block(project: dict, client: dict, formula_ctx: dict) -> Dict[str, Any]:
    formula = formula_ctx["formula"]
    pd_request = formula_ctx.get("pd_request") or {}
    approved_sample = await _approved_sample_payload(project, pd_request)
    kickoff_number_seq = await next_sequence(project["tenant_id"], "kickoff", start=0)
    kickoff_number = f"KO-{datetime.now(timezone.utc).year}-{kickoff_number_seq:04d}"
    return {
        "numero_kickoff": kickoff_number,
        "data_abertura": now_iso(),
        "versao": _version_code(1),
        "versao_numero": 1,
        "status": "em_preenchimento",
        "cliente": project.get("cliente_nome") or client.get("nome_empresa", ""),
        "cnpj": client.get("cnpj", ""),
        "projeto_vinculado": project.get("nome_projeto", ""),
        "amostra_aprovada": approved_sample.get("amostra_aprovada", ""),
        "formula_vinculada": formula.get("name", ""),
        "formulador_responsavel": formula.get("created_by_name", ""),
        "responsavel_comercial": project.get("responsavel_comercial") or client.get("responsavel_comercial", ""),
        "pre_briefing_origem": project.get("briefing_resumido", ""),
        "feedback_cliente": approved_sample.get("feedback_cliente", ""),
        "categoria_anvisa_herdada": project.get("categoria", ""),
    }


async def _ensure_project_and_client(project_id: str, tenant_id: str) -> Tuple[dict, dict]:
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2", project_id, tenant_id
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto nao encontrado")
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        project.get("cliente_id"), tenant_id,
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente do projeto nao encontrado")
    return project, client


async def _get_latest_kickoff_by_group(group_id: str, tenant_id: str) -> Optional[dict]:
    return _row(await pg_db.fetch_one(
        "SELECT * FROM kickoffs WHERE kickoff_group_id=$1 AND tenant_id=$2 ORDER BY versao_numero DESC LIMIT 1",
        group_id, tenant_id,
    ))


async def _get_kickoff_or_404(kickoff_id: str, tenant_id: str) -> dict:
    doc = _row(await pg_db.fetch_one(
        "SELECT * FROM kickoffs WHERE id=$1 AND tenant_id=$2", kickoff_id, tenant_id
    ))
    if not doc:
        raise HTTPException(status_code=404, detail="Kickoff nao encontrado")
    return doc


def _current_approval_step(kickoff: dict) -> Optional[Dict[str, Any]]:
    for step in kickoff.get("aprovacoes", []):
        if step.get("status") == "pendente":
            return step
    return None


async def _sync_project_kickoff_summary(kickoff: dict):
    await pg_db.execute(
        """UPDATE crm_projects SET kickoff_id=$1, kickoff_numero=$2, kickoff_status=$3,
           kickoff_versao=$4, kickoff_group_id=$5, updated_at=NOW()
           WHERE id=$6 AND tenant_id=$7""",
        kickoff["id"], kickoff["numero_kickoff"], kickoff["status"],
        kickoff["versao"], kickoff["kickoff_group_id"],
        kickoff["projeto_id"], kickoff["tenant_id"],
    )


async def _create_or_reuse_task(
    *,
    kickoff: dict,
    title: str,
    task_code: str,
    category: str,
    due_in_days: int,
    created_by: dict,
    responsible_roles: List[str],
    description: str = "",
    blocking: bool = False,
) -> Optional[dict]:
    existing = _row(await pg_db.fetch_one(
        """SELECT * FROM workflow_tasks
           WHERE tenant_id=$1 AND entity_type='kickoff' AND entity_id=$2
           AND status = ANY($3::text[])
           AND metadata->>'kickoff_task_code' = $4
           LIMIT 1""",
        kickoff["tenant_id"], kickoff["id"],
        ["pendente", "em_andamento", "em_atraso"],
        task_code,
    ))
    if existing:
        return existing
    responsible = await _get_user_for_roles(kickoff["tenant_id"], responsible_roles)
    return await create_workflow_task(
        tenant_id=kickoff["tenant_id"],
        entity_type="kickoff",
        entity_id=kickoff["id"],
        title=title,
        description=description,
        category=category,
        blocking=blocking,
        due_in_days=due_in_days,
        responsible_id=(responsible or {}).get("id"),
        created_by=created_by,
        metadata={
            "module_origin": "kickoff",
            "kickoff_task_code": task_code,
            "kickoff_id": kickoff["id"],
            "kickoff_numero": kickoff["numero_kickoff"],
        },
    )


async def _enqueue_block_tasks_after_create(kickoff: dict, user: dict):
    await _create_or_reuse_task(
        kickoff=kickoff,
        title=f"Preencher Bloco 2 do Kickoff {kickoff['numero_kickoff']}",
        task_code="preencher_kickoff_bloco2",
        category="comercial",
        due_in_days=2,
        created_by=user,
        responsible_roles=["sales_ops", "vendedor", "admin"],
        description="Preencher especificacao comercial e anexar contrato assinado.",
        blocking=False,
    )


async def _enqueue_after_block2(kickoff: dict, user: dict):
    await _create_or_reuse_task(
        kickoff=kickoff,
        title=f"Preencher Bloco 3 do Kickoff {kickoff['numero_kickoff']}",
        task_code="preencher_kickoff_bloco3",
        category="pd_dev",
        due_in_days=2,
        created_by=user,
        responsible_roles=["formulador", "lider_pd", "admin"],
        description="Completar especificacao tecnica e foto da amostra aprovada.",
        blocking=False,
    )


async def _enqueue_after_block3(kickoff: dict, user: dict):
    await _create_or_reuse_task(
        kickoff=kickoff,
        title=f"Preencher Bloco 4 do Kickoff {kickoff['numero_kickoff']}",
        task_code="preencher_kickoff_bloco4",
        category="engenharia_produto",
        due_in_days=2,
        created_by=user,
        responsible_roles=["engenharia_produto", "admin"],
        description="Completar embalagem, fornecedores e BOM consolidado.",
        blocking=False,
    )


async def _enqueue_approval_task(kickoff: dict, user: dict, etapa: str):
    role_targets = {
        "lider_pd": ["lider_pd", "admin"],
        "cq": ["qa", "admin"],
        "eng_produto": ["engenharia_produto", "admin"],
        "direcao": ["admin"],
    }
    category_targets = {
        "lider_pd": "pd_dev",
        "cq": "qa",
        "eng_produto": "engenharia_produto",
        "direcao": "manual",
    }
    await _create_or_reuse_task(
        kickoff=kickoff,
        title=f"Aprovar Kickoff {kickoff['numero_kickoff']} - {APPROVAL_LABELS[etapa]}",
        task_code=f"aprovar_kickoff_{etapa}",
        category=category_targets[etapa],
        due_in_days=2,
        created_by=user,
        responsible_roles=role_targets[etapa],
        description=f"Registrar aprovacao ou reprovacao da etapa {APPROVAL_LABELS[etapa]}.",
        blocking=True,
    )


async def _enqueue_revision_task(kickoff: dict, user: dict, etapa: str):
    mapping = {
        "lider_pd": ("preencher_kickoff_bloco3", "pd_dev", ["formulador", "lider_pd", "admin"], "Revisar Bloco 3 do Kickoff"),
        "cq": ("preencher_kickoff_bloco3", "pd_dev", ["formulador", "lider_pd", "admin"], "Ajustar criterios tecnicos do Kickoff"),
        "eng_produto": ("preencher_kickoff_bloco4", "engenharia_produto", ["engenharia_produto", "admin"], "Revisar Bloco 4 do Kickoff"),
        "direcao": ("preencher_kickoff_bloco2", "comercial", ["sales_ops", "vendedor", "admin"], "Revisar condicoes comerciais do Kickoff"),
    }
    task_code, category, roles, title = mapping[etapa]
    await _create_or_reuse_task(
        kickoff=kickoff,
        title=f"{title} {kickoff['numero_kickoff']}",
        task_code=task_code,
        category=category,
        due_in_days=2,
        created_by=user,
        responsible_roles=roles,
        description="Kickoff reprovado em fluxo de aprovacao. Ajustar bloco responsavel.",
        blocking=False,
    )


async def _get_supplier_doc(supplier_id: Optional[str], tenant_id: str) -> Optional[dict]:
    if not supplier_id:
        return None
    return _row(await pg_db.fetch_one(
        """SELECT hf.*, cf.nome_fantasia, cf.razao_social
           FROM homologacao_fornecedores hf
           LEFT JOIN compras_fornecedores cf ON cf.id = hf.fornecedor_id AND cf.tenant_id = hf.tenant_id
           WHERE hf.id=$1 AND hf.tenant_id=$2""",
        supplier_id, tenant_id,
    ))


async def _find_mp_doc(tenant_id: str, ingredient_name: str, catalog_id: Optional[str] = None) -> Optional[dict]:
    keys = []
    if catalog_id:
        catalog = _row(await pg_db.fetch_one(
            "SELECT * FROM pd_catalog WHERE id=$1 AND tenant_id=$2", catalog_id, tenant_id
        ))
        if catalog:
            for key in (catalog.get("nome"), catalog.get("inci"), catalog.get("codigo_interno")):
                if key:
                    keys.append(str(key).strip().lower())
    if ingredient_name:
        keys.append(str(ingredient_name).strip().lower())
    if not keys:
        return None
    return _row(await pg_db.fetch_one(
        """SELECT * FROM homologacao_mps
           WHERE tenant_id=$1 AND (
             LOWER(nome) = ANY($2::text[])
             OR LOWER(inci) = ANY($2::text[])
             OR LOWER(codigo_interno) = ANY($2::text[])
           )
           LIMIT 1""",
        tenant_id, keys,
    ))


async def _build_bom_lines(kickoff: dict) -> List[Dict[str, Any]]:
    _row(await pg_db.fetch_one(
        "SELECT * FROM pd_formulas WHERE id=$1 AND tenant_id=$2",
        kickoff["formula_id"], kickoff["tenant_id"],
    ))
    items_rows = await pg_db.fetch_all(
        "SELECT * FROM pd_formula_items WHERE formula_id=$1", kickoff["formula_id"]
    )
    items = [_row(r) for r in items_rows]
    bloco3 = kickoff.get("bloco3") or {}
    bloco4 = kickoff.get("bloco4") or {}
    bloco2 = kickoff.get("bloco2") or {}
    volume_un = bloco3.get("volume_peso_liquido_unidade") or "mL"
    volume_value = bloco3.get("volume_peso_liquido_valor") or 0
    pedido_volume = bloco2.get("volume_primeiro_pedido") or 0

    lines: List[Dict[str, Any]] = []
    for item in items:
        mp_doc = await _find_mp_doc(kickoff["tenant_id"], item.get("ingredient_name", ""), item.get("catalog_id"))
        unit = "L" if str(volume_un).lower() == "ml" else "kg"
        per_unit = round(((item.get("percentage") or 0) / 100.0) * ((volume_value or 0) / 1000.0), 6)
        lines.append(
            {
                "id": item.get("id") or new_id(),
                "codigo_interno": (mp_doc or {}).get("codigo_interno") or item.get("catalog_id") or item.get("ingredient_name", ""),
                "descricao": item.get("ingredient_name", ""),
                "tipo": "mp_formula",
                "fornecedor_principal": {
                    "id": (mp_doc or {}).get("fornecedor_id"),
                    "nome": (mp_doc or {}).get("fornecedor_nome", ""),
                },
                "fornecedor_alternativo": None,
                "unidade": unit,
                "quantidade_por_unidade": per_unit,
                "custo_unitario_estimado_rs": round(item.get("cost_brl") or 0, 4),
                "status_homologacao": (mp_doc or {}).get("status", "pendente"),
                "quantidade_total_pedido": round(per_unit * pedido_volume, 4),
            }
        )

    packaging_specs = [
        (
            "embalagem_primaria",
            bloco4.get("embalagem_primaria_codigo_interno"),
            f"Embalagem primaria {bloco4.get('embalagem_primaria_tipo', '')} {bloco4.get('embalagem_primaria_material', '')}".strip(),
            bloco4.get("embalagem_primaria_fornecedor_id"),
            bloco4.get("embalagem_primaria_fornecedor_alternativo_id"),
            1,
        ),
        (
            "tampa",
            bloco4.get("fechamento_codigo_interno"),
            f"Fechamento {bloco4.get('fechamento_tipo', '')}".strip(),
            bloco4.get("fechamento_fornecedor_id"),
            None,
            bloco4.get("fechamento_quantidade_por_unidade") or 1,
        ),
        (
            "emb_secundaria",
            bloco4.get("embalagem_secundaria_codigo_interno"),
            f"Embalagem secundaria {bloco4.get('embalagem_secundaria_tipo', '')}".strip(),
            bloco4.get("embalagem_secundaria_fornecedor_id"),
            None,
            1 if bloco4.get("embalagem_secundaria_tipo") != "sem_caixa" else 0,
        ),
        (
            "emb_terciaria",
            bloco4.get("caixa_master_codigo_interno"),
            f"Caixa master {bloco4.get('caixa_master_tipo', '')}".strip(),
            None,
            None,
            1 / max(int(bloco4.get("caixa_master_unidades") or 1), 1),
        ),
        (
            "rotulo",
            bloco4.get("rotulo_codigo_interno"),
            f"Rotulo {bloco4.get('tipo_rotulagem', '')}".strip(),
            bloco4.get("rotulo_fornecedor_id"),
            None,
            1,
        ),
    ]
    for tipo, codigo, descricao, supplier_id, alternative_id, qty in packaging_specs:
        if qty in (None, 0) and tipo != "emb_terciaria":
            continue
        supplier = await _get_supplier_doc(supplier_id, kickoff["tenant_id"])
        supplier_alt = await _get_supplier_doc(alternative_id, kickoff["tenant_id"])
        status = supplier.get("status", "pendente") if supplier else "pendente"
        lines.append(
            {
                "id": new_id(),
                "codigo_interno": codigo or f"{kickoff['numero_kickoff']}-{tipo}",
                "descricao": descricao,
                "tipo": tipo,
                "fornecedor_principal": {
                    "id": (supplier or {}).get("id"),
                    "nome": (supplier or {}).get("nome_fantasia") or (supplier or {}).get("razao_social", ""),
                },
                "fornecedor_alternativo": {
                    "id": (supplier_alt or {}).get("id"),
                    "nome": (supplier_alt or {}).get("nome_fantasia") or (supplier_alt or {}).get("razao_social", ""),
                } if supplier_alt else None,
                "unidade": "un",
                "quantidade_por_unidade": round(qty, 6),
                "custo_unitario_estimado_rs": 0.0,
                "status_homologacao": status,
                "quantidade_total_pedido": round((qty or 0) * pedido_volume, 4),
            }
        )
    return lines


async def _refresh_bom(kickoff: dict) -> dict:
    if not _has_values(kickoff.get("bloco4") or {}):
        kickoff["bom"] = []
        return kickoff
    bom_lines = await _build_bom_lines(kickoff)
    await pg_db.execute(
        "UPDATE kickoffs SET bom=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        bom_lines, kickoff["id"], kickoff["tenant_id"],
    )
    kickoff["bom"] = bom_lines
    return kickoff


async def _create_homologation_tasks_for_bom(kickoff: dict, user: dict):
    for line in kickoff.get("bom", []):
        if line.get("status_homologacao") == "homologado":
            continue
        await _create_or_reuse_task(
            kickoff=kickoff,
            title=f"Homologar item do BOM {line.get('descricao', '')}",
            task_code=f"homologar_fornecedor_mp:{line.get('codigo_interno', '')}",
            category="qa",
            due_in_days=2,
            created_by=user,
            responsible_roles=["qa", "lider_pd", "admin"],
            description="Item do BOM sem homologacao concluida bloqueia aprovacao final do Kickoff.",
            blocking=False,
        )


def _validate_block3_vs_block4(bloco3: dict, bloco4: dict):
    vol3 = bloco3.get("volume_peso_liquido_valor")
    vol4 = bloco4.get("embalagem_primaria_volume_nominal")
    if vol3 not in (None, "") and vol4 not in (None, "") and float(vol3) != float(vol4):
        raise HTTPException(
            status_code=400,
            detail="O volume nominal da embalagem primaria deve coincidir com o volume/peso liquido do Bloco 3.",
        )


def _validate_kickoff_editable(kickoff: dict):
    if kickoff.get("status") == "substituida":
        raise HTTPException(status_code=409, detail="Versao substituida. Edite a versao vigente do Kickoff.")
    if kickoff.get("status") == "arquivado":
        raise HTTPException(status_code=409, detail="Kickoff arquivado nao pode ser alterado.")


async def _insert_kickoff(kf: dict):
    await pg_db.execute(
        """INSERT INTO kickoffs (
            id, tenant_id, kickoff_group_id, parent_kickoff_id, projeto_id, formula_id,
            numero_kickoff, data_abertura, versao, versao_numero, status,
            bloco1, bloco2, bloco3, bloco4, bom, aprovacoes, log_auditoria,
            created_at, updated_at, created_by, created_by_name,
            approved_at, approved_by, approved_by_name
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
            $12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25
        )""",
        kf["id"], kf["tenant_id"], kf.get("kickoff_group_id"), kf.get("parent_kickoff_id"),
        kf["projeto_id"], kf.get("formula_id"),
        kf["numero_kickoff"], kf.get("data_abertura"), kf["versao"], kf["versao_numero"],
        kf["status"],
        kf.get("bloco1") or {}, kf.get("bloco2") or {}, kf.get("bloco3") or {},
        kf.get("bloco4") or {}, kf.get("bom") or [], kf.get("aprovacoes") or [],
        kf.get("log_auditoria") or [],
        kf["created_at"], kf["updated_at"], kf["created_by"], kf.get("created_by_name", ""),
        kf.get("approved_at"), kf.get("approved_by"), kf.get("approved_by_name", ""),
    )


async def _create_revision_version(kickoff: dict, user: dict, reason: str) -> dict:
    latest = await _get_latest_kickoff_by_group(kickoff["kickoff_group_id"], kickoff["tenant_id"])
    if latest and latest.get("id") != kickoff["id"]:
        kickoff = latest
    new_version_number = int(kickoff.get("versao_numero") or 1) + 1
    revision = _clone_value(kickoff)
    revision["id"] = new_id()
    revision["versao_numero"] = new_version_number
    revision["versao"] = _version_code(new_version_number)
    revision["status"] = "em_revisao"
    revision["aprovacoes"] = _approval_template()
    revision["created_at"] = now_iso()
    revision["updated_at"] = now_iso()
    revision["created_by"] = user["id"]
    revision["created_by_name"] = user.get("name", "")
    revision["approved_at"] = None
    revision["approved_by"] = None
    revision["approved_by_name"] = ""
    revision["parent_kickoff_id"] = kickoff["id"]
    revision["log_auditoria"] = list(kickoff.get("log_auditoria") or [])
    revision["log_auditoria"].append(
        {
            "campo": "versao",
            "valor_anterior": kickoff.get("versao"),
            "valor_novo": revision["versao"],
            "usuario_id": user["id"],
            "usuario_nome": user.get("name", ""),
            "datetime": now_iso(),
            "motivo": reason,
        }
    )
    await _insert_kickoff(revision)
    await pg_db.execute(
        "UPDATE kickoffs SET status='substituida', updated_at=NOW() WHERE id=$1 AND tenant_id=$2",
        kickoff["id"], kickoff["tenant_id"],
    )
    await _sync_project_kickoff_summary(revision)
    await audit_log(
        tenant_id=kickoff["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="kickoff_version_created",
        entity_type="kickoff",
        entity_id=revision["id"],
        before={"kickoff_id": kickoff["id"], "versao": kickoff.get("versao")},
        after={"kickoff_id": revision["id"], "versao": revision["versao"], "motivo": reason},
    )
    return revision


async def _ensure_mutable_version(kickoff: dict, user: dict, reason: str) -> dict:
    if kickoff.get("status") == "aprovado":
        return await _create_revision_version(kickoff, user, reason)
    return kickoff


async def _decorate_kickoff(kickoff: dict) -> dict:
    kickoff = await _refresh_bom(kickoff)
    block2_ok, block2_missing = _block2_ready(kickoff.get("bloco2") or {})
    block3_ok, block3_missing = _block3_ready(kickoff.get("bloco3") or {})
    block4_ok, block4_missing = _block4_ready(kickoff.get("bloco4") or {})
    current_step = _current_approval_step(kickoff)
    kickoff["progress"] = {
        "bloco1": True,
        "bloco2": block2_ok,
        "bloco3": block3_ok,
        "bloco4": block4_ok,
        "percentual": round((1 + int(block2_ok) + int(block3_ok) + int(block4_ok)) / 4 * 100),
    }
    kickoff["locks"] = {
        "bloco2": None,
        "bloco3": None if block2_ok else "Bloco 3 bloqueado: complete todos os campos comerciais do Bloco 2 primeiro.",
        "bloco4": None if block3_ok else "Bloco 4 bloqueado: complete os criterios tecnicos e especificacoes do Bloco 3 primeiro.",
        "aprovacao": None if (block2_ok and block3_ok and block4_ok) else "Aprovacao liberada somente apos concluir Blocos 2, 3 e 4.",
    }
    kickoff["blocos_status"] = {
        "bloco2": {"completo": block2_ok, "campos_pendentes": block2_missing},
        "bloco3": {"completo": block3_ok, "campos_pendentes": block3_missing},
        "bloco4": {"completo": block4_ok, "campos_pendentes": block4_missing},
    }
    kickoff["aprovacao_pendente"] = current_step
    return kickoff


async def _validate_kickoff_ready_for_approval(kickoff: dict):
    block2_ok, block2_missing = _block2_ready(kickoff.get("bloco2") or {})
    block3_ok, block3_missing = _block3_ready(kickoff.get("bloco3") or {})
    block4_ok, block4_missing = _block4_ready(kickoff.get("bloco4") or {})
    if not block2_ok:
        raise HTTPException(status_code=400, detail=f"Bloco 2 incompleto: {', '.join(block2_missing)}")
    if not block3_ok:
        raise HTTPException(status_code=400, detail=f"Bloco 3 incompleto: {', '.join(block3_missing)}")
    if not block4_ok:
        raise HTTPException(status_code=400, detail=f"Bloco 4 incompleto: {', '.join(block4_missing)}")


async def _mark_pd_request_kickoff_complete(kickoff: dict, user: dict) -> List[Dict[str, Any]]:
    generated: List[Dict[str, Any]] = []
    formula_ctx = await _find_formula_context(kickoff["formula_id"], kickoff["tenant_id"])
    pd_request = (formula_ctx or {}).get("pd_request") or {}
    if not pd_request:
        return generated
    await pg_db.execute(
        "UPDATE pd_requests SET updated_at=NOW() WHERE id=$1 AND tenant_id=$2",
        pd_request["id"], kickoff["tenant_id"],
    )
    try:
        from pd_routes import _generate_live_document_version

        generated_doc = await _generate_live_document_version(
            req_id=pd_request["id"],
            doc_type="epa",
            user=user,
            reason=f"Gerado apos aprovacao final do Kickoff {kickoff['numero_kickoff']}",
            changed_fields=[
                "identificacao_produto",
                "bom_bulk_formula",
                "bom_embalagem_primaria",
                "bom_embalagem_secundaria",
                "criterios_liberacao_lote",
            ],
            trigger="kickoff_aprovado",
            source_changes=[{"field": "kickoff", "label": "Kickoff aprovado", "before": None, "after": kickoff["numero_kickoff"]}],
        )
        generated.append({"tipo": "epa", "id": generated_doc.get("id"), "version_code": generated_doc.get("version_code")})
    except Exception:
        pass
    return generated


async def create_kickoff_for_project(project_id: str, user: dict, explicit_formula_id: Optional[str] = None) -> dict:
    project, client = await _ensure_project_and_client(project_id, user["tenant_id"])
    if project.get("stage") != "pedido_aprovado":
        raise HTTPException(status_code=400, detail="O Kickoff so pode ser aberto quando o projeto estiver em Pedido Aprovado.")

    existing = _row(await pg_db.fetch_one(
        """SELECT * FROM kickoffs WHERE tenant_id=$1 AND projeto_id=$2
           AND status = ANY($3::text[]) ORDER BY versao_numero DESC LIMIT 1""",
        user["tenant_id"], project_id,
        ["em_preenchimento", "aguardando_aprovacao", "aprovado", "em_revisao"],
    ))
    if existing:
        return await _decorate_kickoff(existing)

    formula_ctx = await _resolve_registered_formula_for_project(project_id, user["tenant_id"], explicit_formula_id)
    auto_block = await _build_kickoff_auto_block(project, client, formula_ctx)
    group_id = new_id()
    kickoff = {
        "id": new_id(),
        "tenant_id": user["tenant_id"],
        "kickoff_group_id": group_id,
        "parent_kickoff_id": None,
        "projeto_id": project_id,
        "formula_id": formula_ctx["formula"]["id"],
        "numero_kickoff": auto_block["numero_kickoff"],
        "data_abertura": auto_block["data_abertura"],
        "versao": auto_block["versao"],
        "versao_numero": auto_block["versao_numero"],
        "status": auto_block["status"],
        "bloco1": auto_block,
        "bloco2": {},
        "bloco3": {},
        "bloco4": {},
        "bom": [],
        "aprovacoes": _approval_template(),
        "log_auditoria": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "approved_at": None,
        "approved_by": None,
        "approved_by_name": "",
    }
    await _insert_kickoff(kickoff)
    await _sync_project_kickoff_summary(kickoff)
    await _enqueue_block_tasks_after_create(kickoff, user)
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="kickoff_created",
        entity_type="kickoff",
        entity_id=kickoff["id"],
        after={
            "numero_kickoff": kickoff["numero_kickoff"],
            "projeto_id": kickoff["projeto_id"],
            "formula_id": kickoff["formula_id"],
        },
    )
    return await _decorate_kickoff(kickoff)


@kickoff_router.post("/kickoff")
async def create_kickoff(data: KickoffCreateInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, {"admin", "sales_ops", "vendedor", "lider_pd"})
    kickoff = await create_kickoff_for_project(data.projeto_id, user, data.formula_id)
    return kickoff


@kickoff_router.get("/kickoff/{kickoff_id}")
async def get_kickoff(kickoff_id: str, request: Request):
    user = await get_current_user(request)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    return await _decorate_kickoff(kickoff)


@kickoff_router.get("/kickoff/{kickoff_id}/historico")
async def kickoff_history(kickoff_id: str, request: Request):
    user = await get_current_user(request)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    rows = await pg_db.fetch_all(
        "SELECT * FROM kickoffs WHERE kickoff_group_id=$1 AND tenant_id=$2 ORDER BY versao_numero DESC LIMIT 100",
        kickoff["kickoff_group_id"], user["tenant_id"],
    )
    return [_row(r) for r in rows]


@kickoff_router.get("/kickoffs")
async def list_kickoffs(
    request: Request,
    status: Optional[str] = None,
    responsavel: Optional[str] = None,
    periodo_de: Optional[str] = None,
    periodo_ate: Optional[str] = None,
):
    user = await get_current_user(request)
    clauses = ["tenant_id=$1"]
    vals: list = [user["tenant_id"]]
    i = 2
    if status:
        clauses.append(f"status=${i}")
        vals.append(status)
        i += 1
    rows = await pg_db.fetch_all(
        f"SELECT * FROM kickoffs WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 1000",
        *vals,
    )
    docs = [_row(r) for r in rows]
    filtered: List[Dict[str, Any]] = []
    start_dt = _parse_iso(periodo_de)
    end_dt = _parse_iso(periodo_ate)
    for doc in docs:
        if responsavel:
            current_step = _current_approval_step(doc)
            current_name = (current_step or {}).get("decidido_por_nome") or ""
            if responsavel.lower() not in f"{doc.get('created_by_name', '')} {current_name}".lower():
                continue
        opened_at = _parse_iso(doc.get("data_abertura")) or _parse_iso(doc.get("created_at"))
        if start_dt and opened_at and opened_at < start_dt:
            continue
        if end_dt and opened_at and opened_at > end_dt + timedelta(days=1):
            continue
        current_step = _current_approval_step(doc)
        filtered.append(
            {
                **doc,
                "responsavel_aprovacao_pendente": (current_step or {}).get("label"),
                "data_aprovacao": doc.get("approved_at"),
            }
        )
    return filtered


@kickoff_router.put("/kickoff/{kickoff_id}/bloco2")
async def update_kickoff_bloco2(kickoff_id: str, data: KickoffBloco2Input, request: Request):
    user = await get_current_user(request)
    require_roles(user, BLOCK_2_ROLES)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    _validate_kickoff_editable(kickoff)
    kickoff = await _ensure_mutable_version(kickoff, user, "Alteracao no Bloco 2 apos aprovacao")
    existing = kickoff.get("bloco2") or {}
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    merged = {**existing, **updates}
    changes = _diff_entries("bloco2", existing, merged, user)
    new_status = kickoff["status"]
    if new_status == "em_revisao":
        new_status = "em_preenchimento"
    await pg_db.execute(
        """UPDATE kickoffs SET bloco2=$1, status=$2,
           log_auditoria = COALESCE(log_auditoria,'[]'::jsonb) || $3::jsonb,
           updated_at=NOW() WHERE id=$4 AND tenant_id=$5""",
        merged, new_status, changes, kickoff["id"], kickoff["tenant_id"],
    )
    kickoff = await _get_kickoff_or_404(kickoff["id"], user["tenant_id"])
    block2_ok, _ = _block2_ready(merged)
    if block2_ok:
        await _enqueue_after_block2(kickoff, user)
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="kickoff_bloco2_updated",
        entity_type="kickoff",
        entity_id=kickoff["id"],
        before=existing,
        after=merged,
    )
    return await _decorate_kickoff(kickoff)


@kickoff_router.put("/kickoff/{kickoff_id}/bloco3")
async def update_kickoff_bloco3(kickoff_id: str, data: KickoffBloco3Input, request: Request):
    user = await get_current_user(request)
    require_roles(user, BLOCK_3_ROLES)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    _validate_kickoff_editable(kickoff)
    kickoff = await _ensure_mutable_version(kickoff, user, "Alteracao no Bloco 3 apos aprovacao")
    existing = kickoff.get("bloco3") or {}
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    merged = {**existing, **updates}
    if merged.get("ph_minimo") not in (None, "") and merged.get("ph_maximo") not in (None, ""):
        if float(merged["ph_minimo"]) > float(merged["ph_maximo"]):
            raise HTTPException(status_code=400, detail="ph_minimo nao pode ser maior que ph_maximo")
    changes = _diff_entries("bloco3", existing, merged, user)
    new_status = kickoff["status"]
    if new_status == "em_revisao":
        new_status = "em_preenchimento"
    await pg_db.execute(
        """UPDATE kickoffs SET bloco3=$1, status=$2,
           log_auditoria = COALESCE(log_auditoria,'[]'::jsonb) || $3::jsonb,
           updated_at=NOW() WHERE id=$4 AND tenant_id=$5""",
        merged, new_status, changes, kickoff["id"], kickoff["tenant_id"],
    )
    kickoff = await _get_kickoff_or_404(kickoff["id"], user["tenant_id"])
    block3_ok, _ = _block3_ready(merged)
    if block3_ok:
        await _enqueue_after_block3(kickoff, user)
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="kickoff_bloco3_updated",
        entity_type="kickoff",
        entity_id=kickoff["id"],
        before=existing,
        after=merged,
    )
    return await _decorate_kickoff(kickoff)


@kickoff_router.put("/kickoff/{kickoff_id}/bloco4")
async def update_kickoff_bloco4(kickoff_id: str, data: KickoffBloco4Input, request: Request):
    user = await get_current_user(request)
    require_roles(user, BLOCK_4_ROLES)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    _validate_kickoff_editable(kickoff)
    kickoff = await _ensure_mutable_version(kickoff, user, "Alteracao no Bloco 4 apos aprovacao")
    existing = kickoff.get("bloco4") or {}
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    merged = {**existing, **updates}
    _validate_block3_vs_block4(kickoff.get("bloco3") or {}, merged)
    changes = _diff_entries("bloco4", existing, merged, user)
    await pg_db.execute(
        """UPDATE kickoffs SET bloco4=$1, status='aguardando_aprovacao',
           log_auditoria = COALESCE(log_auditoria,'[]'::jsonb) || $2::jsonb,
           updated_at=NOW() WHERE id=$3 AND tenant_id=$4""",
        merged, changes, kickoff["id"], kickoff["tenant_id"],
    )
    kickoff = await _get_kickoff_or_404(kickoff["id"], user["tenant_id"])
    kickoff = await _refresh_bom(kickoff)
    await _create_homologation_tasks_for_bom(kickoff, user)
    await _enqueue_approval_task(kickoff, user, "lider_pd")
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="kickoff_bloco4_updated",
        entity_type="kickoff",
        entity_id=kickoff["id"],
        before=existing,
        after=merged,
        metadata={"bom_lines": len(kickoff.get("bom", []))},
    )
    return await _decorate_kickoff(kickoff)


@kickoff_router.get("/kickoff/{kickoff_id}/bom")
async def get_kickoff_bom(kickoff_id: str, request: Request):
    user = await get_current_user(request)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    kickoff = await _refresh_bom(kickoff)
    return kickoff.get("bom", [])


@kickoff_router.post("/kickoff/{kickoff_id}/bom/export")
async def export_kickoff_bom(kickoff_id: str, data: BomExportInput, request: Request):
    user = await get_current_user(request)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    kickoff = await _refresh_bom(kickoff)
    bom = kickoff.get("bom", [])
    formato = (data.formato or "csv").lower()
    if formato == "pdf":
        buffer = io.BytesIO()
        pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("KickoffBOMTitle", parent=styles["Title"], fontSize=18, textColor=rl_colors.HexColor("#111827"))
        body_style = ParagraphStyle("KickoffBOMBody", parent=styles["BodyText"], fontSize=9)
        rows = [["Codigo", "Descricao", "Tipo", "Fornecedor", "Qtd/Un", "Qtd Pedido", "Status"]]
        for line in bom:
            rows.append(
                [
                    str(line.get("codigo_interno", "")),
                    str(line.get("descricao", "")),
                    str(line.get("tipo", "")),
                    str((line.get("fornecedor_principal") or {}).get("nome", "")),
                    str(line.get("quantidade_por_unidade", "")),
                    str(line.get("quantidade_total_pedido", "")),
                    str(line.get("status_homologacao", "")),
                ]
            )
        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#E5E7EB")),
                    ("GRID", (0, 0), (-1, -1), 0.25, rl_colors.HexColor("#D1D5DB")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements = [
            Paragraph(f"BOM Kickoff {kickoff['numero_kickoff']} {kickoff['versao']}", title_style),
            Spacer(1, 4 * mm),
            Paragraph(f"Cliente: {kickoff.get('bloco1', {}).get('cliente', '')}", body_style),
            Spacer(1, 4 * mm),
            table,
        ]
        pdf.build(elements)
        buffer.seek(0)
        filename = f"bom_{kickoff['numero_kickoff']}_{kickoff['versao']}.pdf"
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    text_buffer = io.StringIO()
    writer = csv.writer(text_buffer)
    writer.writerow(["codigo_interno", "descricao", "tipo", "fornecedor_principal", "unidade", "quantidade_por_unidade", "quantidade_total_pedido", "status_homologacao"])
    for line in bom:
        writer.writerow(
            [
                line.get("codigo_interno", ""),
                line.get("descricao", ""),
                line.get("tipo", ""),
                (line.get("fornecedor_principal") or {}).get("nome", ""),
                line.get("unidade", ""),
                line.get("quantidade_por_unidade", ""),
                line.get("quantidade_total_pedido", ""),
                line.get("status_homologacao", ""),
            ]
        )
    byte_buffer = io.BytesIO(text_buffer.getvalue().encode("utf-8"))
    filename = f"bom_{kickoff['numero_kickoff']}_{kickoff['versao']}.csv"
    return StreamingResponse(
        byte_buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@kickoff_router.post("/kickoff/{kickoff_id}/aprovacao")
async def approve_kickoff(kickoff_id: str, data: KickoffApprovalInput, request: Request):
    user = await get_current_user(request)
    kickoff = await _get_kickoff_or_404(kickoff_id, user["tenant_id"])
    if data.etapa not in APPROVAL_SEQUENCE:
        raise HTTPException(status_code=400, detail="Etapa de aprovacao invalida")
    if data.decisao not in {"aprovado", "reprovado"}:
        raise HTTPException(status_code=400, detail="Decisao invalida")
    require_roles(user, APPROVAL_ROLE_MAP[data.etapa])
    kickoff = await _refresh_bom(kickoff)
    await _validate_kickoff_ready_for_approval(kickoff)

    current_step = _current_approval_step(kickoff)
    if not current_step:
        raise HTTPException(status_code=409, detail="O fluxo de aprovacao deste Kickoff ja foi concluido.")
    if current_step["etapa"] != data.etapa:
        raise HTTPException(
            status_code=409,
            detail=f"Etapa atual de aprovacao: {APPROVAL_LABELS[current_step['etapa']]}. Nao e permitido pular etapas.",
        )
    if data.decisao == "reprovado" and not data.justificativa:
        raise HTTPException(status_code=400, detail="Justificativa obrigatoria quando a decisao for reprovado.")

    updated_steps = []
    for step in kickoff.get("aprovacoes", []):
        if step["etapa"] == data.etapa:
            updated_steps.append(
                {
                    **step,
                    "status": "concluida" if data.decisao == "aprovado" else "reprovada",
                    "decisao": data.decisao,
                    "justificativa": data.justificativa or "",
                    "observacoes": data.observacoes or "",
                    "decidido_por": user["id"],
                    "decidido_por_nome": user.get("name", ""),
                    "decidido_em": now_iso(),
                }
            )
        else:
            updated_steps.append(step)

    status = kickoff.get("status", "aguardando_aprovacao")
    generated_docs: List[Dict[str, Any]] = []
    if data.decisao == "reprovado":
        status = "em_preenchimento"
    else:
        next_index = APPROVAL_SEQUENCE.index(data.etapa) + 1
        if next_index >= len(APPROVAL_SEQUENCE):
            status = "aprovado"
            generated_docs = await _mark_pd_request_kickoff_complete(kickoff, user)
        else:
            status = "aguardando_aprovacao"

    now = now_iso()
    log_entry = {
        "campo": f"aprovacao.{data.etapa}",
        "valor_anterior": "pendente",
        "valor_novo": data.decisao,
        "usuario_id": user["id"],
        "usuario_nome": user.get("name", ""),
        "datetime": now,
        "observacoes": data.observacoes or "",
        "justificativa": data.justificativa or "",
    }
    await pg_db.execute(
        """UPDATE kickoffs SET aprovacoes=$1, status=$2, updated_at=NOW(),
           approved_at=$3, approved_by=$4, approved_by_name=$5,
           log_auditoria = COALESCE(log_auditoria,'[]'::jsonb) || $6::jsonb
           WHERE id=$7 AND tenant_id=$8""",
        updated_steps, status,
        now if status == "aprovado" else kickoff.get("approved_at"),
        user["id"] if status == "aprovado" else kickoff.get("approved_by"),
        user.get("name", "") if status == "aprovado" else kickoff.get("approved_by_name", ""),
        [log_entry], kickoff["id"], kickoff["tenant_id"],
    )
    kickoff = await _get_kickoff_or_404(kickoff["id"], user["tenant_id"])
    await _sync_project_kickoff_summary(kickoff)
    if data.decisao == "reprovado":
        await _enqueue_revision_task(kickoff, user, data.etapa)
    elif status != "aprovado":
        await _enqueue_approval_task(kickoff, user, APPROVAL_SEQUENCE[APPROVAL_SEQUENCE.index(data.etapa) + 1])
    else:
        await _create_or_reuse_task(
            kickoff=kickoff,
            title=f"Gerar EPA do Kickoff {kickoff['numero_kickoff']}",
            task_code="gerar_epa",
            category="pd_dev",
            due_in_days=2,
            created_by=user,
            responsible_roles=["lider_pd", "qa", "engenharia_produto", "admin"],
            description="Kickoff aprovado: EPA foi disparado e precisa seguir fluxo de revisao.",
            blocking=False,
        )
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="kickoff_approval_decision",
        entity_type="kickoff",
        entity_id=kickoff["id"],
        before={"status": kickoff.get("status"), "etapa": data.etapa},
        after={"status": status, "etapa": data.etapa, "decisao": data.decisao},
        metadata={"generated_docs": generated_docs},
    )
    decorated = await _decorate_kickoff(kickoff)
    decorated["documentos_gerados"] = generated_docs
    return decorated
