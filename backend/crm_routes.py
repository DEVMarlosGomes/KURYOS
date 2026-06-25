"""
CRM Routes - Kuryos Beauty CRM
3-level pipeline: Clients (CRM1) → Projects (CRM2) → Samples (CRM3) → SKU
"""

from fastapi import APIRouter, HTTPException, Request, Query, File, UploadFile
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import logging
import asyncio
import os
import base64
import json
from pathlib import Path
import database as pg_db
from validation_utils import (
    clean_text,
    normalize_cnpj,
    normalize_email,
    normalize_phone,
    is_valid_cnpj,
    is_valid_email,
    is_valid_phone,
)

from workflow_engine import (
    audit_log,
    create_workflow_task,
    next_sample_number,
    next_sample_code,
    int_to_letters,
    next_sku_number,
    next_sku_per_pair,
    next_sku_per_pair_v2,
    build_sku_code_v2,
    cat2_from_categoria,
    cat3_from_categoria,
    normalise_cli3,
    normalise_cli4,
    suggest_cli4_candidates,
    recalc_sku_averages,
    assert_client_exists,
    assert_project_exists,
    assert_sample_exists,
    assert_no_blocking_tasks,
    trigger_tasks_for_transition,
    inherit,
    INHERITED_FROM_CLIENT,
    INHERITED_FROM_PROJECT,
    INHERITED_FROM_SAMPLE,
)
from rbac import (
    require_roles,
    has_role,
    COMERCIAL_FULL,
    COMERCIAL_LEAD,
    PD_READ,
    PD_WRITE,
    PD_FULL,
    QA_APPROVERS,
    DOC_REVIEWERS,
    ADMIN_ONLY,
)

logger = logging.getLogger(__name__)

crm_router = APIRouter(prefix="/api/crm")

# ============ MODULE STATE (set via init) ============
db = None
_get_current_user = None
_new_id = None
_now_iso = None
_broadcast_event = None

def init_crm(database, get_user_fn, new_id_fn, now_iso_fn, broadcast_event_fn=None):
    global db, _get_current_user, _new_id, _now_iso, _broadcast_event
    db = database
    _get_current_user = get_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn
    _broadcast_event = broadcast_event_fn
    logger.info("CRM module initialized")

# ============ CONSTANTS ============

CLIENT_STAGES = ["prospeccao", "qualificado", "projeto_em_discussao", "negociacao", "cliente_fechado", "cliente_perdido"]

CLIENT_TRANSITIONS = {
    "prospeccao": ["qualificado", "cliente_perdido"],
    "qualificado": ["projeto_em_discussao", "prospeccao", "cliente_perdido"],
    "projeto_em_discussao": ["negociacao", "qualificado", "prospeccao", "cliente_perdido"],
    "negociacao": ["cliente_fechado", "projeto_em_discussao", "qualificado", "prospeccao", "cliente_perdido"],
    "cliente_fechado": ["negociacao", "projeto_em_discussao", "qualificado", "prospeccao"],
    "cliente_perdido": ["prospeccao"],
}

# Stages where moving backward is considered a regression (requires justification)
_CLIENT_STAGE_ORDER = ["prospeccao", "qualificado", "projeto_em_discussao", "negociacao", "cliente_fechado", "cliente_perdido"]

PROJECT_STAGES = [
    "projeto_em_discussao",
    "amostra_solicitada",
    "amostra_em_desenvolvimento",
    "amostra_enviada",
    "em_negociacao",
    "pedido_aprovado",
    "projeto_arquivado",
]

PROJECT_TRANSITIONS = {
    "projeto_em_discussao": ["amostra_solicitada", "projeto_arquivado"],
    "amostra_solicitada": ["amostra_em_desenvolvimento", "projeto_arquivado"],
    "amostra_em_desenvolvimento": ["amostra_enviada", "projeto_arquivado"],
    "amostra_enviada": ["em_negociacao", "projeto_arquivado"],
    "em_negociacao": ["pedido_aprovado", "projeto_arquivado"],
    "pedido_aprovado": [],
    "projeto_arquivado": [],
    # legado
    "amostras": ["amostra_em_desenvolvimento", "projeto_arquivado"],
}

SAMPLE_STAGES = ["solicitada", "em_elaboracao", "retrabalho", "enviada", "aprovada", "reprovada"]

SAMPLE_TRANSITIONS = {
    "solicitada": ["em_elaboracao"],
    "em_elaboracao": ["enviada", "retrabalho"],
    "retrabalho": ["em_elaboracao"],
    "enviada": ["aprovada", "reprovada", "retrabalho"],
    "aprovada": [],
    "reprovada": [],
}

CANAL_ORIGEM_OPTIONS = [
    # Prospecção Ativa — Digital
    "linkedin_dm_outbound",
    "linkedin_engajamento_organico",
    "instagram_abordagem_direta",
    "whatsapp_abordagem_fria",
    "email_outbound_automatizado",
    "email_outbound_manual",
    # Prospecção Ativa — Presencial
    "evento",
    "feira_setor",
    "visita_presencial_espontanea",
    "abordagem_pdv",
    # Indicação
    "indicacao_cliente_ativo",
    "indicacao_fornecedor_parceiro",
    "indicacao_ex_cliente",
    "indicacao_pessoal",
    "indicacao_influenciador_parceiro_midia",
    # Inbound — Digital
    "formulario_site",
    "whatsapp_receptivo",
    "instagram_dm_receptivo",
    "linkedin_inbound",
    "google_organico",
    "google_ads",
    "meta_ads",
    # Inbound — Conteúdo
    "blog",
    "seo",
    "newsletter",
    "youtube",
    "webinar_live",
    # Relacionamento Existente
    "reativacao_lead_frio",
    "reativacao_ex_cliente",
    "cross_sell_cliente_ativo",
    "upsell_cliente_ativo",
    # Outros
    "parceria_cobrand",
    "consultor_agencia",
    "licitacao_edital",
    "outro",
]

# Categorias de Interesse 2 níveis conforme PRD
CATEGORIA_INTERESSE_OPTIONS = {
    "capilares": ["shampoo", "condicionador", "mascara_capilar", "leave_in_finalizador", "oleo_capilar", "ampola_tratamento", "tonico_capilar", "coloracao_tonalizante", "relaxante_alisante", "neutralizante", "botox_capilar", "progressiva_escova"],
    "skin_care_dermocosmeticos": ["hidratante_corporal", "hidratante_facial", "serum_facial", "protetor_solar_facial", "protetor_solar_corporal", "esfoliante", "tonico_facial", "sabonete_liquido_facial", "mascara_facial", "contorno_olhos", "vitamina_c_antioxidante", "clareador", "antiacneico"],
    "higiene_pessoal": ["sabonete_liquido_corporal", "sabonete_em_barra", "gel_banho", "desodorante_spray", "desodorante_rollon", "desodorante_creme", "talco", "antisseptico_maos"],
    "perfumaria": ["perfume_edp", "eau_de_toilette", "body_splash_colonia", "splash_capilar", "home_spray_aromatizador", "sache_perfumado", "sabonete_perfumado"],
    "maquiagem": ["base_liquida", "bb_cream_cc_cream", "primer", "blush_bronzer", "iluminador", "batom_gloss", "delineador", "mascara_cilios", "fixador"],
    "corporal_spa": ["oleo_corporal", "manteiga_corporal", "esfoliante_corporal", "creme_maos_pes", "creme_estrias", "gel_redutor", "creme_pos_depilacao", "creme_massagem"],
    "infantil": ["shampoo_infantil", "condicionador_infantil", "sabonete_infantil", "locao_infantil", "protetor_solar_infantil", "oleo_massagem_infantil"],
    "masculino": ["shampoo_masculino", "balsamo_pos_barba", "gel_creme_barbear", "locao_pos_barba", "desodorante_masculino", "perfume_masculino", "hidratante_facial_masculino"],
    "profissional_salao": ["tratamento_intensivo", "progressiva_escova", "coloracao_profissional", "tonalizante", "alisamento", "neutralizante_profissional"],
    "regulatorio_grau2": ["protetor_solar_fps6", "repelente_insetos", "clareador_pele", "antiacneico", "ativo_farmacologico"],
}

# Campos que indicam produto Grau 2 ANVISA
CATEGORIAS_GRAU2 = ["protetor_solar_facial", "protetor_solar_corporal", "protetor_solar_fps6", "protetor_solar_infantil", "repelente_insetos", "clareador", "clareador_pele", "antiacneico", "ativo_farmacologico"]

ORIGEM_LEAD_OPTIONS = [
    "indicacao_cliente_habibi",
    "indicacao_fornecedor",
    "indicacao_parceiro",
    "feira_setor",
    "evento",
    "linkedin",
    "instagram",
    "google",
    "site",
    "outro",
]

VOLUME_ESTIMADO_OPTIONS = ["menos_1k", "1k_5k", "5k_20k", "20k_50k", "50k_100k", "mais_100k"]

TEM_ANVISA_OPTIONS = ["sim", "nao", "depende"]

MOTIVO_PERDA_OPTIONS = ["preco", "prazo", "qualidade", "concorrencia", "projeto_cancelado", "sem_retorno", "outro"]

# Segmentos de cliente
SEGMENTO_CLIENTE_OPTIONS = ["marca_propria", "distribuidor", "varejo", "salao", "industria", "outro"]

# Porte do cliente
PORTE_CLIENTE_OPTIONS = ["pequeno", "medio", "grande"]

# Temperatura do lead
TEMPERATURA_LEAD_OPTIONS = ["quente", "morno", "frio"]

# Cargos de decisores
CARGO_DECISOR_OPTIONS = ["ceo", "comprador", "desenvolvimento", "diretor_comercial", "gerente_produto", "outro"]

UF_OPTIONS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]

CANAL_ORIGEM_GROUPS = {
    "prospeccao_ativa_digital": [
        "linkedin_dm_outbound",
        "linkedin_engajamento_organico",
        "instagram_abordagem_direta",
        "whatsapp_abordagem_fria",
        "email_outbound_automatizado",
        "email_outbound_manual",
    ],
    "prospeccao_ativa_presencial": [
        "evento",
        "feira_setor",
        "visita_presencial_espontanea",
        "abordagem_pdv",
    ],
    "indicacao": [
        "indicacao_cliente_ativo",
        "indicacao_fornecedor_parceiro",
        "indicacao_ex_cliente",
        "indicacao_pessoal",
        "indicacao_influenciador_parceiro_midia",
    ],
    "inbound_digital": [
        "formulario_site",
        "whatsapp_receptivo",
        "instagram_dm_receptivo",
        "linkedin_inbound",
        "google_organico",
        "google_ads",
        "meta_ads",
    ],
    "inbound_conteudo": [
        "blog",
        "seo",
        "newsletter",
        "youtube",
        "webinar_live",
    ],
    "relacionamento_existente": [
        "reativacao_lead_frio",
        "reativacao_ex_cliente",
        "cross_sell_cliente_ativo",
        "upsell_cliente_ativo",
    ],
    "outros": [
        "parceria_cobrand",
        "consultor_agencia",
        "licitacao_edital",
        "outro",
    ],
}

# Prazo de follow-up por etapa (em dias)
FOLLOW_UP_PRAZOS = {
    "prospeccao": 3,
    "qualificado": 5,
    "projeto_em_discussao": 7,
    "negociacao": 5,
    "cliente_fechado": 30,
    "cliente_perdido": 90,
}

PROJECT_POSICIONAMENTO_OPTIONS = [
    "custo_beneficio",
    "premium",
    "luxo",
    "acessivel",
    "nicho",
    "profissional",
]

PROJECT_TIPO_SERVICO_OPTIONS = [
    "full_service_kuryos",
    "co_desenvolvimento",
    "formula_do_cliente",
]

PROJECT_RESTRICAO_TECNICA_OPTIONS = [
    "vegano",
    "sem_parabenos",
    "sem_sulfato",
    "sem_silicone",
    "hipoalergenico",
    "natural",
    "organico",
    "anvisa_g2",
    "outro",
]

TIPO_AMOSTRA_OPTIONS = [
    "desenvolvimento_novo",
    "portfolio_existente",
    "adaptacao_de_formula",
]

UNIDADE_QUANTIDADE_AMOSTRA_OPTIONS = ["g", "kg", "ml", "l", "un"]

SAMPLE_VARIATION_PARAM_OPTIONS = [
    "fragrancia",
    "cor",
    "ativo",
    "outro",
]

SAMPLE_RESULTADO_OPTIONS = [
    "aprovada",
    "reprovada",
    "retrabalho",
]

STAGE_LABELS = {
    "prospeccao": "Prospecção",
    "qualificado": "Qualificado",
    "projeto_em_discussao": "Projeto em Discussão",
    "negociacao": "Negociação",
    "cliente_fechado": "Cliente Fechado",
    "cliente_perdido": "Cliente Perdido",
    "amostras": "Amostra Solicitada",
    "amostra_solicitada": "Amostra Solicitada",
    "amostra_em_desenvolvimento": "Amostra em Desenvolvimento",
    "amostra_enviada": "Amostra Enviada ao Cliente",
    "em_negociacao": "Em Negociação",
    "pedido_aprovado": "Pedido Aprovado",
    "projeto_arquivado": "Projeto Arquivado",
    "solicitada": "Solicitada",
    "em_elaboracao": "Em Elaboração",
    "retrabalho": "Retrabalho",
    "enviada": "Enviada",
    "aprovada": "Aprovada",
    "reprovada": "Reprovada",
}

# ============ PYDANTIC MODELS ============

class ContatoPrincipal(BaseModel):
    nome: str = ""
    cargo: str = ""
    cargo_custom: Optional[str] = None
    whatsapp: str = ""
    email: str = ""

class ContatoAdicional(BaseModel):
    nome: str = ""
    cargo: str = ""
    cargo_custom: Optional[str] = None
    whatsapp: str = ""
    email: str = ""

class Decisor(BaseModel):
    nome: str = ""
    cargo: str = ""
    contato: str = ""

class FornecedorAtual(BaseModel):
    tem: bool = False
    motivo_troca: str = ""

class AnvisaInfo(BaseModel):
    necessario: bool = False
    status: str = ""

class ClientCreate(BaseModel):
    nome_empresa: str
    cnpj: str = ""
    contato_principal: Optional[ContatoPrincipal] = None
    contatos_adicionais: List[ContatoAdicional] = []
    canal_origem: str = ""
    categoria_interesse: List[str] = []
    origem_lead: str = ""
    # Novos campos PRD
    temperatura_lead: str = "morno"
    responsavel_comercial: str = ""
    segmento: str = ""
    porte: str = ""
    regiao: str = ""
    site: str = ""
    instagram: str = ""
    observacoes: str = ""
    # SKU identifiers
    cli3: str = ""
    cli4: str = ""  # R23: 4-letter code — auto-suggested from nome_empresa if empty
    # Qualificação — opcionais na criação, permitem auto-completar blocking task
    decisores: List[Decisor] = []
    tem_anvisa: str = ""
    volume_estimado_mensal: str = ""
    fornecedor_atual: Optional[FornecedorAtual] = None


class ClientUpdate(BaseModel):
    nome_empresa: Optional[str] = None
    cnpj: Optional[str] = None
    contato_principal: Optional[ContatoPrincipal] = None
    contatos_adicionais: Optional[List[ContatoAdicional]] = None
    canal_origem: Optional[str] = None
    categoria_interesse: Optional[List[str]] = None
    origem_lead: Optional[str] = None
    decisores: Optional[List[Decisor]] = None
    tem_marca_propria: Optional[bool] = None
    tem_anvisa: Optional[str] = None
    volume_estimado_mensal: Optional[str] = None
    fornecedor_atual: Optional[FornecedorAtual] = None
    prazo_urgencia: Optional[str] = None
    amostras_aprovadas: Optional[List[str]] = None
    valor_estimado_projeto: Optional[float] = None
    valor_estimado_projeto_currency: Optional[str] = None
    moq_negociado: Optional[str] = None
    condicao_pagamento: Optional[str] = None
    anvisa_necessario: Optional[AnvisaInfo] = None
    concorrentes_envolvidos: Optional[List[str]] = None
    data_pedido: Optional[str] = None
    skus_confirmados: Optional[List[str]] = None
    valor_primeiro_pedido: Optional[float] = None
    valor_primeiro_pedido_currency: Optional[str] = None
    previsao_segundo_pedido: Optional[str] = None
    motivo_perda: Optional[str] = None
    # Novos campos PRD
    temperatura_lead: Optional[str] = None
    responsavel_comercial: Optional[str] = None
    segmento: Optional[str] = None
    porte: Optional[str] = None
    regiao: Optional[str] = None
    site: Optional[str] = None
    instagram: Optional[str] = None
    observacoes: Optional[str] = None
    ultima_atualizacao_temperatura: Optional[str] = None
    cli3: Optional[str] = None
    cli4: Optional[str] = None  # R23: frozen after first SKU

class ClientMove(BaseModel):
    stage: str
    motivo_perda: Optional[str] = None
    justificativa: Optional[str] = None

class ProjectBatchItem(BaseModel):
    nome_projeto: str
    categoria: str = ""
    briefing_resumido: str = ""
    responsavel_comercial: str = ""
    ideia_conceito: str = ""
    referencia_mercado: str = ""
    publico_alvo: str = ""
    posicionamento: str = ""
    faixa_preco_venda: Optional[float] = None
    volume_estimado_pedido: Optional[int] = None
    tipo_servico: str = ""
    sensorial_desejado: str = ""
    restricoes_tecnicas: List[str] = []
    claims_desejados: str = ""
    prazo_desejado_amostra: str = ""
    observacoes_livres: str = ""

class ProjectBatchCreate(BaseModel):
    cliente_id: str
    projects: List[ProjectBatchItem]

class ProjectUpdate(BaseModel):
    nome_projeto: Optional[str] = None
    categoria: Optional[str] = None
    briefing_tecnico: Optional[str] = None
    responsavel_comercial: Optional[str] = None
    ideia_conceito: Optional[str] = None
    referencia_mercado: Optional[str] = None
    publico_alvo: Optional[str] = None
    posicionamento: Optional[str] = None
    faixa_preco_venda: Optional[float] = None
    volume_estimado_pedido: Optional[int] = None
    tipo_servico: Optional[str] = None
    sensorial_desejado: Optional[str] = None
    restricoes_tecnicas: Optional[List[str]] = None
    claims_desejados: Optional[str] = None
    prazo_desejado_amostra: Optional[str] = None
    observacoes_livres: Optional[str] = None
    responsavel_interno: Optional[str] = None
    data_inicio_desenvolvimento: Optional[str] = None
    prazo_prometido_cliente: Optional[str] = None
    numero_amostras_solicitadas: Optional[int] = None
    motivo_arquivamento: Optional[str] = None

class ProjectMove(BaseModel):
    stage: str
    motivo_arquivamento: Optional[str] = None

class SampleBatchItem(BaseModel):
    nome_amostra: str
    codigo_referencia: str = ""
    observacao_tecnica: str = ""
    tipo_amostra: str = "nova_formula"
    referencia_formula: str = ""
    produto: str = ""
    objetivo_projeto: str = ""
    aplicacoes_desenvolver: str = ""
    ativos_claims: str = ""
    referencias: str = ""
    referencias_fotos: List[str] = []
    orcamento_projeto: str = ""
    textura_esperada: str = ""
    aplicacao: str = ""
    sensorial: str = ""
    ph: str = ""

class SampleBatchCreate(BaseModel):
    projeto_id: str
    samples: List[SampleBatchItem]

class SampleUpdate(BaseModel):
    nome_amostra: Optional[str] = None
    codigo_referencia: Optional[str] = None
    observacao_tecnica: Optional[str] = None
    responsavel_pd: Optional[str] = None
    data_envio: Optional[str] = None
    feedback_cliente: Optional[str] = None
    direcoes_retrabalho: Optional[str] = None
    prazo_entrega_cliente: Optional[str] = None
    tipo_amostra: Optional[str] = None
    referencia_formula: Optional[str] = None
    quantidade_por_variacao: Optional[float] = None
    unidade_quantidade: Optional[str] = None
    briefing_especifico: Optional[str] = None
    resultado: Optional[str] = None
    produto: Optional[str] = None
    objetivo_projeto: Optional[str] = None
    aplicacoes_desenvolver: Optional[str] = None
    ativos_claims: Optional[str] = None
    referencias: Optional[str] = None
    referencias_fotos: Optional[List[str]] = None
    orcamento_projeto: Optional[str] = None
    textura_esperada: Optional[str] = None
    aplicacao: Optional[str] = None
    sensorial: Optional[str] = None
    ph: Optional[str] = None

class SampleMove(BaseModel):
    stage: str
    motivo_retrabalho: Optional[str] = None
    origem_retrabalho: Optional[str] = None
    feedback_cliente: Optional[str] = None
    direcoes_retrabalho: Optional[str] = None

class VariacaoItem(BaseModel):
    descricao_aplicacao: str
    percentual_fragrancia: Optional[float] = None
    referencia_fragrancia: str = ""   # R07: deve seguir padrão "FR-NNNNN - Nome"
    fr_codigo: str = ""               # R08: código interno do cadastro db.fragrancias
    custo_fragrancia: Optional[float] = None
    custo_fragrancia_currency: str = "BRL"
    observacoes_especificas: str = ""
    feedback_cliente: str = ""
    direcoes_retrabalho: str = ""

class SampleBatchItemV2(BaseModel):
    """Nova versão com suporte a variações"""
    nome_produto: str
    categoria: str = ""
    briefing_base: str = ""
    responsavel_pd: str = ""
    parametro_variacao: str = ""
    tipo_amostra: str = ""
    referencia_formula: str = ""
    quantidade_por_variacao: Optional[float] = None
    unidade_quantidade: str = "g"
    prazo_entrega_cliente: str = ""
    briefing_especifico: str = ""
    feedback_cliente: str = ""
    direcoes_retrabalho: str = ""
    resultado: str = ""
    # Campos de briefing herdados
    produto: str = ""
    objetivo_projeto: str = ""
    aplicacoes_desenvolver: str = ""
    ativos_claims: str = ""
    referencias: str = ""
    referencias_fotos: List[str] = []
    orcamento_projeto: str = ""
    textura_esperada: str = ""
    aplicacao: str = ""
    sensorial: str = ""
    ph: str = ""
    observacao_tecnica: str = ""
    # Variações
    variacoes: List[VariacaoItem] = []

class SampleBatchCreateV2(BaseModel):
    projeto_id: str
    samples: List[SampleBatchItemV2]
    # R02: campos do card a atualizar no projeto antes de criar amostras
    projeto_updates: Optional[dict] = None

class VariacaoUpdate(BaseModel):
    descricao_aplicacao: Optional[str] = None
    percentual_fragrancia: Optional[float] = None
    referencia_fragrancia: Optional[str] = None
    custo_fragrancia: Optional[float] = None
    custo_fragrancia_currency: Optional[str] = None
    observacoes_especificas: Optional[str] = None
    feedback_cliente: Optional[str] = None

class VariacaoMove(BaseModel):
    status: str
    motivo_retrabalho: Optional[str] = None
    origem_retrabalho: Optional[str] = None
    feedback_cliente: Optional[str] = None
    direcoes_retrabalho: Optional[str] = None

class SKUUpdate(BaseModel):
    preco_unitario: Optional[float] = None
    preco_unitario_currency: Optional[str] = None
    moq: Optional[int] = None
    anvisa_numero: Optional[str] = None
    anvisa_validade: Optional[str] = None
    status: Optional[str] = None
    nome_produto: Optional[str] = None

class SKUMetaUpdate(BaseModel):
    meta_unh: Optional[float] = None
    ajuste_percentual: Optional[float] = None  # -100 to +100

class SKUDescontinuar(BaseModel):
    motivo: str

class OrderAdd(BaseModel):
    data_pedido: str
    quantidade: int
    valor_total: float
    observacao: str = ""

class AlertResolve(BaseModel):
    comment: str = ""

class FollowUpSchedule(BaseModel):
    """Agendamento de follow-up manual (RN-FU-03)"""
    client_id: str
    data_follow_up: str  # ISO datetime
    observacao: str = ""

# ============ HELPER ============

def _row(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    return d

def _rows(rows) -> list:
    return [_row(r) for r in (rows or [])]

async def _update_variacao_in_sample(sample_id: str, tenant_id: str, variacao_id: str, updates: dict) -> None:
    """Load sample variacoes, update the matching variacao in Python, save back."""
    row = _row(await pg_db.fetch_one(
        "SELECT variacoes FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, tenant_id
    ))
    if not row:
        return
    variacoes = row.get("variacoes") or []
    for v in variacoes:
        if v.get("id") == variacao_id:
            v.update(updates)
            break
    await pg_db.execute(
        "UPDATE crm_samples SET variacoes=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        variacoes, sample_id, tenant_id
    )

async def _push_variacao_history(sample_id: str, tenant_id: str, variacao_id: str, entry: dict) -> None:
    """Append entry to variacoes[i].historico_status inside JSONB."""
    row = _row(await pg_db.fetch_one(
        "SELECT variacoes FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, tenant_id
    ))
    if not row:
        return
    variacoes = row.get("variacoes") or []
    for v in variacoes:
        if v.get("id") == variacao_id:
            hist = v.get("historico_status") or []
            hist.append(entry)
            v["historico_status"] = hist
            break
    await pg_db.execute(
        "UPDATE crm_samples SET variacoes=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        variacoes, sample_id, tenant_id
    )

def _serialize(doc: dict) -> dict:
    """Remove MongoDB _id from doc"""
    if doc:
        doc.pop("_id", None)
    return doc

async def _get_next_sample_code(projeto_id: str, tenant_id: str) -> str:
    """Retorna o próximo código de amostra GLOBAL no formato {ANO}-{NNNN} (ERP v3.0)."""
    return await next_sample_code(tenant_id)


async def _resolve_cli4(tenant_id: str, requested: str, nome_empresa: str) -> str:
    """
    Return the CLI4 to use for a new client.
    - If `requested` is provided and unique: use it.
    - If `requested` is empty: auto-suggest from `nome_empresa`.
    - Raises HTTPException 409 if the requested code conflicts.
    """
    if requested:
        code = normalise_cli4(requested)
        conflict = _row(await pg_db.fetch_one(
            "SELECT nome_empresa FROM crm_clients WHERE tenant_id=$1 AND cli4=$2",
            tenant_id, code
        ))
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"CLI4 '{code}' já está em uso pelo cliente '{conflict['nome_empresa']}'"
            )
        return code

    # Auto-suggest from name
    candidates = suggest_cli4_candidates(nome_empresa)
    for code in candidates:
        conflict = _row(await pg_db.fetch_one(
            "SELECT id FROM crm_clients WHERE tenant_id=$1 AND cli4=$2",
            tenant_id, code
        ))
        if not conflict:
            return code
    # Fallback: first candidate even if occupied (caller can update later)
    return candidates[0] if candidates else normalise_cli4(nome_empresa)

LEGACY_PROJECT_STAGE_ALIASES = {
    "amostras": "amostra_solicitada",
}

def _normalize_project_stage(stage: Optional[str]) -> Optional[str]:
    if not stage:
        return stage
    return LEGACY_PROJECT_STAGE_ALIASES.get(stage, stage)

def _project_stage_rank(stage: Optional[str]) -> int:
    normalized = _normalize_project_stage(stage)
    order = [
        "projeto_em_discussao",
        "amostra_solicitada",
        "amostra_em_desenvolvimento",
        "amostra_enviada",
        "em_negociacao",
        "pedido_aprovado",
        "projeto_arquivado",
    ]
    try:
        return order.index(normalized)
    except ValueError:
        return -1

def _business_days_before(date_str: str, days: int) -> Optional[datetime]:
    if not date_str:
        return None
    raw = clean_text(date_str)
    if not raw:
        return None
    try:
        target = datetime.fromisoformat(raw)
    except ValueError:
        try:
            target = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None
    current = target
    remaining = max(days, 0)
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current

def _days_until(target: Optional[datetime]) -> Optional[int]:
    if not target:
        return None
    now = datetime.now()
    delta = target - now
    return max(delta.days, 0)

async def _create_project_deadline_alert_task(project: dict, user: dict):
    prazo = clean_text(project.get("prazo_desejado_amostra", ""))
    if not prazo:
        return None
    alert_date = _business_days_before(prazo, 3)
    if not alert_date:
        return None
    due_in_days = _days_until(alert_date)
    existing = await db.workflow_tasks.find_one(
        {
            "tenant_id": user["tenant_id"],
            "entity_type": "project",
            "entity_id": project["id"],
            "title": "Prazo-alvo da amostra em 3 dias uteis",
            "status": {"$in": ["pendente", "em_andamento"]},
        },
        {"_id": 0},
    )
    if existing:
        return existing
    return await create_workflow_task(
        tenant_id=user["tenant_id"],
        entity_type="project",
        entity_id=project["id"],
        title="Prazo-alvo da amostra em 3 dias uteis",
        description=f"Alerta automatico para o prazo desejado de amostra ({prazo}).",
        category="projeto",
        blocking=False,
        due_in_days=due_in_days if due_in_days is not None else 0,
        responsible_id=project.get("responsavel_comercial") or project.get("created_by"),
        created_by=user,
        metadata={
            "trigger": "prazo_desejado_amostra",
            "prazo_desejado_amostra": prazo,
            "alerta_para": alert_date.date().isoformat(),
        },
    )


async def _rollback_batch_created_projects(
    tenant_id: str,
    *,
    project_ids: List[str],
    workflow_task_ids: List[str],
    audit_log_ids: List[str],
):
    if workflow_task_ids:
        await db.workflow_tasks.delete_many(
            {"tenant_id": tenant_id, "id": {"$in": workflow_task_ids}}
        )
    if audit_log_ids:
        await db.audit_logs.delete_many(
            {"tenant_id": tenant_id, "id": {"$in": audit_log_ids}}
        )
    if project_ids:
        await pg_db.execute(
            "DELETE FROM crm_projects WHERE tenant_id=$1 AND id = ANY($2::text[])",
            tenant_id, project_ids
        )


CRM_TO_PD_STATUS_MAP = {
    "solicitada": "solicitado",
    "em_elaboracao": "em_desenvolvimento",
    "enviada": "aguardando_aprovacao",
    "reprovada": "retrabalho_interno",
    "retrabalho": "retrabalho_interno",
}


async def _broadcast_pd_card_update(tenant_id: str, card: dict, old_status: str, new_status: str):
    if not _broadcast_event or not card:
        return
    await _broadcast_event(
        tenant_id,
        "pd_card_moved",
        {
            "card": card,
            "from_status": old_status,
            "to_status": new_status,
        },
    )


async def _sync_pd_cards_from_crm_stage(
    *,
    tenant_id: str,
    sample_id: str,
    user: dict,
    now: str,
    crm_stage: str,
    variacao_id: Optional[str] = None,
    feedback_cliente: str = "",
    direcoes_retrabalho: str = "",
    resultado_cliente: str = "",
):
    pd_status = CRM_TO_PD_STATUS_MAP.get(crm_stage)
    if not pd_status:
        return []

    query = {"tenant_id": tenant_id}
    if variacao_id:
        query["amostra_variacao_id"] = variacao_id
    else:
        query["amostra_id"] = sample_id

    if variacao_id:
        cards = _rows(await pg_db.fetch_all(
            "SELECT * FROM pd_cards WHERE tenant_id=$1 AND amostra_variacao_id=$2",
            tenant_id, variacao_id
        ))
    else:
        cards = _rows(await pg_db.fetch_all(
            "SELECT * FROM pd_cards WHERE tenant_id=$1 AND amostra_id=$2",
            tenant_id, sample_id
        ))
    updated_cards = []
    for card in cards:
        old_status = card.get("status_pd", "")
        history_entry = {
            "de": old_status,
            "para": pd_status,
            "data": now,
            "usuario": user["name"],
            "usuario_id": user["id"],
            "observacao": f"Sincronizado automaticamente pelo CRM: {STAGE_LABELS.get(crm_stage, crm_stage)}",
            "sincronizado_crm": True,
        }
        if resultado_cliente:
            history_entry["resultado_cliente"] = resultado_cliente
        extra_merge: dict = {}
        if feedback_cliente:
            extra_merge["feedback_cliente"] = feedback_cliente
        if direcoes_retrabalho:
            extra_merge["direcoes_retrabalho"] = direcoes_retrabalho
        if resultado_cliente:
            extra_merge["resultado_cliente"] = resultado_cliente
        await pg_db.execute(
            """UPDATE pd_cards
               SET status_pd=$1, updated_at=$2,
                   extra = jsonb_set(
                       extra || $3::jsonb,
                       '{historico_movimentacoes}',
                       COALESCE(extra->'historico_movimentacoes', '[]'::jsonb) || jsonb_build_array($4::jsonb)
                   )
               WHERE id=$5 AND tenant_id=$6""",
            pd_status, now, extra_merge, history_entry, card["id"], tenant_id
        )
        updated_card = {**card, "status_pd": pd_status, "updated_at": now}
        updated_cards.append(updated_card)
        await _broadcast_pd_card_update(tenant_id, updated_card, old_status, pd_status)

    return updated_cards

async def _advance_project_stage_if_needed(
    project_id: str,
    target_stage: str,
    user: dict,
    *,
    movement_source: str,
    extra_set: Optional[dict] = None,
):
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))
    if not project:
        return None

    old_stage = _normalize_project_stage(project.get("stage"))
    new_stage = _normalize_project_stage(target_stage)
    if not old_stage or not new_stage or old_stage == new_stage:
        return project

    allowed = [_normalize_project_stage(stage) for stage in PROJECT_TRANSITIONS.get(old_stage, [])]
    if new_stage not in allowed:
        return project

    now = _now_iso()
    movement = {
        "de": old_stage,
        "para": new_stage,
        "data": now,
        "usuario": user["name"],
        "usuario_id": user["id"],
        "origem": movement_source,
    }

    set_parts = ["stage=$1", "updated_at=$2",
                 "historico_movimentacoes = historico_movimentacoes || jsonb_build_array($3::jsonb)"]
    params: list = [new_stage, now, movement]
    if extra_set:
        for k, v in extra_set.items():
            params.append(v)
            set_parts.append(f"{k}=${len(params)}")
    params.extend([project_id, user["tenant_id"]])
    await pg_db.execute(
        f"UPDATE crm_projects SET {', '.join(set_parts)} WHERE id=${len(params)-1} AND tenant_id=${len(params)}",
        *params
    )
    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))

    new_tasks = []
    try:
        new_tasks = await trigger_tasks_for_transition(
            entity_type="project",
            entity_id=project_id,
            tenant_id=user["tenant_id"],
            old_stage=old_stage,
            new_stage=new_stage,
            user=user,
        )
    except Exception as exc:
        logger.error(f"[project_auto_move] trigger_tasks_for_transition falhou (ignorado): {exc}", exc_info=True)
    try:
        await audit_log(
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            user_name=user.get("name", ""),
            action="project_auto_moved",
            entity_type="project",
            entity_id=project_id,
            before={"stage": old_stage},
            after={"stage": new_stage},
            metadata={
                "source": movement_source,
                "tasks_generated": [task["id"] for task in new_tasks],
            },
        )
    except Exception as exc:
        logger.error(f"[project_auto_move] audit_log falhou (ignorado): {exc}", exc_info=True)
    if new_stage == "em_negociacao" and updated:
        await _mirror_client_stage_to_negociacao(updated, user)

    return updated


async def _mirror_client_stage_to_negociacao(project: dict, user: dict):
    """Quando CRM2 vai para em_negociacao, espelha o cliente no CRM1 para 'negociacao'."""
    cliente_id = project.get("cliente_id")
    if not cliente_id:
        return
    client = _row(await pg_db.fetch_one(
        "SELECT id, stage FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        cliente_id, user["tenant_id"]
    ))
    if not client:
        return
    old_stage = client.get("stage", "")
    if old_stage in ("negociacao", "cliente_fechado", "cliente_perdido"):
        return
    now = _now_iso()
    movement = {
        "de": old_stage,
        "para": "negociacao",
        "data": now,
        "usuario": user["name"],
        "usuario_id": user["id"],
        "origem": "espelho_crm2_em_negociacao",
    }
    await pg_db.execute(
        """UPDATE crm_clients
           SET stage='negociacao', updated_at=$1,
               historico_movimentacoes = historico_movimentacoes || jsonb_build_array($2::jsonb)
           WHERE id=$3 AND tenant_id=$4""",
        now, movement, cliente_id, user["tenant_id"]
    )


def _normalize_contact_payload(contact: Optional[dict]) -> dict:
    payload = contact or {}
    return {
        "nome": clean_text(payload.get("nome", "")),
        "whatsapp": normalize_phone(payload.get("whatsapp", "")),
        "email": normalize_email(payload.get("email", "")),
    }


def _normalize_additional_contacts_payload(contacts: Optional[List[dict]]) -> List[dict]:
    normalized = []
    for item in contacts or []:
        payload = item or {}
        contact = {
            "nome": clean_text(payload.get("nome", "")),
            "cargo": clean_text(payload.get("cargo", "")).lower(),
            "whatsapp": normalize_phone(payload.get("whatsapp", "")),
            "email": normalize_email(payload.get("email", "")),
        }
        if any(contact.values()):
            normalized.append(contact)
    return normalized


async def _validate_client_payload(
    tenant_id: str,
    payload: dict,
    exclude_id: Optional[str] = None,
    require_required_fields: bool = False,
    fields_being_updated: Optional[set] = None,
) -> dict:
    payload["nome_empresa"] = clean_text(payload.get("nome_empresa", ""))
    if not payload["nome_empresa"]:
        raise HTTPException(status_code=400, detail="Nome da empresa é obrigatório")

    payload["canal_origem"] = clean_text(payload.get("canal_origem", ""))
    payload["origem_lead"] = clean_text(payload.get("origem_lead", ""))
    payload["categoria_interesse"] = [clean_text(item) for item in (payload.get("categoria_interesse") or []) if clean_text(item)]
    payload["contato_principal"] = _normalize_contact_payload(payload.get("contato_principal"))
    payload["contatos_adicionais"] = _normalize_additional_contacts_payload(payload.get("contatos_adicionais"))
    payload["temperatura_lead"] = clean_text(payload.get("temperatura_lead", "morno")).lower() or "morno"
    payload["responsavel_comercial"] = clean_text(payload.get("responsavel_comercial", ""))
    payload["segmento"] = clean_text(payload.get("segmento", "")).lower()
    payload["porte"] = clean_text(payload.get("porte", "")).lower()
    payload["regiao"] = clean_text(payload.get("regiao", "")).upper()
    payload["site"] = clean_text(payload.get("site", ""))
    payload["instagram"] = clean_text(payload.get("instagram", ""))
    payload["observacoes"] = clean_text(payload.get("observacoes", ""))
    for contact in payload["contatos_adicionais"]:
        if contact["email"] and not is_valid_email(contact["email"]):
            raise HTTPException(status_code=400, detail=f"E-mail inválido em contato adicional: {contact['nome'] or contact['email']}")
        if contact["whatsapp"] and not is_valid_phone(contact["whatsapp"]):
            raise HTTPException(status_code=400, detail=f"WhatsApp inválido em contato adicional: {contact['nome'] or contact['whatsapp']}")
        if contact["cargo"] and contact["cargo"] not in CARGO_DECISOR_OPTIONS:
            raise HTTPException(status_code=400, detail="Cargo inválido em contato adicional")

    cnpj_normalized = normalize_cnpj(payload.get("cnpj", ""))
    payload["cnpj"] = clean_text(payload.get("cnpj", ""))
    payload["cnpj_normalized"] = cnpj_normalized
    if cnpj_normalized:
        if exclude_id:
            existing = _row(await pg_db.fetch_one(
                "SELECT nome_empresa FROM crm_clients WHERE tenant_id=$1 AND cnpj_normalized=$2 AND id != $3",
                tenant_id, cnpj_normalized, exclude_id
            ))
        else:
            existing = _row(await pg_db.fetch_one(
                "SELECT nome_empresa FROM crm_clients WHERE tenant_id=$1 AND cnpj_normalized=$2",
                tenant_id, cnpj_normalized
            ))
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"CNPJ já cadastrado para o cliente '{existing.get('nome_empresa', '')}'.",
            )

    email = payload["contato_principal"].get("email")
    whatsapp = payload["contato_principal"].get("whatsapp")
    if email and not is_valid_email(email):
        raise HTTPException(status_code=400, detail="E-mail do contato principal inválido")
    if whatsapp and not is_valid_phone(whatsapp):
        raise HTTPException(status_code=400, detail="Telefone/WhatsApp do contato principal inválido")

    if payload["canal_origem"] and (fields_being_updated is None or "canal_origem" in fields_being_updated):
        valid_sources = await _get_valid_lead_sources(tenant_id)
        if payload["canal_origem"] not in valid_sources:
            raise HTTPException(status_code=400, detail="Canal de origem inválido")

    # Validar categorias de interesse (2 níveis)
    all_valid_categories = []
    for category, subcategories in CATEGORIA_INTERESSE_OPTIONS.items():
        all_valid_categories.append(category)
        all_valid_categories.extend(subcategories)
    
    invalid_categories = [item for item in payload["categoria_interesse"] if item not in all_valid_categories]
    if invalid_categories:
        raise HTTPException(status_code=400, detail=f"Categoria(s) inválida(s): {', '.join(invalid_categories)}")

    # Validar temperatura do lead
    temperatura = payload.get("temperatura_lead", "morno")
    if temperatura and temperatura not in TEMPERATURA_LEAD_OPTIONS:
        raise HTTPException(status_code=400, detail="Temperatura do lead inválida")

    # Validar segmento
    segmento = payload.get("segmento", "")
    if segmento and segmento not in SEGMENTO_CLIENTE_OPTIONS:
        raise HTTPException(status_code=400, detail="Segmento inválido")

    # Validar porte
    porte = payload.get("porte", "")
    if porte and porte not in PORTE_CLIENTE_OPTIONS:
        raise HTTPException(status_code=400, detail="Porte inválido")

    # Verificar se há categorias Grau 2 ANVISA e alertar
    has_grau2 = any(cat in CATEGORIAS_GRAU2 for cat in payload["categoria_interesse"])
    payload["has_grau2_anvisa"] = has_grau2

    if payload["regiao"] and payload["regiao"] not in UF_OPTIONS:
        raise HTTPException(status_code=400, detail="UF inválida")

    if payload["responsavel_comercial"]:
        responsible = await db.users.find_one(
            {"id": payload["responsavel_comercial"], "tenant_id": tenant_id},
            {"_id": 0, "id": 1},
        )
        if not responsible:
            raise HTTPException(status_code=400, detail="Responsável comercial inválido")

    if require_required_fields:
        missing = []
        contact = payload["contato_principal"]
        if not clean_text(contact.get("nome", "")):
            missing.append("contato_principal.nome")
        if not clean_text(contact.get("whatsapp", "")):
            missing.append("contato_principal.whatsapp")
        if not payload["canal_origem"]:
            missing.append("canal_origem")
        if not payload["categoria_interesse"]:
            missing.append("categoria_interesse")
        if not payload["temperatura_lead"]:
            missing.append("temperatura_lead")
        if not payload["responsavel_comercial"]:
            missing.append("responsavel_comercial")
        if not payload["segmento"]:
            missing.append("segmento")
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Campos obrigatórios ausentes: {', '.join(missing)}",
            )

    return payload


def _validate_client_transition_requirements(client: dict, target_stage: str):
    if target_stage != "qualificado":
        return
    missing = []
    contact = client.get("contato_principal") or {}
    if not client.get("canal_origem"):
        missing.append("canal_origem")
    if not client.get("categoria_interesse"):
        missing.append("categoria_interesse")
    if not clean_text(contact.get("nome", "")):
        missing.append("contato_principal.nome")
    if not contact.get("whatsapp"):
        missing.append("contato_principal.whatsapp")
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Preencha os campos obrigatórios antes de avançar: {', '.join(missing)}",
        )


def _validate_project_transition_requirements(project: dict, target_stage: str):
    normalized_stage = _normalize_project_stage(target_stage)
    if normalized_stage != "amostra_solicitada":
        return
    missing = []
    if not clean_text(project.get("nome_projeto", "")):
        missing.append("nome_projeto")
    if not clean_text(project.get("categoria", "")):
        missing.append("categoria")
    if not clean_text(project.get("responsavel_comercial", "")):
        missing.append("responsavel_comercial")
    if not clean_text(project.get("ideia_conceito", "")) and not clean_text(project.get("briefing_tecnico", "")):
        missing.append("ideia_conceito")
    if not clean_text(project.get("posicionamento", "")):
        missing.append("posicionamento")
    if not project.get("volume_estimado_pedido"):
        missing.append("volume_estimado_pedido")
    if not clean_text(project.get("tipo_servico", "")):
        missing.append("tipo_servico")
    if not clean_text(project.get("prazo_desejado_amostra", "")) and not clean_text(project.get("prazo_prometido_cliente", "")):
        missing.append("prazo_desejado_amostra")
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Preencha o pré-briefing antes de avançar: {', '.join(missing)}",
        )

# ======================================================================
#  CRM 1 — CLIENTS (Pipeline Comercial)
# ======================================================================

@crm_router.get("/clients/suggest-cli4")
async def suggest_cli4_endpoint(nome: str, request: Request):
    """
    R23: Retorna sugestões de CLI4 (4 letras) para um nome de empresa,
    indicando disponibilidade de cada código.
    """
    user = await _get_current_user(request)
    candidates = suggest_cli4_candidates(nome)
    result = []
    for code in candidates[:6]:
        conflict = _row(await pg_db.fetch_one(
            "SELECT nome_empresa FROM crm_clients WHERE tenant_id=$1 AND cli4=$2",
            user["tenant_id"], code
        ))
        result.append({
            "cli4": code,
            "disponivel": conflict is None,
            "ocupado_por": conflict["nome_empresa"] if conflict else None,
        })
    return {"sugestoes": result}


@crm_router.post("/clients")
async def create_client(data: ClientCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL)
    client_id = _new_id()

    now = _now_iso()
    create_payload = await _validate_client_payload(
        user["tenant_id"],
        {
            "nome_empresa": data.nome_empresa,
            "cnpj": data.cnpj,
            "contato_principal": data.contato_principal.model_dump() if data.contato_principal else {"nome": "", "whatsapp": "", "email": ""},
            "contatos_adicionais": [item.model_dump() for item in data.contatos_adicionais],
            "canal_origem": data.canal_origem,
            "categoria_interesse": data.categoria_interesse,
            "origem_lead": data.origem_lead,
            # Novos campos PRD
            "temperatura_lead": data.temperatura_lead or "morno",
            "responsavel_comercial": data.responsavel_comercial or user["id"],
            "segmento": data.segmento or "outro",
            "porte": data.porte,
            "regiao": data.regiao,
            "site": data.site,
            "instagram": data.instagram,
            "observacoes": data.observacoes,
        },
        require_required_fields=True,
    )

    client = {
        "id": client_id,
        "tenant_id": user["tenant_id"],
        "stage": "prospeccao",
        # Prospecção fields
        "nome_empresa": create_payload["nome_empresa"],
        "cnpj": create_payload["cnpj"],
        "cnpj_normalized": create_payload["cnpj_normalized"],
        "contato_principal": create_payload["contato_principal"],
        "contatos_adicionais": create_payload["contatos_adicionais"],
        "canal_origem": create_payload["canal_origem"],
        "categoria_interesse": create_payload["categoria_interesse"],
        "origem_lead": create_payload["origem_lead"],
        # Novos campos PRD
        "temperatura_lead": create_payload["temperatura_lead"],
        "responsavel_comercial": create_payload["responsavel_comercial"],
        "segmento": create_payload["segmento"],
        "porte": create_payload["porte"],
        "regiao": create_payload["regiao"],
        "site": create_payload["site"],
        "instagram": create_payload["instagram"],
        "observacoes": create_payload["observacoes"],
        "cli3": normalise_cli3(data.cli3 or ""),
        "cli4": await _resolve_cli4(user["tenant_id"], data.cli4, data.nome_empresa),
        "cli4_congelado": False,
        "has_grau2_anvisa": create_payload.get("has_grau2_anvisa", False),
        "ultima_atualizacao_temperatura": now,
        # Qualificado fields — pre-filled if provided at creation
        "decisores": [d.model_dump() for d in data.decisores] if data.decisores else [],
        "tem_marca_propria": None,
        "tem_anvisa": data.tem_anvisa or "",
        "volume_estimado_mensal": data.volume_estimado_mensal or "",
        "fornecedor_atual": data.fornecedor_atual.model_dump() if data.fornecedor_atual else {"tem": False, "motivo_troca": ""},
        "prazo_urgencia": None,
        # Negociação fields (empty initially)
        "amostras_aprovadas": [],
        "valor_estimado_projeto": None,
        "moq_negociado": "",
        "condicao_pagamento": "",
        "anvisa_necessario": {"necessario": False, "status": ""},
        "concorrentes_envolvidos": [],
        # Fechado fields (empty initially)
        "data_pedido": None,
        "skus_confirmados": [],
        "valor_primeiro_pedido": None,
        "previsao_segundo_pedido": None,
        # Perdido
        "motivo_perda": "",
        # Meta
        "historico_movimentacoes": [],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }

    await pg_db.execute(
        """INSERT INTO crm_clients (
            id, tenant_id, stage, nome_empresa, cnpj, cnpj_normalized, cli3, cli4, cli4_congelado,
            canal_origem, origem_lead, temperatura_lead, responsavel_comercial, segmento, porte,
            regiao, site, instagram, observacoes, has_grau2_anvisa, ultima_atualizacao_temperatura,
            tem_anvisa, volume_estimado_mensal, created_by, created_by_name, created_at, updated_at,
            categoria_interesse, contato_principal, contatos_adicionais, decisores, fornecedor_atual,
            anvisa_necessario, concorrentes_envolvidos, skus_confirmados, amostras_aprovadas,
            historico_movimentacoes
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,
            $22,$23,$24,$25,NOW(),NOW(),$26,$27,$28,$29,$30,$31,$32,$33,$34,$35
        )""",
        client["id"], client["tenant_id"], client["stage"], client["nome_empresa"],
        client.get("cnpj",""), client.get("cnpj_normalized"),
        client.get("cli3",""), client.get("cli4",""), client.get("cli4_congelado", False),
        client.get("canal_origem",""), client.get("origem_lead",""),
        client.get("temperatura_lead","morno"), client.get("responsavel_comercial",""),
        client.get("segmento",""), client.get("porte",""), client.get("regiao",""),
        client.get("site",""), client.get("instagram",""), client.get("observacoes",""),
        client.get("has_grau2_anvisa", False), client.get("ultima_atualizacao_temperatura"),
        client.get("tem_anvisa",""), client.get("volume_estimado_mensal",""),
        client.get("created_by",""), client.get("created_by_name",""),
        client.get("categoria_interesse", []), client.get("contato_principal", {}),
        client.get("contatos_adicionais", []), client.get("decisores", []),
        client.get("fornecedor_atual", {}), client.get("anvisa_necessario", {}),
        client.get("concorrentes_envolvidos", []), client.get("skus_confirmados", []),
        client.get("amostras_aprovadas", []), client.get("historico_movimentacoes", [])
    )
    initial_task = await create_workflow_task(
        tenant_id=user["tenant_id"],
        entity_type="client",
        entity_id=client_id,
        title="Realizar primeiro contato comercial",
        description="Tarefa gerada automaticamente ao entrar em Prospecção.",
        category="comercial",
        blocking=False,
        due_in_days=3,
        responsible_id=client["responsavel_comercial"],
        created_by=user,
        metadata={"trigger": "client_created", "stage": "prospeccao"},
    )
    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="client_created",
        entity_type="client",
        entity_id=client_id,
        after={"nome_empresa": client["nome_empresa"], "stage": client["stage"]},
        metadata={"tasks_generated": [initial_task["id"]]},
    )
    return _serialize(client)


@crm_router.get("/clients")
async def list_clients(
    request: Request,
    stage: Optional[str] = None,
    search: Optional[str] = None,
):
    user = await _get_current_user(request)
    sql = "SELECT * FROM crm_clients WHERE tenant_id=$1"
    params: list = [user["tenant_id"]]
    if stage:
        params.append(stage)
        sql += f" AND stage=${len(params)}"
    if search:
        search = clean_text(search)
        digits = normalize_phone(search) or ""
        params.append(f"%{search}%")
        n = len(params)
        sql += (
            f" AND (nome_empresa ILIKE ${n} OR cnpj ILIKE ${n}"
            f" OR contato_principal->>'nome' ILIKE ${n}"
            f" OR contato_principal->>'email' ILIKE ${n}"
        )
        if digits:
            params.append(f"%{digits}%")
            m = len(params)
            sql += f" OR cnpj_normalized ILIKE ${m} OR contato_principal->>'whatsapp' ILIKE ${m}"
        sql += ")"
    sql += " ORDER BY created_at DESC LIMIT 5000"
    clients = _rows(await pg_db.fetch_all(sql, *params))
    return clients


@crm_router.get("/clients/{client_id}")
async def get_client(client_id: str, request: Request):
    user = await _get_current_user(request)
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        client_id, user["tenant_id"]
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@crm_router.put("/clients/{client_id}")
async def update_client(client_id: str, data: ClientUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL)
    existing = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        client_id, user["tenant_id"]
    ))
    if not existing:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    update_fields = {}
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None:
            if isinstance(v, BaseModel):
                update_fields[k] = v.model_dump()
            else:
                update_fields[k] = v

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # RN-CL-04: Registrar data de atualização de temperatura
    if "temperatura_lead" in update_fields:
        update_fields["ultima_atualizacao_temperatura"] = _now_iso()

    # RN-SK-01: cli3 must be exactly 3 uppercase alpha chars
    if "cli3" in update_fields:
        raw = str(update_fields["cli3"] or "")
        letters = "".join(c for c in raw.upper() if c.isalpha())[:3]
        if letters and len(letters) < 3:
            raise HTTPException(status_code=400, detail=f"cli3 deve ter 3 letras (ex: 'ABC'). Recebido: '{raw}'")
        update_fields["cli3"] = letters or ""

    # R23: cli4 freeze — not editable after first SKU
    if "cli4" in update_fields:
        if existing.get("cli4_congelado"):
            raise HTTPException(
                status_code=409,
                detail=f"CLI4 '{existing.get('cli4')}' está congelado — já existe SKU gerado para este cliente e o código não pode mais ser alterado"
            )
        new_cli4 = normalise_cli4(str(update_fields["cli4"] or ""))
        conflict = _row(await pg_db.fetch_one(
            "SELECT nome_empresa FROM crm_clients WHERE tenant_id=$1 AND cli4=$2 AND id != $3",
            user["tenant_id"], new_cli4, client_id
        ))
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"CLI4 '{new_cli4}' já está em uso pelo cliente '{conflict['nome_empresa']}'"
            )
        update_fields["cli4"] = new_cli4

    payload = dict(existing)
    payload.update(update_fields)
    payload = await _validate_client_payload(
        user["tenant_id"], payload, exclude_id=client_id,
        fields_being_updated=set(update_fields.keys()),
    )
    for field in (
        "nome_empresa",
        "cnpj",
        "cnpj_normalized",
        "contato_principal",
        "contatos_adicionais",
        "canal_origem",
        "categoria_interesse",
        "origem_lead",
        "temperatura_lead",
        "responsavel_comercial",
        "segmento",
        "porte",
        "regiao",
        "site",
        "instagram",
        "observacoes",
        "has_grau2_anvisa",
    ):
        if field in update_fields or field == "cnpj_normalized":
            update_fields[field] = payload[field]

    set_parts = [f"{k}=${i+1}" for i, k in enumerate(update_fields.keys())]
    set_parts.append("updated_at=NOW()")
    params = list(update_fields.values())
    params.extend([client_id, user["tenant_id"]])
    rows = await pg_db.fetch_all(
        f"UPDATE crm_clients SET {', '.join(set_parts)} WHERE id=${len(params)-1} AND tenant_id=${len(params)} RETURNING id",
        *params
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    client = _row(await pg_db.fetch_one("SELECT * FROM crm_clients WHERE id=$1", client_id))

    # Auto-complete "qualificacao" blocking task when all 4 fields are present
    await _auto_complete_qualificacao_task(client, user["tenant_id"], user)

    return client


async def _auto_complete_qualificacao_task(client: dict, tenant_id: str, user: dict):
    """Mark the 'Qualificar lead' blocking task as done when all required fields are filled.
    The three fields below have no default value — only non-empty means 'filled'."""
    decisores_ok = bool(client.get("decisores"))          # at least one entry in list
    anvisa_ok = bool(str(client.get("tem_anvisa") or "").strip())   # e.g. "sim" / "nao"
    volume_ok = bool(str(client.get("volume_estimado_mensal") or "").strip())

    if not (decisores_ok and anvisa_ok and volume_ok):
        return

    now = _now_iso()
    await db.workflow_tasks.update_many(
        {
            "tenant_id": tenant_id,
            "entity_type": "client",
            "entity_id": client["id"],
            "category": "qualificacao",
            "status": {"$in": ["pendente", "em_andamento", "em_atraso"]},
        },
        {
            "$set": {
                "status": "concluida",
                "completed_at": now,
                "completed_by": user["id"],
                "completed_by_name": user.get("name", ""),
                "completion_comment": "Concluído automaticamente — decisores, ANVISA, volume e fornecedor preenchidos.",
                "updated_at": now,
            }
        }
    )


@crm_router.put("/clients/{client_id}/move")
async def move_client(client_id: str, data: ClientMove, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL)
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        client_id, user["tenant_id"]
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    old_stage = client["stage"]
    new_stage = data.stage

    if new_stage not in CLIENT_STAGES:
        raise HTTPException(status_code=400, detail=f"Estágio inválido: {new_stage}")

    allowed = CLIENT_TRANSITIONS.get(old_stage, [])
    if new_stage not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transição não permitida: {STAGE_LABELS.get(old_stage)} → {STAGE_LABELS.get(new_stage)}"
        )

    old_idx = _CLIENT_STAGE_ORDER.index(old_stage) if old_stage in _CLIENT_STAGE_ORDER else 0
    new_idx = _CLIENT_STAGE_ORDER.index(new_stage) if new_stage in _CLIENT_STAGE_ORDER else 0
    is_regression = new_idx < old_idx

    if is_regression and not (data.justificativa or "").strip():
        raise HTTPException(status_code=400, detail="Justificativa obrigatória para movimentações retroativas")

    # Auto-complete qualificacao task if fields are already filled
    await _auto_complete_qualificacao_task(client, user["tenant_id"], user)

    # ERP v3.0: bloquear avanço se houver tarefas obrigatórias pendentes
    _validate_client_transition_requirements(client, new_stage)
    await assert_no_blocking_tasks(
        tenant_id=user["tenant_id"],
        entity_type="client",
        entity_id=client_id,
        target_stage=new_stage,
    )

    # Validate motivo_perda for cliente_perdido
    if new_stage == "cliente_perdido" and not data.motivo_perda:
        raise HTTPException(status_code=400, detail="Motivo da perda é obrigatório")

    now = _now_iso()
    if new_stage == "cliente_perdido" and clean_text(data.motivo_perda).lower() not in MOTIVO_PERDA_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Motivo da perda inválido. Use: {', '.join(MOTIVO_PERDA_OPTIONS)}",
        )

    update_data = {
        "stage": new_stage,
    }

    if new_stage == "cliente_perdido" and data.motivo_perda:
        update_data["motivo_perda"] = clean_text(data.motivo_perda).lower()

    # Add to historico_movimentacoes
    movement = {
        "de": old_stage,
        "para": new_stage,
        "data": now,
        "usuario": user["name"],
        "usuario_id": user["id"],
        "is_regression": is_regression,
    }
    if is_regression and data.justificativa:
        movement["justificativa"] = data.justificativa.strip()

    # updated_at uses NOW() directly — asyncpg requires datetime objects for TIMESTAMPTZ, not ISO strings
    set_parts = [f"{k}=${i+1}" for i, k in enumerate(update_data.keys())]
    set_parts.append("updated_at=NOW()")
    set_parts.append(f"historico_movimentacoes = historico_movimentacoes || jsonb_build_array(${len(update_data)+1}::jsonb)")
    params = list(update_data.values()) + [movement, client_id]
    await pg_db.execute(
        f"UPDATE crm_clients SET {', '.join(set_parts)} WHERE id=${len(params)}",
        *params
    )

    updated = _row(await pg_db.fetch_one("SELECT * FROM crm_clients WHERE id=$1", client_id))

    # ERP v3.0: trigger workflow tasks for the new stage (non-fatal — schema issues must not block the move)
    new_tasks = []
    try:
        new_tasks = await trigger_tasks_for_transition(
            entity_type="client",
            entity_id=client_id,
            tenant_id=user["tenant_id"],
            old_stage=old_stage,
            new_stage=new_stage,
            user=user,
        )
    except Exception as exc:
        logger.error(f"[move_client] trigger_tasks_for_transition falhou (ignorado): {exc}", exc_info=True)

    # ERP v3.0: immutable audit log of stage change (non-fatal)
    try:
        await audit_log(
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            user_name=user.get("name", ""),
            action="client_moved",
            entity_type="client",
            entity_id=client_id,
            before={"stage": old_stage},
            after={"stage": new_stage, "motivo_perda": update_data.get("motivo_perda")},
            metadata={"tasks_generated": [t["id"] for t in new_tasks]},
        )
    except Exception as exc:
        logger.error(f"[move_client] audit_log falhou (ignorado): {exc}", exc_info=True)

    # Determine if batch project creation is triggered
    trigger_batch_projects = (new_stage == "projeto_em_discussao")

    return {
        "client": updated,
        "trigger_batch_projects": trigger_batch_projects,
        "from_stage": STAGE_LABELS.get(old_stage, old_stage),
        "to_stage": STAGE_LABELS.get(new_stage, new_stage),
        "tasks_generated": new_tasks,
    }


@crm_router.get("/clients/{client_id}/full")
async def get_client_full(client_id: str, request: Request):
    user = await _get_current_user(request)
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        client_id, user["tenant_id"]
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    projects = _rows(await pg_db.fetch_all(
        "SELECT * FROM crm_projects WHERE cliente_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 500",
        client_id, user["tenant_id"]
    ))
    samples = _rows(await pg_db.fetch_all(
        "SELECT * FROM crm_samples WHERE cliente_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 500",
        client_id, user["tenant_id"]
    ))
    skus = _rows(await pg_db.fetch_all(
        "SELECT * FROM skus WHERE cliente_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 500",
        client_id, user["tenant_id"]
    ))
    alerts = _rows(await pg_db.fetch_all(
        "SELECT * FROM crm_alerts WHERE tenant_id=$1 AND entidade_ref=$2 AND status != 'resolvido' LIMIT 100",
        user["tenant_id"], client_id
    ))
    # Enrich with orders history (stays MongoDB)
    orders = await db.orders.find(
        {"client_card_id": client_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    # Computed summary fields
    projetos_ativos = [p for p in projects if p.get("stage") not in ("projeto_arquivado",)]
    ultimo_projeto = projects[0] if projects else None
    ultimo_pedido = orders[0] if orders else None

    # Item mais pedido across all orders
    item_counter: dict = {}
    for order in orders:
        for item in order.get("items", []):
            name = item.get("item") or item.get("codigo_kuryos") or ""
            if name:
                item_counter[name] = item_counter.get(name, 0) + 1
    item_mais_pedido = max(item_counter, key=item_counter.get) if item_counter else None

    return {
        "client": client,
        "projects": projects,
        "samples": samples,
        "skus": skus,
        "alerts": alerts,
        "orders": orders,
        "summary": {
            "projetos_ativos": len(projetos_ativos),
            "total_projetos": len(projects),
            "total_amostras": len(samples),
            "total_pedidos": len(orders),
            "ultimo_projeto": {
                "id": ultimo_projeto["id"],
                "nome": ultimo_projeto.get("nome_projeto", ""),
                "stage": ultimo_projeto.get("stage", ""),
                "created_at": ultimo_projeto.get("created_at", ""),
            } if ultimo_projeto else None,
            "ultimo_pedido": {
                "id": ultimo_pedido["id"],
                "numero": ultimo_pedido.get("numero_pedido", ""),
                "status": ultimo_pedido.get("status", ""),
                "total": ultimo_pedido.get("total_pedido", 0),
                "created_at": ultimo_pedido.get("created_at", ""),
            } if ultimo_pedido else None,
            "item_mais_pedido": item_mais_pedido,
        },
    }


# ======================================================================
#  CRM 2 — PROJECTS (Pipeline de Projetos)
# ======================================================================

@crm_router.post("/projects/batch")
async def batch_create_projects(data: ProjectBatchCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL)

    # ERP v3.0: hierarchy lock — child cannot exist without parent
    client = await assert_client_exists(user["tenant_id"], data.cliente_id)

    if not data.projects:
        raise HTTPException(status_code=400, detail="Nenhum projeto fornecido")

    now = _now_iso()
    created = []
    created_project_ids: List[str] = []
    created_task_ids: List[str] = []
    created_audit_ids: List[str] = []

    try:
        for item in data.projects:
            project_id = _new_id()
            project = {
                "id": project_id,
                "tenant_id": user["tenant_id"],
                "cliente_id": data.cliente_id,
                "cliente_nome": client["nome_empresa"],
                "stage": "projeto_em_discussao",
                "nome_projeto": item.nome_projeto,
                "categoria": item.categoria,
                "briefing_tecnico": item.briefing_resumido,
                "responsavel_comercial": item.responsavel_comercial or client.get("responsavel_comercial", ""),
                "ideia_conceito": item.ideia_conceito,
                "referencia_mercado": item.referencia_mercado,
                "publico_alvo": item.publico_alvo,
                "posicionamento": item.posicionamento,
                "faixa_preco_venda": item.faixa_preco_venda,
                "volume_estimado_pedido": item.volume_estimado_pedido,
                "tipo_servico": item.tipo_servico,
                "sensorial_desejado": item.sensorial_desejado,
                "restricoes_tecnicas": item.restricoes_tecnicas,
                "claims_desejados": item.claims_desejados,
                "prazo_desejado_amostra": item.prazo_desejado_amostra,
                "observacoes_livres": item.observacoes_livres,
                "responsavel_interno": "",
                "data_inicio_desenvolvimento": None,
                "prazo_prometido_cliente": item.prazo_desejado_amostra or None,
                "data_ultima_amostra_enviada": None,
                "numero_amostras_solicitadas": 0,
                "motivo_arquivamento": "",
                "historico_movimentacoes": [],
                "created_by": user["id"],
                "created_by_name": user["name"],
                "created_at": now,
                "updated_at": now,
            }
            inherit(project, client, INHERITED_FROM_CLIENT)

            await pg_db.execute(
                """INSERT INTO crm_projects (
                    id, tenant_id, cliente_id, cliente_nome, stage, nome_projeto, categoria,
                    briefing_tecnico, responsavel_comercial, responsavel_interno,
                    ideia_conceito, referencia_mercado, publico_alvo, posicionamento,
                    faixa_preco_venda, volume_estimado_pedido, tipo_servico, sensorial_desejado,
                    claims_desejados, prazo_desejado_amostra, prazo_prometido_cliente,
                    observacoes_livres, data_inicio_desenvolvimento, data_ultima_amostra_enviada,
                    numero_amostras_solicitadas, motivo_arquivamento,
                    created_by, created_by_name, created_at, updated_at,
                    restricoes_tecnicas, historico_movimentacoes
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
                    $19,$20,$21,$22,$23,$24,$25,$26,$27,$28,NOW(),NOW(),$29,$30
                )""",
                project["id"], project["tenant_id"], project["cliente_id"], project["cliente_nome"],
                project["stage"], project["nome_projeto"], project.get("categoria",""),
                project.get("briefing_tecnico",""), project.get("responsavel_comercial",""),
                project.get("responsavel_interno",""), project.get("ideia_conceito",""),
                project.get("referencia_mercado",""), project.get("publico_alvo",""),
                project.get("posicionamento",""), project.get("faixa_preco_venda"),
                project.get("volume_estimado_pedido"), project.get("tipo_servico",""),
                project.get("sensorial_desejado",""), project.get("claims_desejados",""),
                project.get("prazo_desejado_amostra",""), project.get("prazo_prometido_cliente"),
                project.get("observacoes_livres",""), project.get("data_inicio_desenvolvimento"),
                project.get("data_ultima_amostra_enviada"),
                project.get("numero_amostras_solicitadas", 0), project.get("motivo_arquivamento",""),
                project.get("created_by",""), project.get("created_by_name",""),
                project.get("restricoes_tecnicas", []),
                project.get("historico_movimentacoes", [])
            )
            created_project_ids.append(project_id)

            viability_task = None
            try:
                viability_task = await create_workflow_task(
                    tenant_id=user["tenant_id"],
                    entity_type="project",
                    entity_id=project_id,
                    title="Validar viabilidade tecnica do pre-briefing",
                    description="Tarefa automatica ao criar projeto em discussao.",
                    category="pd_dev",
                    blocking=False,
                    due_in_days=2,
                    created_by=user,
                )
            except Exception as _wf_exc:
                logger.error(f"[batch_create_projects] create_workflow_task falhou (ignorado): {_wf_exc}", exc_info=True)
            if viability_task and viability_task.get("id"):
                created_task_ids.append(viability_task["id"])

            deadline_task = None
            try:
                deadline_task = await _create_project_deadline_alert_task(project, user)
            except Exception as _dl_exc:
                logger.error(f"[batch_create_projects] deadline_task falhou (ignorado): {_dl_exc}", exc_info=True)
            if deadline_task and deadline_task.get("id"):
                created_task_ids.append(deadline_task["id"])

            audit_entry = None
            try:
                audit_entry = await audit_log(
                    tenant_id=user["tenant_id"],
                    user_id=user["id"],
                    user_name=user.get("name", ""),
                    action="project_created",
                    entity_type="project",
                    entity_id=project_id,
                    after={
                        "nome_projeto": project["nome_projeto"],
                        "cliente_id": data.cliente_id,
                        "stage": project["stage"],
                    },
                    metadata={
                        "tasks_generated": [
                            task_id for task_id in [
                                viability_task.get("id") if viability_task else None,
                                deadline_task.get("id") if deadline_task else None,
                            ] if task_id
                        ]
                    },
                )
            except Exception as _al_exc:
                logger.error(f"[batch_create_projects] audit_log falhou (ignorado): {_al_exc}", exc_info=True)
            if audit_entry and audit_entry.get("id"):
                created_audit_ids.append(audit_entry["id"])

            created.append(project)
    except Exception as exc:
        logger.exception("Failed to create project batch; rolling back persisted records")
        await _rollback_batch_created_projects(
            user["tenant_id"],
            project_ids=created_project_ids,
            workflow_task_ids=created_task_ids,
            audit_log_ids=created_audit_ids,
        )
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail="Falha ao criar projetos. Nenhum projeto foi persistido; revise os dados e tente novamente.",
        ) from exc

    logger.info(f"Batch created {len(created)} projects for client {data.cliente_id}")
    return {"created": created, "count": len(created)}


@crm_router.get("/projects")
async def list_projects(
    request: Request,
    cliente_id: Optional[str] = None,
    stage: Optional[str] = None,
    search: Optional[str] = None,
):
    user = await _get_current_user(request)
    sql = "SELECT * FROM crm_projects WHERE tenant_id=$1"
    params: list = [user["tenant_id"]]
    if cliente_id:
        params.append(cliente_id); sql += f" AND cliente_id=${len(params)}"
    if stage:
        params.append(_normalize_project_stage(stage)); sql += f" AND stage=${len(params)}"
    if search:
        params.append(f"%{search}%"); n = len(params)
        sql += (f" AND (nome_projeto ILIKE ${n} OR cliente_nome ILIKE ${n}"
                f" OR categoria ILIKE ${n} OR briefing_tecnico ILIKE ${n}"
                f" OR ideia_conceito ILIKE ${n} OR publico_alvo ILIKE ${n}"
                f" OR claims_desejados ILIKE ${n})")
    sql += " ORDER BY created_at DESC LIMIT 5000"
    projects = _rows(await pg_db.fetch_all(sql, *params))
    return projects


@crm_router.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request):
    user = await _get_current_user(request)
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return project


@crm_router.put("/projects/{project_id}")
async def update_project(project_id: str, data: ProjectUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL)
    update_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    fields = list(update_fields.keys())
    params: list = [update_fields[k] for k in fields]
    set_clause = ", ".join(f"{k}=${i+1}" for i, k in enumerate(fields)) + ", updated_at=NOW()"
    params.extend([project_id, user["tenant_id"]])
    matched = await pg_db.fetch_val(
        f"UPDATE crm_projects SET {set_clause} WHERE id=${len(params)-1} AND tenant_id=${len(params)} RETURNING id",
        *params
    )
    if not matched:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))
    if project and update_fields.get("prazo_desejado_amostra"):
        await _create_project_deadline_alert_task(project, user)
    return project


@crm_router.put("/projects/{project_id}/move")
async def move_project(project_id: str, data: ProjectMove, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL)
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    old_stage = _normalize_project_stage(project["stage"])
    new_stage = _normalize_project_stage(data.stage)

    if new_stage not in PROJECT_STAGES:
        raise HTTPException(status_code=400, detail=f"Estágio inválido: {new_stage}")

    allowed = [_normalize_project_stage(stage) for stage in PROJECT_TRANSITIONS.get(old_stage, [])]
    if new_stage not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transição não permitida: {STAGE_LABELS.get(old_stage)} → {STAGE_LABELS.get(new_stage)}"
        )
    if new_stage == "pedido_aprovado":
        from kickoff_routes import _resolve_registered_formula_for_project

        await _resolve_registered_formula_for_project(project_id, user["tenant_id"])

    _validate_project_transition_requirements(project, new_stage)
    if new_stage == "projeto_arquivado" and not clean_text(data.motivo_arquivamento or ""):
        raise HTTPException(status_code=400, detail="Motivo do arquivamento é obrigatório")
    await assert_no_blocking_tasks(
        tenant_id=user["tenant_id"],
        entity_type="project",
        entity_id=project_id,
        target_stage=new_stage,
    )

    now = _now_iso()
    movement = {
        "de": old_stage,
        "para": new_stage,
        "data": now,
        "usuario": user["name"],
        "usuario_id": user["id"],
    }

    update_fields = {"stage": new_stage, "updated_at": now}
    if new_stage == "amostra_em_desenvolvimento" and not project.get("data_inicio_desenvolvimento"):
        update_fields["data_inicio_desenvolvimento"] = now
    if new_stage == "amostra_enviada":
        update_fields["data_ultima_amostra_enviada"] = now
    if new_stage == "projeto_arquivado":
        update_fields["motivo_arquivamento"] = clean_text(data.motivo_arquivamento or "")

    set_parts = ["stage=$1",
                 "updated_at=NOW()",
                 "historico_movimentacoes = historico_movimentacoes || jsonb_build_array($2::jsonb)"]
    params: list = [new_stage, json.dumps(movement)]
    for k, v in update_fields.items():
        if k not in ("stage", "updated_at"):
            params.append(v); set_parts.append(f"{k}=${len(params)}")
    params.extend([project_id, user["tenant_id"]])
    await pg_db.execute(
        f"UPDATE crm_projects SET {', '.join(set_parts)} WHERE id=${len(params)-1} AND tenant_id=${len(params)}",
        *params
    )

    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))
    if new_stage == "amostra_solicitada":
        try:
            await _create_project_deadline_alert_task(updated, user)
        except Exception as _exc:
            logger.error(f"[move_project] deadline_task falhou (ignorado): {_exc}", exc_info=True)

    new_tasks = []
    try:
        new_tasks = await trigger_tasks_for_transition(
            entity_type="project",
            entity_id=project_id,
            tenant_id=user["tenant_id"],
            old_stage=old_stage,
            new_stage=new_stage,
            user=user,
        )
    except Exception as exc:
        logger.error(f"[move_project] trigger_tasks_for_transition falhou (ignorado): {exc}", exc_info=True)
    kickoff_created = None
    kickoff_tasks = []
    if new_stage == "pedido_aprovado":
        from kickoff_routes import create_kickoff_for_project

        kickoff = await create_kickoff_for_project(project_id, user)
        kickoff_created = {
            "kickoff_id": kickoff["id"],
            "numero_kickoff": kickoff["numero_kickoff"],
        }
        kickoff_tasks.append({"tipo": "preencher_kickoff_bloco2", "responsavel": "comercial"})

    try:
        await audit_log(
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            user_name=user.get("name", ""),
            action="project_moved",
            entity_type="project",
            entity_id=project_id,
            before={"stage": old_stage},
            after={"stage": new_stage, "motivo_arquivamento": update_fields.get("motivo_arquivamento")},
            metadata={"tasks_generated": [t["id"] for t in new_tasks]},
        )
    except Exception as exc:
        logger.error(f"[move_project] audit_log falhou (ignorado): {exc}", exc_info=True)

    if new_stage == "em_negociacao" and updated:
        await _mirror_client_stage_to_negociacao(updated, user)

    trigger_batch_samples = (new_stage == "amostra_solicitada")

    return {
        "project": updated,
        "trigger_batch_samples": trigger_batch_samples,
        "from_stage": STAGE_LABELS.get(old_stage, old_stage),
        "to_stage": STAGE_LABELS.get(new_stage, new_stage),
        "tasks_generated": new_tasks,
        "kickoff_criado": kickoff_created,
        "tarefas_criadas": kickoff_tasks,
    }


@crm_router.get("/projects/{project_id}/full")
async def get_project_full(project_id: str, request: Request):
    user = await _get_current_user(request)
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        project["cliente_id"], user["tenant_id"]
    ))

    samples = _rows(await pg_db.fetch_all(
        "SELECT * FROM crm_samples WHERE projeto_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 500",
        project_id, user["tenant_id"]
    ))

    skus = _rows(await pg_db.fetch_all(
        "SELECT * FROM skus WHERE projeto_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 500",
        project_id, user["tenant_id"]
    ))

    # Enrich each variation with live P&D status
    all_card_ids = []
    for s in samples:
        for v in s.get("variacoes", []) or []:
            if v.get("pd_card_id"):
                all_card_ids.append(v["pd_card_id"])

    if all_card_ids:
        pd_cards_docs = _rows(await pg_db.fetch_all(
            "SELECT id, pd_request_id, status_pd FROM pd_cards WHERE id = ANY($1::text[]) AND tenant_id=$2",
            all_card_ids, user["tenant_id"]
        ))
        cards_map = {c["id"]: c for c in pd_cards_docs}

        req_ids = list({c["pd_request_id"] for c in pd_cards_docs if c.get("pd_request_id")})
        reqs_map: Dict[str, Any] = {}
        if req_ids:
            reqs_docs = await db.pd_requests.find(
                {"id": {"$in": req_ids}, "tenant_id": user["tenant_id"]},
                {"_id": 0, "id": 1, "status": 1, "updated_at": 1, "project_name": 1}
            ).to_list(500)
            reqs_map = {r["id"]: r for r in reqs_docs}

        for s in samples:
            for v in s.get("variacoes", []) or []:
                card = cards_map.get(v.get("pd_card_id"))
                if card:
                    req = reqs_map.get(card.get("pd_request_id"), {})
                    v["pd_request_id"] = card.get("pd_request_id")
                    v["pd_status"] = req.get("status")
                    v["pd_status_pd"] = card.get("status_pd")
                    v["pd_updated_at"] = req.get("updated_at")

    return {
        "project": project,
        "client": client,
        "samples": samples,
        "skus": skus,
    }


@crm_router.delete("/projects/{project_id}")
async def delete_project(project_id: str, request: Request):
    """Deleta um projeto em cascata (samples + variações + pd_cards).
    Bloqueia se houver SKU já gerado a partir deste projeto."""
    user = await _get_current_user(request)
    require_roles(user, ADMIN_ONLY | {"sales_ops"})
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    # Bloquear se houver SKU vinculado
    sku_count = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM skus WHERE projeto_id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ) or 0
    if sku_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir: existem {sku_count} SKU(s) gerados a partir deste projeto."
        )

    # Coletar samples e pd_cards para deletar
    samples = _rows(await pg_db.fetch_all(
        "SELECT id, variacoes FROM crm_samples WHERE projeto_id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    ))

    sample_ids = [s["id"] for s in samples]
    pd_card_ids = []
    for s in samples:
        for v in s.get("variacoes", []) or []:
            if v.get("pd_card_id"):
                pd_card_ids.append(v["pd_card_id"])

    # Apagar pd_cards vinculados
    if pd_card_ids:
        await pg_db.execute(
            "DELETE FROM pd_cards WHERE id = ANY($1::text[]) AND tenant_id=$2",
            pd_card_ids, user["tenant_id"]
        )
    # Apagar samples
    if sample_ids:
        await pg_db.execute(
            "DELETE FROM crm_samples WHERE id = ANY($1::text[]) AND tenant_id=$2",
            sample_ids, user["tenant_id"]
        )
    # Apagar projeto
    await pg_db.execute(
        "DELETE FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        project_id, user["tenant_id"]
    )

    logger.info(f"Deleted project {project_id} (samples={len(sample_ids)}, pd_cards={len(pd_card_ids)})")
    return {
        "deleted_project": project_id,
        "deleted_samples": len(sample_ids),
        "deleted_pd_cards": len(pd_card_ids),
    }


# ======================================================================
#  CRM 3 — SAMPLES (Pipeline de Amostras)
# ======================================================================

@crm_router.post("/samples/batch")
async def batch_create_samples(data: SampleBatchCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL | PD_FULL)

    # Verify project exists
    project = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        data.projeto_id, user["tenant_id"]
    ))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    if not data.samples:
        raise HTTPException(status_code=400, detail="Nenhuma amostra fornecida")

    now = _now_iso()
    created = []

    for item in data.samples:
        if item.tipo_amostra == "adaptacao_de_formula" and not clean_text(item.referencia_formula):
            raise HTTPException(status_code=400, detail="referencia_formula é obrigatória para adaptação de fórmula")
        sample_id = _new_id()
        sample = {
            "id": sample_id,
            "tenant_id": user["tenant_id"],
            "projeto_id": data.projeto_id,
            "projeto_nome": project["nome_projeto"],
            "cliente_id": project["cliente_id"],
            "cliente_nome": project.get("cliente_nome", ""),
            "stage": "solicitada",
            "nome_amostra": item.nome_amostra,
            "observacao_tecnica": item.observacao_tecnica,
            "responsavel_pd": "",
            "data_envio": None,
            "feedback_cliente": "",
            "produto": item.produto,
            "objetivo_projeto": item.objetivo_projeto,
            "aplicacoes_desenvolver": item.aplicacoes_desenvolver,
            "ativos_claims": item.ativos_claims,
            "referencias": item.referencias,
            "referencias_fotos": item.referencias_fotos or [],
            "orcamento_projeto": item.orcamento_projeto,
            "textura_esperada": item.textura_esperada,
            "aplicacao": item.aplicacao,
            "sensorial": item.sensorial,
            "ph": item.ph,
            "historico_movimentacoes": [],
            "created_by": user["id"],
            "created_by_name": user["name"],
            "created_at": now,
            "updated_at": now,
        }
        await pg_db.execute(
            """INSERT INTO crm_samples (
                id, tenant_id, projeto_id, projeto_nome, cliente_id, cliente_nome, stage,
                nome_amostra, observacao_tecnica, responsavel_pd, data_envio, feedback_cliente,
                produto, objetivo_projeto, aplicacoes_desenvolver, ativos_claims, referencias,
                referencias_fotos, orcamento_projeto, textura_esperada, aplicacao, sensorial, ph,
                historico_movimentacoes, created_by, created_by_name, created_at, updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                $18,$19,$20,$21,$22,$23,$24,$25,$26,NOW(),NOW()
            )""",
            sample_id, user["tenant_id"], data.projeto_id, project["nome_projeto"],
            project["cliente_id"], project.get("cliente_nome", ""), "solicitada",
            item.nome_amostra, item.observacao_tecnica, "", None, "",
            item.produto, item.objetivo_projeto, item.aplicacoes_desenvolver, item.ativos_claims,
            item.referencias, item.referencias_fotos or [], item.orcamento_projeto,
            item.textura_esperada, item.aplicacao, item.sensorial, item.ph,
            [], user["id"], user["name"]
        )
        created.append(sample)

    logger.info(f"Batch created {len(created)} samples for project {data.projeto_id}")
    return {"created": created, "count": len(created)}


@crm_router.post("/samples/upload-image")
async def upload_sample_image(request: Request, file: UploadFile = File(...)):
    """Upload image for sample reference"""
    user = await _get_current_user(request)
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido. Use: JPG, PNG ou WEBP")
    
    # Create upload directory if not exists
    upload_dir = Path("/app/uploads/sample_images")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_ext = file.filename.split(".")[-1]
    unique_filename = f"{_new_id()}.{file_ext}"
    file_path = upload_dir / unique_filename
    
    # Save file
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Return URL path
        file_url = f"/uploads/sample_images/{unique_filename}"
        return {"url": file_url, "filename": unique_filename}
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        raise HTTPException(status_code=500, detail="Erro ao fazer upload da imagem")


@crm_router.post("/samples/batch/v2")
async def batch_create_samples_v2(data: SampleBatchCreateV2, request: Request):
    """Criar amostras em lote com suporte a variações (ERP v3.0: numeração GLOBAL)."""
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL | PD_FULL)

    # ERP v3.0: hierarchy lock
    project = await assert_project_exists(user["tenant_id"], data.projeto_id)

    if not data.samples:
        raise HTTPException(status_code=400, detail="Nenhuma amostra fornecida")

    # R02: atualizar campos do card antes de criar amostras (sync CRM→P&D)
    if data.projeto_updates:
        _ALLOWED_PROJETO_FIELDS = {
            "categoria", "responsavel_comercial", "responsavel_interno",
            "ideia_conceito", "referencia_mercado", "publico_alvo", "posicionamento",
            "tipo_servico", "faixa_preco_venda", "volume_estimado_pedido",
            "prazo_desejado_amostra", "sensorial_desejado", "claims_desejados",
            "restricoes_tecnicas", "observacoes_livres",
        }
        patch = {k: v for k, v in data.projeto_updates.items() if k in _ALLOWED_PROJETO_FIELDS}
        if patch:
            fields = list(patch.keys())
            p2: list = [patch[k] for k in fields]
            set_clause = ", ".join(f"{k}=${i+1}" for i, k in enumerate(fields)) + ", updated_at=NOW()"
            p2.extend([data.projeto_id, user["tenant_id"]])
            await pg_db.execute(
                f"UPDATE crm_projects SET {set_clause} WHERE id=${len(p2)-1} AND tenant_id=${len(p2)}",
                *p2
            )
            # Recarregar projeto com campos atualizados
            project = await assert_project_exists(user["tenant_id"], data.projeto_id)

    now = _now_iso()
    created_samples = []

    for item in data.samples:
        # ERP v3.0: numeração GLOBAL sequencial (counter atômico no tenant)
        numero_amostra = await _get_next_sample_code(data.projeto_id, user["tenant_id"])

        # Criar amostra pai
        sample_id = _new_id()

        # Criar variações
        variacoes_data = []
        for idx, var in enumerate(item.variacoes):
            letra = int_to_letters(idx)
            codigo = f"{numero_amostra}-{letra}"
            variacao_id = _new_id()
            
            variacao = {
                "id": variacao_id,
                "codigo": codigo,
                "letra": letra,
                "descricao_aplicacao": var.descricao_aplicacao,
                "percentual_fragrancia": var.percentual_fragrancia,
                "referencia_fragrancia": var.referencia_fragrancia,
                "fr_codigo": var.fr_codigo or "",
                "custo_fragrancia": var.custo_fragrancia,
                "observacoes_especificas": var.observacoes_especificas,
                "status": "solicitada",
                "aprovacao_interna": False,
                "aprovacao_externa": False,
                "historico_status": [{
                    "de": "",
                    "para": "solicitada",
                    "data": now,
                    "usuario": user["name"],
                    "usuario_id": user["id"]
                }],
                "motivo_retrabalho": "",
                "historico_retrabalhos": [],
                "feedback_cliente": "",
                "direcoes_retrabalho": "",
                "resultado": "",
                "enviado_comercial_em": None,
                "aprovado_cliente_em": None,
                "reprovacao_motivo": "",
                "gera_sku": False,
                "sku_id": None,
                "pd_card_id": None  # Será preenchido quando criar o card no P&D
            }
            variacoes_data.append(variacao)
        
        # Se não houver variações, criar uma padrão
        if not variacoes_data:
            letra = "a"
            codigo = f"{numero_amostra}-{letra}"
            variacao_id = _new_id()
            variacao = {
                "id": variacao_id,
                "codigo": codigo,
                "letra": letra,
                "descricao_aplicacao": "",
                "percentual_fragrancia": None,
                "referencia_fragrancia": "",
                "custo_fragrancia": None,
                "observacoes_especificas": "",
                "status": "solicitada",
                "aprovacao_interna": False,
                "aprovacao_externa": False,
                "historico_status": [{
                    "de": "",
                    "para": "solicitada",
                    "data": now,
                    "usuario": user["name"],
                    "usuario_id": user["id"]
                }],
                "motivo_retrabalho": "",
                "historico_retrabalhos": [],
                "feedback_cliente": "",
                "direcoes_retrabalho": "",
                "resultado": "",
                "enviado_comercial_em": None,
                "aprovado_cliente_em": None,
                "reprovacao_motivo": "",
                "gera_sku": False,
                "sku_id": None,
                "pd_card_id": None
            }
            variacoes_data.append(variacao)
        
        sample = {
            "id": sample_id,
            "tenant_id": user["tenant_id"],
            "projeto_id": data.projeto_id,
            "projeto_nome": project["nome_projeto"],
            "cliente_id": project["cliente_id"],
            "cliente_nome": project.get("cliente_nome", ""),
            "numero_amostra": str(numero_amostra),
            "nome_produto": item.nome_produto,
            "categoria": item.categoria,
            "briefing_base": item.briefing_base,
            "responsavel_pd": item.responsavel_pd,
            "parametro_variacao": item.parametro_variacao,
            "tipo_amostra": item.tipo_amostra,
            "referencia_formula": item.referencia_formula,
            "quantidade_por_variacao": item.quantidade_por_variacao,
            "unidade_quantidade": item.unidade_quantidade,
            "prazo_entrega_cliente": item.prazo_entrega_cliente,
            "briefing_especifico": item.briefing_especifico,
            "feedback_cliente": item.feedback_cliente,
            "direcoes_retrabalho": item.direcoes_retrabalho,
            "resultado": item.resultado,
            "aprovacao_interna": False,
            "aprovacao_externa": False,
            "data_envio": None,
            "enviado_comercial_em": None,
            "aprovado_cliente_em": None,
            "reprovacao_motivo": "",
            "tem_variacoes": len(variacoes_data) > 1,
            "variacoes": variacoes_data,
            # Campos de briefing (herdados pelas variações)
            "produto": item.produto,
            "objetivo_projeto": item.objetivo_projeto,
            "aplicacoes_desenvolver": item.aplicacoes_desenvolver,
            "ativos_claims": item.ativos_claims,
            "referencias": item.referencias,
            "referencias_fotos": item.referencias_fotos,
            "orcamento_projeto": item.orcamento_projeto,
            "textura_esperada": item.textura_esperada,
            "aplicacao": item.aplicacao,
            "sensorial": item.sensorial,
            "ph": item.ph,
            "observacao_tecnica": item.observacao_tecnica,
            "stage": "solicitada",
            "rework_de_amostra_id": None,
            "rework_motivo": "",
            # R02: snapshot dos campos ricos do projeto no momento da criação
            "projeto_briefing": {
                "publico_alvo": project.get("publico_alvo", ""),
                "posicionamento": project.get("posicionamento", ""),
                "tipo_servico": project.get("tipo_servico", ""),
                "faixa_preco_venda": project.get("faixa_preco_venda"),
                "volume_estimado_pedido": project.get("volume_estimado_pedido"),
                "restricoes_tecnicas": project.get("restricoes_tecnicas", []),
                "observacoes_livres": project.get("observacoes_livres", ""),
                "responsavel_comercial": project.get("responsavel_comercial", ""),
            },
            "created_by": user["id"],
            "created_by_name": user["name"],
            "created_at": now,
            "updated_at": now,
        }
        # R02: inheritance do projeto → amostra (preenche campos vazios)
        inherit(sample, project, INHERITED_FROM_PROJECT)

        await pg_db.execute(
            """INSERT INTO crm_samples (
                id, tenant_id, projeto_id, projeto_nome, cliente_id, cliente_nome,
                numero_amostra, nome_produto, categoria, briefing_base, responsavel_pd,
                parametro_variacao, tipo_amostra, referencia_formula, quantidade_por_variacao,
                unidade_quantidade, prazo_entrega_cliente, briefing_especifico, feedback_cliente,
                direcoes_retrabalho, resultado, aprovacao_interna, aprovacao_externa,
                data_envio, enviado_comercial_em, aprovado_cliente_em, reprovacao_motivo,
                tem_variacoes, variacoes, produto, objetivo_projeto, aplicacoes_desenvolver,
                ativos_claims, referencias, referencias_fotos, orcamento_projeto, textura_esperada,
                aplicacao, sensorial, ph, observacao_tecnica, stage, rework_de_amostra_id,
                rework_motivo, projeto_briefing, historico_movimentacoes,
                created_by, created_by_name, created_at, updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,
                $20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36,
                $37,$38,$39,$40,$41,$42,$43,$44,$45,$46,$47,$48,NOW(),NOW()
            )""",
            sample["id"], sample["tenant_id"], sample["projeto_id"], sample["projeto_nome"],
            sample["cliente_id"], sample.get("cliente_nome", ""),
            str(sample.get("numero_amostra", "")), sample.get("nome_produto", ""),
            sample.get("categoria", ""), sample.get("briefing_base", ""),
            sample.get("responsavel_pd", ""), sample.get("parametro_variacao", ""),
            sample.get("tipo_amostra", ""), sample.get("referencia_formula", ""),
            sample.get("quantidade_por_variacao"), sample.get("unidade_quantidade", "g"),
            sample.get("prazo_entrega_cliente", ""), sample.get("briefing_especifico", ""),
            sample.get("feedback_cliente", ""), sample.get("direcoes_retrabalho", ""),
            sample.get("resultado", ""), sample.get("aprovacao_interna", False),
            sample.get("aprovacao_externa", False), sample.get("data_envio"),
            sample.get("enviado_comercial_em"), sample.get("aprovado_cliente_em"),
            sample.get("reprovacao_motivo", ""), sample.get("tem_variacoes", False),
            sample.get("variacoes", []), sample.get("produto", ""),
            sample.get("objetivo_projeto", ""), sample.get("aplicacoes_desenvolver", ""),
            sample.get("ativos_claims", ""), sample.get("referencias", ""),
            sample.get("referencias_fotos", []), sample.get("orcamento_projeto", ""),
            sample.get("textura_esperada", ""), sample.get("aplicacao", ""),
            sample.get("sensorial", ""), sample.get("ph", ""),
            sample.get("observacao_tecnica", ""), sample.get("stage", "solicitada"),
            sample.get("rework_de_amostra_id"), sample.get("rework_motivo", ""),
            sample.get("projeto_briefing", {}), sample.get("historico_movimentacoes", []),
            sample.get("created_by", ""), sample.get("created_by_name", "")
        )

        try:
            await audit_log(
                tenant_id=user["tenant_id"],
                user_id=user["id"],
                user_name=user.get("name", ""),
                action="sample_created",
                entity_type="sample",
                entity_id=sample_id,
                after={
                    "numero_amostra": sample["numero_amostra"],
                    "projeto_id": data.projeto_id,
                    "cliente_id": project["cliente_id"],
                    "nome_produto": sample["nome_produto"],
                    "variacoes": [v["codigo"] for v in variacoes_data],
                },
            )
        except Exception as _al_exc:
            logger.error(f"[batch_create_samples_v2] audit_log falhou (ignorado): {_al_exc}", exc_info=True)

        created_samples.append(sample)

        # Criar cards no P&D para cada variação
        for variacao in variacoes_data:
            try:
                await _create_pd_card_for_variacao(sample, variacao, user)
            except Exception as _pd_exc:
                logger.error(f"[batch_create_samples_v2] _create_pd_card_for_variacao falhou (ignorado): {_pd_exc}", exc_info=True)

    if _project_stage_rank(project.get("stage")) < _project_stage_rank("amostra_solicitada"):
        await _advance_project_stage_if_needed(
            data.projeto_id,
            "amostra_solicitada",
            user,
            movement_source="sample_batch_created",
        )

    logger.info(f"Batch created {len(created_samples)} samples (v2) with variations for project {data.projeto_id}")
    return {"created": created_samples, "count": len(created_samples)}


async def _ensure_pd_request_for_card(card: dict, user: dict) -> str:
    """Garante que existe um pd_request linkado ao pd_card. Retorna o pd_request_id.
    Cria sob demanda quando o card é proveniente de variação CRM (sem pd_request prévio).
    Permite que o clique no card P&D abra a tela completa de PDDetail (/pd/{id}).
    """
    existing_id = card.get("pd_request_id")
    if existing_id:
        # Backfill: garantir que development + fórmula inicial existem
        # (cards criados antes do bootstrap automático ainda podem estar sem dev)
        try:
            existing_dev = await db.pd_developments.find_one(
                {"pd_request_id": existing_id, "tenant_id": user["tenant_id"]}
            )
            if not existing_dev and card.get("amostra_id") and card.get("amostra_variacao_id"):
                await _bootstrap_pd_development_for_variacao(
                    pd_request_id=existing_id, card=card, user=user
                )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Backfill bootstrap failed for pd_request {existing_id}: {exc}")
        return existing_id

    now = _now_iso()
    req_id = _new_id()

    sample_id = card.get("amostra_id")
    variacao_id = card.get("amostra_variacao_id")
    cliente_id = card.get("cliente_id")

    # Build a description from briefing data so the operator sees everything
    desc_parts = []
    if card.get("objetivo_projeto"):
        desc_parts.append(f"Objetivo: {card['objetivo_projeto']}")
    if card.get("textura_esperada"):
        desc_parts.append(f"Textura: {card['textura_esperada']}")
    if card.get("aplicacao"):
        desc_parts.append(f"Aplicação: {card['aplicacao']}")
    if card.get("sensorial"):
        desc_parts.append(f"Sensorial: {card['sensorial']}")
    if card.get("ph"):
        desc_parts.append(f"pH: {card['ph']}")
    if card.get("ativos_claims"):
        desc_parts.append(f"Ativos/Claims: {card['ativos_claims']}")
    if card.get("aplicacoes_desenvolver"):
        desc_parts.append(f"Aplicações a desenvolver: {card['aplicacoes_desenvolver']}")
    if card.get("briefing_base"):
        desc_parts.append(f"\nBriefing base:\n{card['briefing_base']}")
    if card.get("briefing_especifico"):
        desc_parts.append(f"\nBriefing específico:\n{card['briefing_especifico']}")
    if card.get("descricao_aplicacao"):
        desc_parts.append(f"\nDescrição da aplicação (variação): {card['descricao_aplicacao']}")
    if card.get("observacoes_especificas"):
        desc_parts.append(f"Observações específicas: {card['observacoes_especificas']}")

    description = "\n".join(desc_parts).strip()

    # Volume from sample
    volume_str = ""
    if card.get("quantidade_por_variacao"):
        volume_str = f"{card['quantidade_por_variacao']}{card.get('unidade_quantidade', 'g')}"

    pd_request = {
        "id": req_id,
        "tenant_id": user["tenant_id"],
        "client_card_id": None,  # CRM v3 uses crm_clients (not cards). Set null.
        "client_name": card.get("cliente", ""),
        "project_name": card.get("projeto_nome") or card.get("produto") or variacao_id or req_id,
        "technical_name": f"{card.get('produto', '')} - {card.get('numero_completo', '')}".strip(" -"),
        "commercial_name": card.get("produto", ""),
        "internal_code": card.get("numero_completo", ""),
        "request_type": "Amostra",
        "category": card.get("tipo_amostra", ""),
        "description": description,
        "references": card.get("referencias", ""),
        "restrictions": "",
        "volume": volume_str,
        "packaging": "",
        "priority": "Normal",
        "deadline": card.get("prazo_entrega_cliente") or None,
        "status": "OPEN",
        "is_internal_research": False,
        "kickoff_completed": False,
        # Link back to CRM source
        "linked_amostra_id": sample_id,
        "linked_variacao_id": variacao_id,
        "linked_cliente_id": cliente_id,
        "linked_projeto_id": card.get("projeto_id"),
        "linked_pd_card_id": card.get("id"),
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": now,
        "updated_at": now,
    }

    await db.pd_requests.insert_one(pd_request)
    await db.pd_request_status_history.insert_one({
        "id": _new_id(),
        "pd_request_id": req_id,
        "from_status": None,
        "to_status": "OPEN",
        "changed_by": user["id"],
        "changed_by_name": user.get("name", ""),
        "comment": "Criado automaticamente a partir de variação CRM",
        "created_at": now,
    })

    # Link card -> pd_request
    await pg_db.execute(
        "UPDATE pd_cards SET pd_request_id=$1, updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        req_id, now, card["id"], user["tenant_id"]
    )
    card["pd_request_id"] = req_id

    # Auto-create development + initial formula pre-filled with briefing data
    # so the operator only needs to add raw materials/ingredients
    try:
        await _bootstrap_pd_development_for_variacao(
            pd_request_id=req_id, card=card, user=user
        )
    except Exception as exc:  # pragma: no cover
        logger.warning(f"Failed to bootstrap dev/formula for pd_request {req_id}: {exc}")

    logger.info(f"Auto-created pd_request {req_id} for pd_card {card.get('id')} (variação {card.get('numero_completo')})")
    return req_id


async def _bootstrap_pd_development_for_variacao(pd_request_id: str, card: dict, user: dict):
    """Cria development + fórmula v1 pré-preenchida a partir da variação CRM.
    Inclui a fragrância da variação como primeiro item (P&D só adiciona MPs/insumos).
    """
    sample_id = card.get("amostra_id")
    variacao_id = card.get("amostra_variacao_id")
    if not sample_id or not variacao_id:
        return

    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        return
    variacao = next(
        (v for v in sample.get("variacoes", []) if v.get("id") == variacao_id), None
    )
    if not variacao:
        return

    now = _now_iso()

    # Move pd_request to IN_PROGRESS so the dev/formula appear active
    await db.pd_requests.update_one(
        {"id": pd_request_id, "tenant_id": user["tenant_id"]},
        {"$set": {"status": "IN_PROGRESS", "updated_at": now}},
    )
    await db.pd_request_status_history.insert_one({
        "id": _new_id(),
        "pd_request_id": pd_request_id,
        "from_status": "OPEN",
        "to_status": "IN_PROGRESS",
        "changed_by": user["id"],
        "changed_by_name": user.get("name", ""),
        "comment": "Bootstrap automático: desenvolvimento + fórmula inicial criados a partir do briefing CRM",
        "created_at": now,
    })

    # 1) Development
    dev_id = _new_id()
    await db.pd_developments.insert_one({
        "id": dev_id,
        "pd_request_id": pd_request_id,
        "tenant_id": user["tenant_id"],
        "assigned_to": user["id"],
        "assigned_to_name": user.get("name", ""),
        "lab_responsible": None,
        "current_version": 1,
        "status": "active",
        "started_at": now,
        "completed_at": None,
    })

    # 2) Initial formula pre-filled
    quantidade = sample.get("quantidade_por_variacao") or 0.0
    unidade = (sample.get("unidade_quantidade") or "g").lower()
    if unidade in ("ml", "l"):
        volume_unit = "mL" if unidade == "ml" else "L"
    elif unidade in ("g", "kg"):
        volume_unit = unidade
    else:
        volume_unit = "g"

    notes_lines = [
        "Pré-preenchido automaticamente a partir do briefing CRM.",
        "→ P&D: adicionar MPs/insumos/ingredientes. Fragrância já está como item nº 1.",
        "",
    ]
    if sample.get("ph"):
        notes_lines.append(f"pH alvo: {sample['ph']}")
    if sample.get("textura_esperada"):
        notes_lines.append(f"Textura esperada: {sample['textura_esperada']}")
    if sample.get("sensorial"):
        notes_lines.append(f"Sensorial: {sample['sensorial']}")
    if sample.get("aplicacao"):
        notes_lines.append(f"Aplicação: {sample['aplicacao']}")
    if sample.get("ativos_claims"):
        notes_lines.append(f"Ativos/Claims obrigatórios: {sample['ativos_claims']}")
    if sample.get("orcamento_projeto"):
        notes_lines.append(f"Orçamento alvo: {sample['orcamento_projeto']}")
    if variacao.get("descricao_aplicacao"):
        notes_lines.append("")
        notes_lines.append(f"Variação {variacao.get('codigo', '')}: {variacao['descricao_aplicacao']}")
    if variacao.get("observacoes_especificas"):
        notes_lines.append(f"Observações específicas: {variacao['observacoes_especificas']}")

    formula_id = _new_id()
    formula_name = f"Manipulação {variacao.get('codigo', '')} — {sample.get('nome_produto', '')} v1".strip()
    await db.pd_formulas.insert_one({
        "id": formula_id,
        "tenant_id": user["tenant_id"],
        "development_id": dev_id,
        "version": 1,
        "name": formula_name,
        "notes": "\n".join(notes_lines).strip(),
        "volume": float(quantidade or 0.0),
        "volume_unit": volume_unit,
        "indice_perdas": 0.0,
        "cotacao_usd": 6.00,
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": now,
    })

    # 3) Fragrance pre-filled as first item (if available)
    if variacao.get("percentual_fragrancia") is not None and float(variacao.get("percentual_fragrancia") or 0) > 0:
        ref_frag = variacao.get("referencia_fragrancia") or "Fragrância da variação"
        pct = float(variacao.get("percentual_fragrancia") or 0)
        custo_kg = float(variacao.get("custo_fragrancia") or 0)
        cotacao = 6.00
        cost_brl = round((pct / 100.0) * custo_kg, 4)
        cost_kg_usd = round((custo_kg / cotacao) if cotacao else 0.0, 4)
        item_id = _new_id()
        await db.pd_formula_items.insert_one({
            "id": item_id,
            "formula_id": formula_id,
            "ingredient_name": ref_frag,
            "percentage": pct,
            "price_per_kg": custo_kg,
            "cost_brl": cost_brl,
            "cost_kg_usd": cost_kg_usd,
            "fornecedor": "",
            "phase": "Fragrância",
            "function": "Fragrância",
            "catalog_id": None,
        })

    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="pd_dev_bootstrap_from_variacao",
        entity_type="pd_request",
        entity_id=pd_request_id,
        after={
            "development_id": dev_id,
            "formula_id": formula_id,
            "variacao_codigo": variacao.get("codigo"),
            "amostra_id": sample_id,
        },
    )


async def _create_pd_card_for_variacao(sample: dict, variacao: dict, user: dict):
    """Cria um card no Pipeline P&D para uma variação de amostra (ERP v3.0)."""
    now = _now_iso()
    card_id = _new_id()
    
    card = {
        "id": card_id,
        "tenant_id": user["tenant_id"],
        "tipo": "amostra",
        "numero_completo": variacao["codigo"],
        "produto": sample.get("nome_produto", sample.get("produto", "")),
        "cliente": sample.get("cliente_nome", ""),
        "cliente_id": sample.get("cliente_id"),
        "projeto_id": sample.get("projeto_id"),
        "projeto_nome": sample.get("projeto_nome", ""),
        "amostra_id": sample["id"],
        "amostra_numero": sample.get("numero_amostra", ""),
        "amostra_variacao_id": variacao["id"],
        "descricao_aplicacao": variacao.get("descricao_aplicacao", ""),
        "briefing_base": sample.get("briefing_base", ""),
        "parametro_variacao": sample.get("parametro_variacao", ""),
        "tipo_amostra": sample.get("tipo_amostra", ""),
        "referencia_formula": sample.get("referencia_formula", ""),
        "quantidade_por_variacao": sample.get("quantidade_por_variacao"),
        "unidade_quantidade": sample.get("unidade_quantidade", ""),
        "prazo_entrega_cliente": sample.get("prazo_entrega_cliente", ""),
        "briefing_especifico": sample.get("briefing_especifico", ""),
        "feedback_cliente": variacao.get("feedback_cliente") or sample.get("feedback_cliente", ""),
        "direcoes_retrabalho": variacao.get("direcoes_retrabalho") or sample.get("direcoes_retrabalho", ""),
        # ERP v3.0: inheritance from sample (briefing técnico, ph, sensorial, etc.)
        "objetivo_projeto": sample.get("objetivo_projeto", ""),
        "aplicacoes_desenvolver": sample.get("aplicacoes_desenvolver", ""),
        "ativos_claims": sample.get("ativos_claims", ""),
        "referencias": sample.get("referencias", ""),
        "textura_esperada": sample.get("textura_esperada", ""),
        "aplicacao": sample.get("aplicacao", ""),
        "sensorial": sample.get("sensorial", ""),
        "ph": sample.get("ph", ""),
        "observacoes_especificas": variacao.get("observacoes_especificas", ""),
        "responsavel_pd": sample.get("responsavel_pd", ""),
        # R02: campos contextuais do projeto (para Detalhes da Solicitação no P&D)
        "publico_alvo": sample.get("projeto_briefing", {}).get("publico_alvo", ""),
        "posicionamento": sample.get("projeto_briefing", {}).get("posicionamento", ""),
        "tipo_servico": sample.get("projeto_briefing", {}).get("tipo_servico", ""),
        "faixa_preco_venda": sample.get("projeto_briefing", {}).get("faixa_preco_venda"),
        "volume_estimado_pedido": sample.get("projeto_briefing", {}).get("volume_estimado_pedido"),
        "restricoes_tecnicas": sample.get("projeto_briefing", {}).get("restricoes_tecnicas", []),
        "observacoes_livres": sample.get("projeto_briefing", {}).get("observacoes_livres", ""),
        "data_solicitacao": now,
        "prazo_prometido": None,
        "status_pd": "solicitado",
        "historico_movimentacoes": [{
            "de": "",
            "para": "solicitado",
            "data": now,
            "usuario": user["name"],
            "usuario_id": user["id"]
        }],
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    
    extra = {k: v for k, v in card.items() if k not in {
        "id", "tenant_id", "amostra_id", "amostra_variacao_id",
        "pd_request_id", "status_pd", "executor_id", "executor_name",
        "atribuido_em", "atribuido_por", "atribuido_por_nome",
        "extra", "created_at", "updated_at"
    }}
    await pg_db.execute(
        """INSERT INTO pd_cards (
            id, tenant_id, amostra_id, amostra_variacao_id, pd_request_id,
            status_pd, extra, created_at, updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,NOW(),NOW())""",
        card_id, user["tenant_id"], sample["id"], variacao["id"], None,
        card.get("status_pd", "solicitado"), extra
    )

    # Atualizar variação com o card_id
    await _update_variacao_in_sample(sample["id"], user["tenant_id"], variacao["id"], {"pd_card_id": card_id})

    try:
        await audit_log(
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            user_name=user.get("name", ""),
            action="pd_card_auto_created",
            entity_type="pd_card",
            entity_id=card_id,
            after={
                "numero_completo": variacao["codigo"],
                "amostra_id": sample["id"],
                "variacao_id": variacao["id"],
                "trigger": "sample_creation",
            },
        )
    except Exception as _al_exc:
        logger.error(f"[_create_pd_card_for_variacao] audit_log falhou (ignorado): {_al_exc}", exc_info=True)

    logger.info(f"Created P&D card {card_id} for variação {variacao['codigo']}")
    # pd_request é criado sob demanda quando o formulador abre o card (GET /pd/cards/{id}).
    # Não criamos aqui para evitar o log "Auto-created pd_request" em toda variação CRM.


@crm_router.get("/samples")
async def list_samples(
    request: Request,
    projeto_id: Optional[str] = None,
    cliente_id: Optional[str] = None,
    stage: Optional[str] = None,
    search: Optional[str] = None,
):
    user = await _get_current_user(request)
    sql = "SELECT * FROM crm_samples WHERE tenant_id=$1"
    params: list = [user["tenant_id"]]
    if projeto_id:
        params.append(projeto_id); sql += f" AND projeto_id=${len(params)}"
    if cliente_id:
        params.append(cliente_id); sql += f" AND cliente_id=${len(params)}"
    if stage:
        params.append(stage); sql += f" AND stage=${len(params)}"
    if search:
        params.append(f"%{search}%"); n = len(params)
        sql += (f" AND (nome_amostra ILIKE ${n} OR nome_produto ILIKE ${n}"
                f" OR numero_amostra ILIKE ${n} OR projeto_nome ILIKE ${n}"
                f" OR cliente_nome ILIKE ${n})")
    sql += " ORDER BY created_at DESC LIMIT 5000"
    samples = _rows(await pg_db.fetch_all(sql, *params))
    return samples


@crm_router.get("/samples/{sample_id}")
async def get_sample(sample_id: str, request: Request):
    user = await _get_current_user(request)
    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")
    return sample


@crm_router.put("/samples/{sample_id}")
async def update_sample(sample_id: str, data: SampleUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL | PD_FULL)
    update_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}

    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    update_fields["updated_at"] = _now_iso()
    fields = list(update_fields.keys())
    params: list = [update_fields[k] for k in fields]
    set_clause = ", ".join(f"{k}=${i+1}" for i, k in enumerate(fields))
    params.extend([sample_id, user["tenant_id"]])
    matched = await pg_db.fetch_val(
        f"UPDATE crm_samples SET {set_clause} WHERE id=${len(params)-1} AND tenant_id=${len(params)} RETURNING id",
        *params
    )
    if not matched:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")

    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    return sample


@crm_router.put("/samples/{sample_id}/move")
async def move_sample(sample_id: str, data: SampleMove, request: Request):
    user = await _get_current_user(request)
    require_roles(user, COMERCIAL_FULL | PD_FULL)
    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")

    old_stage = sample.get("stage", "solicitada")
    new_stage = data.stage

    if new_stage not in SAMPLE_STAGES:
        raise HTTPException(status_code=400, detail=f"Estágio inválido: {new_stage}")

    # ERP v3.0: Retrabalho NÃO é uma transição de estágio simples — exige criar NOVA amostra.
    if new_stage == "retrabalho":
        raise HTTPException(
            status_code=400,
            detail="Retrabalho deve gerar nova amostra (use POST /samples/{id}/rework). "
                   "Variações usam #N/letra; retrabalho gera novo número global."
        )

    allowed = SAMPLE_TRANSITIONS.get(old_stage, [])
    if new_stage not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transição não permitida: {STAGE_LABELS.get(old_stage)} → {STAGE_LABELS.get(new_stage)}"
        )

    # Blocking tasks
    await assert_no_blocking_tasks(
        tenant_id=user["tenant_id"],
        entity_type="sample",
        entity_id=sample_id,
        target_stage=new_stage,
    )

    # Validate motivo for reprovada
    if new_stage == "reprovada" and not data.motivo_retrabalho:
        raise HTTPException(status_code=400, detail="Motivo da reprovação é obrigatório")
    if new_stage == "aprovada":
        raise HTTPException(
            status_code=422,
            detail="Aprovação direta não é permitida. Registre o envio e depois o resultado do cliente.",
        )

    now = _now_iso()
    update_data = {
        "stage": new_stage,
        "aprovacao_interna": sample.get("aprovacao_interna", False),
        "aprovacao_externa": sample.get("aprovacao_externa", False),
    }
    if new_stage == "enviada":
        update_data["data_envio"] = now
        update_data["enviado_comercial_em"] = now
        update_data["aprovacao_interna"] = True
    if new_stage == "reprovada":
        update_data["resultado"] = "reprovada"
        update_data["aprovacao_externa"] = False
        update_data["reprovacao_motivo"] = data.motivo_retrabalho or data.feedback_cliente or ""
        if data.feedback_cliente:
            update_data["feedback_cliente"] = data.feedback_cliente
    if data.direcoes_retrabalho:
        update_data["direcoes_retrabalho"] = data.direcoes_retrabalho

    push_ops = {
        "historico_movimentacoes": {
            "de": old_stage,
            "para": new_stage,
            "data": now,
            "usuario": user["name"],
            "usuario_id": user["id"],
        }
    }

    if new_stage == "reprovada" and data.motivo_retrabalho:
        update_data["motivo_retrabalho"] = data.motivo_retrabalho

    movement = push_ops["historico_movimentacoes"]
    set_parts = ["historico_movimentacoes = historico_movimentacoes || jsonb_build_array($1::jsonb)", "updated_at=NOW()"]
    params: list = [json.dumps(movement)]
    for k, v in update_data.items():
        params.append(v); set_parts.append(f"{k}=${len(params)}")
    params.extend([sample_id, user["tenant_id"]])
    await pg_db.execute(
        f"UPDATE crm_samples SET {', '.join(set_parts)} WHERE id=${len(params)-1} AND tenant_id=${len(params)}",
        *params
    )

    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))

    new_tasks = []
    try:
        new_tasks = await trigger_tasks_for_transition(
            entity_type="sample",
            entity_id=sample_id,
            tenant_id=user["tenant_id"],
            old_stage=old_stage,
            new_stage=new_stage,
            user=user,
        )
    except Exception as exc:
        logger.error(f"[move_sample] trigger_tasks_for_transition falhou (ignorado): {exc}", exc_info=True)

    try:
        await audit_log(
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            user_name=user.get("name", ""),
            action="sample_moved",
            entity_type="sample",
            entity_id=sample_id,
            before={"stage": old_stage},
            after={"stage": new_stage, "motivo": update_data.get("motivo_retrabalho")},
            metadata={"tasks_generated": [t["id"] for t in new_tasks]},
        )
    except Exception as exc:
        logger.error(f"[move_sample] audit_log falhou (ignorado): {exc}", exc_info=True)

    # TRIGGER: Auto-create SKU when sample is approved
    sku_created = None
    if new_stage == "aprovada":
        sku_created = await _create_sku_from_sample(updated, user)
        await _advance_project_stage_if_needed(
            updated["projeto_id"],
            "em_negociacao",
            user,
            movement_source="sample_approved",
        )
    elif new_stage == "em_elaboracao":
        await _advance_project_stage_if_needed(
            updated["projeto_id"],
            "amostra_em_desenvolvimento",
            user,
            movement_source="sample_in_development",
            extra_set={"data_inicio_desenvolvimento": now},
        )
    elif new_stage == "enviada":
        await _advance_project_stage_if_needed(
            updated["projeto_id"],
            "amostra_enviada",
            user,
            movement_source="sample_sent",
            extra_set={"data_ultima_amostra_enviada": now},
        )

    await _sync_pd_cards_from_crm_stage(
        tenant_id=user["tenant_id"],
        sample_id=sample_id,
        user=user,
        now=now,
        crm_stage=new_stage,
        feedback_cliente=update_data.get("feedback_cliente", ""),
        direcoes_retrabalho=update_data.get("direcoes_retrabalho", ""),
        resultado_cliente=update_data.get("resultado", ""),
    )

    return {
        "sample": updated,
        "from_stage": STAGE_LABELS.get(old_stage, old_stage),
        "to_stage": STAGE_LABELS.get(new_stage, new_stage),
        "sku_created": sku_created,
        "tasks_generated": new_tasks,
    }


# ======================================================================
#  ERP v3.0 — REWORK = NEW SAMPLE WITH NEW GLOBAL NUMBER
# ======================================================================

class SampleReworkInput(BaseModel):
    motivo: str
    origem: str = "interna"  # interna | cliente
    variacao_id: Optional[str] = None  # se referencia uma variação específica
    nome_produto: Optional[str] = None
    observacoes_especificas: str = ""
    feedback_cliente: str = ""
    direcoes_retrabalho: str = ""


@crm_router.post("/samples/{sample_id}/rework")
async def create_rework_sample(sample_id: str, data: SampleReworkInput, request: Request):
    """ERP v3.0: Retrabalho gera NOVA amostra com NOVO número global.
    A amostra original permanece imutável (mas registra o retrabalho no histórico)."""
    user = await _get_current_user(request)

    original = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not original:
        raise HTTPException(status_code=404, detail="Amostra original não encontrada")

    if not data.motivo:
        raise HTTPException(status_code=400, detail="Motivo do retrabalho é obrigatório")

    if not clean_text(data.feedback_cliente) or not clean_text(data.direcoes_retrabalho):
        raise HTTPException(status_code=400, detail="Retrabalho exige feedback_cliente e direcoes_retrabalho")

    project = await assert_project_exists(user["tenant_id"], original["projeto_id"])

    now = _now_iso()
    novo_numero = await next_sample_code(user["tenant_id"])

    # Determinar variação base para herança (se especificada)
    base_variacao = None
    if data.variacao_id:
        base_variacao = next(
            (v for v in original.get("variacoes", []) if v["id"] == data.variacao_id), None
        )

    nova_letra = "a"
    nova_var_id = _new_id()
    nova_variacao = {
        "id": nova_var_id,
        "codigo": f"{novo_numero}-{nova_letra}",
        "letra": nova_letra,
        "descricao_aplicacao": (base_variacao or {}).get("descricao_aplicacao", ""),
        "percentual_fragrancia": (base_variacao or {}).get("percentual_fragrancia"),
        "referencia_fragrancia": (base_variacao or {}).get("referencia_fragrancia", ""),
        "custo_fragrancia": (base_variacao or {}).get("custo_fragrancia"),
        "observacoes_especificas": data.observacoes_especificas
            or (base_variacao or {}).get("observacoes_especificas", ""),
        "status": "solicitada",
        "aprovacao_interna": False,
        "aprovacao_externa": False,
        "historico_status": [{
            "de": "",
            "para": "solicitada",
            "data": now,
            "usuario": user["name"],
            "usuario_id": user["id"],
            "trigger": "retrabalho",
        }],
        "motivo_retrabalho": "",
        "historico_retrabalhos": [],
        "feedback_cliente": data.feedback_cliente or (base_variacao or {}).get("feedback_cliente", ""),
        "direcoes_retrabalho": data.direcoes_retrabalho,
        "resultado": "",
        "enviado_comercial_em": None,
        "aprovado_cliente_em": None,
        "reprovacao_motivo": "",
        "gera_sku": False,
        "sku_id": None,
        "pd_card_id": None,
    }

    nova_sample_id = _new_id()
    nova_sample = {
        "id": nova_sample_id,
        "tenant_id": user["tenant_id"],
        "projeto_id": original["projeto_id"],
        "projeto_nome": original.get("projeto_nome", ""),
        "cliente_id": original["cliente_id"],
        "cliente_nome": original.get("cliente_nome", ""),
        "numero_amostra": str(novo_numero),
        "nome_produto": data.nome_produto or original.get("nome_produto", ""),
        "categoria": original.get("categoria", ""),
        "briefing_base": original.get("briefing_base", ""),
        "responsavel_pd": original.get("responsavel_pd", ""),
        "parametro_variacao": original.get("parametro_variacao", ""),
        "tipo_amostra": original.get("tipo_amostra", ""),
        "referencia_formula": original.get("referencia_formula", ""),
        "quantidade_por_variacao": original.get("quantidade_por_variacao"),
        "unidade_quantidade": original.get("unidade_quantidade", ""),
        "prazo_entrega_cliente": original.get("prazo_entrega_cliente", ""),
        "briefing_especifico": original.get("briefing_especifico", ""),
        "feedback_cliente": data.feedback_cliente,
        "direcoes_retrabalho": data.direcoes_retrabalho,
        "resultado": "",
        "aprovacao_interna": False,
        "aprovacao_externa": False,
        "data_envio": None,
        "enviado_comercial_em": None,
        "aprovado_cliente_em": None,
        "reprovacao_motivo": "",
        "tem_variacoes": False,
        "variacoes": [nova_variacao],
        "produto": original.get("produto", ""),
        "objetivo_projeto": original.get("objetivo_projeto", ""),
        "aplicacoes_desenvolver": original.get("aplicacoes_desenvolver", ""),
        "ativos_claims": original.get("ativos_claims", ""),
        "referencias": original.get("referencias", ""),
        "referencias_fotos": original.get("referencias_fotos", []),
        "orcamento_projeto": original.get("orcamento_projeto", ""),
        "textura_esperada": original.get("textura_esperada", ""),
        "aplicacao": original.get("aplicacao", ""),
        "sensorial": original.get("sensorial", ""),
        "ph": original.get("ph", ""),
        "observacao_tecnica": original.get("observacao_tecnica", ""),
        "stage": "solicitada",
        "rework_de_amostra_id": original["id"],
        "rework_de_numero": original.get("numero_amostra", ""),
        "rework_motivo": data.motivo,
        "rework_origem": data.origem,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    inherit(nova_sample, project, INHERITED_FROM_PROJECT)
    await pg_db.execute(
        """INSERT INTO crm_samples (
            id, tenant_id, projeto_id, projeto_nome, cliente_id, cliente_nome,
            numero_amostra, nome_produto, categoria, briefing_base, responsavel_pd,
            parametro_variacao, tipo_amostra, referencia_formula, quantidade_por_variacao,
            unidade_quantidade, prazo_entrega_cliente, briefing_especifico, feedback_cliente,
            direcoes_retrabalho, resultado, aprovacao_interna, aprovacao_externa,
            data_envio, enviado_comercial_em, aprovado_cliente_em, reprovacao_motivo,
            tem_variacoes, variacoes, produto, objetivo_projeto, aplicacoes_desenvolver,
            ativos_claims, referencias, referencias_fotos, orcamento_projeto, textura_esperada,
            aplicacao, sensorial, ph, observacao_tecnica, stage, rework_de_amostra_id,
            rework_motivo, historico_movimentacoes, created_by, created_by_name, created_at, updated_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,
            $20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36,
            $37,$38,$39,$40,$41,$42,$43,$44,$45,$46,$47,NOW(),NOW()
        )""",
        nova_sample["id"], nova_sample["tenant_id"], nova_sample["projeto_id"],
        nova_sample.get("projeto_nome", ""), nova_sample["cliente_id"],
        nova_sample.get("cliente_nome", ""), str(nova_sample.get("numero_amostra", "")),
        nova_sample.get("nome_produto", ""), nova_sample.get("categoria", ""),
        nova_sample.get("briefing_base", ""), nova_sample.get("responsavel_pd", ""),
        nova_sample.get("parametro_variacao", ""), nova_sample.get("tipo_amostra", ""),
        nova_sample.get("referencia_formula", ""), nova_sample.get("quantidade_por_variacao"),
        nova_sample.get("unidade_quantidade", "g"), nova_sample.get("prazo_entrega_cliente", ""),
        nova_sample.get("briefing_especifico", ""), nova_sample.get("feedback_cliente", ""),
        nova_sample.get("direcoes_retrabalho", ""), nova_sample.get("resultado", ""),
        nova_sample.get("aprovacao_interna", False), nova_sample.get("aprovacao_externa", False),
        nova_sample.get("data_envio"), nova_sample.get("enviado_comercial_em"),
        nova_sample.get("aprovado_cliente_em"), nova_sample.get("reprovacao_motivo", ""),
        nova_sample.get("tem_variacoes", False), nova_sample.get("variacoes", []),
        nova_sample.get("produto", ""), nova_sample.get("objetivo_projeto", ""),
        nova_sample.get("aplicacoes_desenvolver", ""), nova_sample.get("ativos_claims", ""),
        nova_sample.get("referencias", ""), nova_sample.get("referencias_fotos", []),
        nova_sample.get("orcamento_projeto", ""), nova_sample.get("textura_esperada", ""),
        nova_sample.get("aplicacao", ""), nova_sample.get("sensorial", ""),
        nova_sample.get("ph", ""), nova_sample.get("observacao_tecnica", ""),
        nova_sample.get("stage", "solicitada"), nova_sample.get("rework_de_amostra_id"),
        nova_sample.get("rework_motivo", ""), [],
        nova_sample.get("created_by", ""), nova_sample.get("created_by_name", "")
    )

    # Marcar a original com referência ao retrabalho gerado
    rework_entry = {
        "data": now, "motivo": data.motivo, "origem": data.origem,
        "nova_amostra_id": nova_sample_id, "novo_numero": str(novo_numero),
        "usuario": user["name"], "usuario_id": user["id"],
    }
    await pg_db.execute(
        """UPDATE crm_samples SET
            feedback_cliente=$1, direcoes_retrabalho=$2, resultado=$3, updated_at=$4,
            historico_movimentacoes = historico_movimentacoes || jsonb_build_array($5::jsonb)
           WHERE id=$6 AND tenant_id=$7""",
        data.feedback_cliente, data.direcoes_retrabalho, "retrabalho", now,
        json.dumps(rework_entry), original["id"], user["tenant_id"]
    )
    if data.variacao_id:
        await _update_variacao_in_sample(
            original["id"], user["tenant_id"], data.variacao_id,
            {
                "motivo_retrabalho": data.motivo,
                "feedback_cliente": data.feedback_cliente,
                "direcoes_retrabalho": data.direcoes_retrabalho,
                "resultado": "retrabalho",
            }
        )

    # Criar P&D card para a nova variação
    await _create_pd_card_for_variacao(nova_sample, nova_variacao, user)

    await audit_log(
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="sample_rework_created",
        entity_type="sample",
        entity_id=nova_sample_id,
        before={"original_id": original["id"], "original_numero": original.get("numero_amostra")},
        after={"novo_numero": str(novo_numero), "motivo": data.motivo, "origem": data.origem},
        metadata={"projeto_id": original["projeto_id"], "cliente_id": original["cliente_id"]},
    )

    return {
        "rework_sample": nova_sample,
        "original_id": original["id"],
        "novo_numero": str(novo_numero),
    }


@crm_router.put("/samples/{sample_id}/variacoes/{variacao_id}")
async def update_variacao(sample_id: str, variacao_id: str, data: VariacaoUpdate, request: Request):
    """Atualizar uma variação específica de uma amostra"""
    user = await _get_current_user(request)
    
    update_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    
    sample = _row(await pg_db.fetch_one(
        "SELECT variacoes FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra ou variação não encontrada")
    variacoes = sample.get("variacoes") or []
    target = next((v for v in variacoes if v.get("id") == variacao_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Amostra ou variação não encontrada")

    target.update(update_fields)
    target["updated_at"] = _now_iso()
    await pg_db.execute(
        "UPDATE crm_samples SET variacoes=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        variacoes, sample_id, user["tenant_id"]
    )
    return _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))


@crm_router.put("/samples/{sample_id}/variacoes/{variacao_id}/move")
async def move_variacao(sample_id: str, variacao_id: str, data: VariacaoMove, request: Request):
    """Mover uma variação entre status — bloqueado para perfis comerciais (CRM é read-only)."""
    user = await _get_current_user(request)

    # REGRA DE NEGÓCIO: status da variação é controlado exclusivamente pelo P&D.
    # Perfis comerciais não podem mover variações; apenas registram resultado do cliente
    # via POST /samples/{id}/variacoes/{vid}/resultado-cliente.
    _COMERCIAL_ROLES = {"vendedor", "sales_ops", "sucesso_cliente"}
    from rbac import normalize_role
    if normalize_role(user.get("role", "")) in _COMERCIAL_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "sem_permissao",
                "message": "O status da variação é controlado pelo setor P&D. "
                           "Para atualizar, o formulador deve mover o card no Pipeline P&D.",
                "instrucao": "Acesse Pipeline P&D para ver o progresso desta amostra.",
            },
        )

    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")

    # Encontrar a variação
    variacao = next((v for v in sample.get("variacoes", []) if v["id"] == variacao_id), None)
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")
    
    old_status = variacao["status"]
    new_status = data.status
    
    # Validar transição
    if new_status not in SAMPLE_STAGES:
        raise HTTPException(status_code=400, detail=f"Status inválido: {new_status}")

    # ERP v3.0: Retrabalho exige uso do endpoint /samples/{id}/rework (gera novo nº global)
    if new_status == "retrabalho":
        raise HTTPException(
            status_code=400,
            detail="Retrabalho não move variação — gera nova amostra. Use POST /api/crm/samples/{sample_id}/rework",
        )

    allowed = SAMPLE_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transição não permitida: {STAGE_LABELS.get(old_status)} → {STAGE_LABELS.get(new_status)}"
        )

    # ERP v3.0: blocking tasks
    await assert_no_blocking_tasks(
        tenant_id=user["tenant_id"],
        entity_type="variacao",
        entity_id=variacao_id,
        target_stage=new_status,
    )

    # Validar motivo de reprovação
    if new_status == "reprovada" and not data.motivo_retrabalho:
        raise HTTPException(status_code=400, detail="Motivo da reprovação é obrigatório")
    if new_status == "aprovada":
        raise HTTPException(
            status_code=422,
            detail="Aprovação direta não é permitida. Registre o envio e depois o resultado do cliente.",
        )
    
    now = _now_iso()
    
    # Atualizar status da variação
    set_ops = {
        "variacoes.$.status": new_status,
        "variacoes.$.updated_at": now,
        "variacoes.$.aprovacao_interna": variacao.get("aprovacao_interna", False),
        "variacoes.$.aprovacao_externa": variacao.get("aprovacao_externa", False),
        "updated_at": now
    }
    if new_status == "enviada":
        set_ops["data_envio"] = now
        set_ops["variacoes.$.enviado_comercial_em"] = now
        set_ops["variacoes.$.aprovacao_interna"] = True
    if new_status == "reprovada":
        set_ops["variacoes.$.resultado"] = "reprovada"
        set_ops["variacoes.$.aprovacao_externa"] = False
        set_ops["variacoes.$.reprovacao_motivo"] = data.motivo_retrabalho or data.feedback_cliente or ""
    if data.feedback_cliente:
        set_ops["variacoes.$.feedback_cliente"] = data.feedback_cliente
    if data.direcoes_retrabalho:
        set_ops["variacoes.$.direcoes_retrabalho"] = data.direcoes_retrabalho
    
    push_ops = {
        "variacoes.$.historico_status": {
            "de": old_status,
            "para": new_status,
            "data": now,
            "usuario": user["name"],
            "usuario_id": user["id"]
        }
    }
    
    if new_status == "reprovada" and data.motivo_retrabalho:
        set_ops["variacoes.$.motivo_retrabalho"] = data.motivo_retrabalho
    if data.origem_retrabalho:
        set_ops["variacoes.$.origem_retrabalho"] = data.origem_retrabalho
    
    var_updates = {
        "status": new_status,
        "updated_at": now,
        "aprovacao_interna": set_ops.get("variacoes.$.aprovacao_interna", variacao.get("aprovacao_interna", False)),
        "aprovacao_externa": set_ops.get("variacoes.$.aprovacao_externa", variacao.get("aprovacao_externa", False)),
    }
    if new_status == "enviada":
        var_updates["enviado_comercial_em"] = now
        var_updates["aprovacao_interna"] = True
    if new_status == "reprovada":
        var_updates["resultado"] = "reprovada"
        var_updates["aprovacao_externa"] = False
        var_updates["reprovacao_motivo"] = data.motivo_retrabalho or data.feedback_cliente or ""
    if data.feedback_cliente:
        var_updates["feedback_cliente"] = data.feedback_cliente
    if data.direcoes_retrabalho:
        var_updates["direcoes_retrabalho"] = data.direcoes_retrabalho
    if new_status == "reprovada" and data.motivo_retrabalho:
        var_updates["motivo_retrabalho"] = data.motivo_retrabalho
    if data.origem_retrabalho:
        var_updates["origem_retrabalho"] = data.origem_retrabalho

    await _update_variacao_in_sample(sample_id, user["tenant_id"], variacao_id, var_updates)
    hist_entry = {"de": old_status, "para": new_status, "data": now, "usuario": user["name"], "usuario_id": user["id"]}
    await _push_variacao_history(sample_id, user["tenant_id"], variacao_id, hist_entry)
    if new_status == "enviada":
        await pg_db.execute(
            "UPDATE crm_samples SET data_envio=$1, updated_at=$2 WHERE id=$3 AND tenant_id=$4",
            now, now, sample_id, user["tenant_id"]
        )

    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))

    new_tasks = []
    try:
        new_tasks = await trigger_tasks_for_transition(
            entity_type="variacao",
            entity_id=variacao_id,
            tenant_id=user["tenant_id"],
            old_stage=old_status,
            new_stage=new_status,
            user=user,
        )
    except Exception as exc:
        logger.error(f"[move_variacao] trigger_tasks_for_transition falhou (ignorado): {exc}", exc_info=True)

    try:
        await audit_log(
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            user_name=user.get("name", ""),
            action="variacao_moved",
            entity_type="variacao",
            entity_id=variacao_id,
            before={"status": old_status},
            after={"status": new_status},
            metadata={"sample_id": sample_id, "tasks_generated": [t["id"] for t in new_tasks]},
        )
    except Exception as exc:
        logger.error(f"[move_variacao] audit_log falhou (ignorado): {exc}", exc_info=True)

    # TRIGGER: Auto-create SKU when variação is approved
    sku_created = None
    if new_status == "aprovada":
        # Encontrar a variação atualizada
        updated_variacao = next((v for v in updated.get("variacoes", []) if v["id"] == variacao_id), None)
        if updated_variacao:
            sku_created = await _create_sku_from_variacao(updated, updated_variacao, user)
        await _advance_project_stage_if_needed(
            updated["projeto_id"],
            "em_negociacao",
            user,
            movement_source="variacao_approved",
        )
    elif new_status == "em_elaboracao":
        await _advance_project_stage_if_needed(
            updated["projeto_id"],
            "amostra_em_desenvolvimento",
            user,
            movement_source="variacao_in_development",
            extra_set={"data_inicio_desenvolvimento": now},
        )
    elif new_status == "enviada":
        await _advance_project_stage_if_needed(
            updated["projeto_id"],
            "amostra_enviada",
            user,
            movement_source="variacao_sent",
            extra_set={"data_ultima_amostra_enviada": now},
        )

    await _sync_pd_cards_from_crm_stage(
        tenant_id=user["tenant_id"],
        sample_id=sample_id,
        variacao_id=variacao_id,
        user=user,
        now=now,
        crm_stage=new_status,
        feedback_cliente=set_ops.get("variacoes.$.feedback_cliente", ""),
        direcoes_retrabalho=set_ops.get("variacoes.$.direcoes_retrabalho", ""),
        resultado_cliente=set_ops.get("variacoes.$.resultado", ""),
    )
    
    return {
        "sample": updated,
        "variacao_id": variacao_id,
        "from_status": STAGE_LABELS.get(old_status, old_status),
        "to_status": STAGE_LABELS.get(new_status, new_status),
        "sku_created": sku_created,
        "tasks_generated": new_tasks,
    }


# ======================================================================
#  VARIAÇÃO — RESULTADO DO CLIENTE (único ponto de escrita comercial pós-envio)
# ======================================================================

class ResultadoClienteRequest(BaseModel):
    resultado: str  # "aprovada" | "reprovada" | "retrabalho"
    feedback_cliente: Optional[str] = None
    direcoes_retrabalho: Optional[str] = None


@crm_router.post("/samples/{sample_id}/variacoes/{variacao_id}/resultado-cliente")
async def resultado_cliente(
    sample_id: str, variacao_id: str, data: ResultadoClienteRequest, request: Request
):
    """Único ponto onde o Comercial pode registrar algo sobre a variação:
    o resultado que o cliente deu (aprovada/reprovada/retrabalho).
    Só permitido quando o status está em 'enviada' (amostra já no cliente).
    """
    user = await _get_current_user(request)

    if data.resultado not in ("aprovada", "reprovada", "retrabalho"):
        raise HTTPException(
            status_code=422,
            detail="resultado deve ser: aprovada, reprovada ou retrabalho",
        )
    if data.resultado == "retrabalho" and not (data.feedback_cliente or "").strip():
        raise HTTPException(
            status_code=422,
            detail="feedback_cliente é obrigatório quando resultado='retrabalho'",
        )

    tenant_id = user["tenant_id"]
    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, tenant_id
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")

    variacao = next((v for v in sample.get("variacoes", []) if v["id"] == variacao_id), None)
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")

    status_atual = variacao.get("status")
    if status_atual != "enviada":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "status_invalido",
                "message": (
                    f"Resultado só pode ser registrado quando status='enviada'. "
                    f"Status atual: '{status_atual}'"
                ),
                "status_atual": status_atual,
            },
        )

    now = _now_iso()
    novo_status_crm = data.resultado  # aprovada | reprovada | retrabalho
    aprovacao_interna = bool(
        variacao.get("aprovacao_interna")
        or variacao.get("enviado_comercial_em")
        or sample.get("aprovacao_interna")
        or sample.get("data_envio")
    )
    if not aprovacao_interna:
        raise HTTPException(
            status_code=409,
            detail="Aprovação interna pendente antes do registro do cliente.",
        )
    pd_label = {
        "aprovada":    "Aprovado pelo Cliente",
        "reprovada":   "Reprovado pelo Cliente",
        "retrabalho":  "Retrabalho Solicitado",
    }[data.resultado]

    set_ops = {
        "variacoes.$.status": novo_status_crm,
        "variacoes.$.status_pd_label": pd_label,
        "variacoes.$.feedback_cliente": data.feedback_cliente or "",
        "variacoes.$.resultado_cliente_registrado_por": user["id"],
        "variacoes.$.resultado_cliente_registrado_em": now,
        "variacoes.$.aprovacao_interna": True,
        "variacoes.$.updated_at": now,
    }
    if data.direcoes_retrabalho:
        set_ops["variacoes.$.direcoes_retrabalho"] = data.direcoes_retrabalho
    if data.resultado == "aprovada":
        set_ops["variacoes.$.resultado"] = "aprovada"
        set_ops["variacoes.$.aprovacao_externa"] = True
        set_ops["variacoes.$.aprovado_cliente_em"] = now
    if data.resultado == "reprovada":
        set_ops["variacoes.$.resultado"] = "reprovada"
        set_ops["variacoes.$.aprovacao_externa"] = False
        set_ops["variacoes.$.reprovacao_motivo"] = data.feedback_cliente or ""
        set_ops["variacoes.$.arquivada"] = True
    if data.resultado == "retrabalho":
        set_ops["variacoes.$.aprovacao_externa"] = False
        set_ops["variacoes.$.reprovacao_motivo"] = data.feedback_cliente or ""

    var_resultado = {
        "status": novo_status_crm,
        "status_pd_label": pd_label,
        "feedback_cliente": data.feedback_cliente or "",
        "resultado_cliente_registrado_por": user["id"],
        "resultado_cliente_registrado_em": now,
        "aprovacao_interna": True,
        "updated_at": now,
    }
    if data.direcoes_retrabalho:
        var_resultado["direcoes_retrabalho"] = data.direcoes_retrabalho
    if data.resultado == "aprovada":
        var_resultado["resultado"] = "aprovada"
        var_resultado["aprovacao_externa"] = True
        var_resultado["aprovado_cliente_em"] = now
    if data.resultado == "reprovada":
        var_resultado["resultado"] = "reprovada"
        var_resultado["aprovacao_externa"] = False
        var_resultado["reprovacao_motivo"] = data.feedback_cliente or ""
        var_resultado["arquivada"] = True
    if data.resultado == "retrabalho":
        var_resultado["aprovacao_externa"] = False
        var_resultado["reprovacao_motivo"] = data.feedback_cliente or ""

    await _update_variacao_in_sample(sample_id, tenant_id, variacao_id, var_resultado)
    hist_rc = {
        "de": "enviada", "para": novo_status_crm, "data": now,
        "usuario": user["name"], "usuario_id": user["id"], "origem": "resultado_cliente",
    }
    await _push_variacao_history(sample_id, tenant_id, variacao_id, hist_rc)

    await _sync_pd_cards_from_crm_stage(
        tenant_id=tenant_id,
        sample_id=sample_id,
        variacao_id=variacao_id,
        user=user,
        now=now,
        crm_stage="reprovada" if data.resultado in ("reprovada", "retrabalho") else "enviada",
        feedback_cliente=data.feedback_cliente or "",
        direcoes_retrabalho=data.direcoes_retrabalho or "",
        resultado_cliente=data.resultado,
    )

    # Notificar pd_card vinculado
    pd_card = _row(await pg_db.fetch_one(
        "SELECT id, status_pd, extra FROM pd_cards WHERE amostra_variacao_id=$1 AND tenant_id=$2",
        variacao_id, tenant_id
    ))
    pd_card_notificado = False
    if pd_card:
        novo_status_pd = {
            "aprovada":   "aguardando_aprovacao",
            "reprovada":  "retrabalho_interno",
            "retrabalho": "retrabalho_interno",
        }[data.resultado]
        hist_card = {
            "de": pd_card.get("status_pd", ""), "para": novo_status_pd,
            "data": now, "usuario": user["name"], "usuario_id": user["id"],
            "observacao": f"Resultado do cliente: {pd_label}",
        }
        extra_merge = {"feedback_cliente": data.feedback_cliente or "",
                       "direcoes_retrabalho": data.direcoes_retrabalho or "",
                       "resultado_cliente": data.resultado}
        await pg_db.execute(
            """UPDATE pd_cards SET status_pd=$1, updated_at=$2,
               extra = jsonb_set(
                   extra || $3::jsonb,
                   '{historico_movimentacoes}',
                   COALESCE(extra->'historico_movimentacoes','[]'::jsonb) || jsonb_build_array($4::jsonb)
               )
               WHERE id=$5 AND tenant_id=$6""",
            novo_status_pd, now, json.dumps(extra_merge), json.dumps(hist_card),
            pd_card["id"], tenant_id
        )
        pd_card_notificado = True
        logger.info(f"Resultado cliente: variação {variacao_id} → {novo_status_crm} / pd_card {pd_card['id']} → {novo_status_pd}")

    await audit_log(
        tenant_id=tenant_id,
        user_id=user["id"],
        user_name=user.get("name", ""),
        action="resultado_cliente_registrado",
        entity_type="variacao",
        entity_id=variacao_id,
        before={"status": "enviada"},
        after={"status": novo_status_crm, "resultado": data.resultado},
        metadata={"sample_id": sample_id, "pd_card_id": pd_card["id"] if pd_card else None},
    )

    return {
        "success": True,
        "variacao_id": variacao_id,
        "resultado": data.resultado,
        "status_atualizado": novo_status_crm,
        "pd_card_notificado": pd_card_notificado,
    }


# ======================================================================
#  SAMPLE / VARIAÇÃO — DELETE & ADD VARIAÇÕES (pós-envio)
# ======================================================================

class AddVariacoesRequest(BaseModel):
    variacoes: List[VariacaoItem]


@crm_router.delete("/samples/{sample_id}")
async def delete_sample(sample_id: str, request: Request):
    """Deleta uma amostra completa (todas variações + pd_cards).
    Bloqueia se alguma variação já gerou SKU."""
    user = await _get_current_user(request)
    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")

    # Bloquear se alguma variação tiver SKU
    for v in sample.get("variacoes", []) or []:
        if v.get("sku_id"):
            raise HTTPException(
                status_code=400,
                detail=f"Não é possível excluir: variação {v.get('codigo')} já gerou SKU."
            )

    # Coletar pd_cards vinculados
    pd_card_ids = [v["pd_card_id"] for v in (sample.get("variacoes") or []) if v.get("pd_card_id")]

    if pd_card_ids:
        await pg_db.execute(
            "DELETE FROM pd_cards WHERE id = ANY($1::text[]) AND tenant_id=$2",
            pd_card_ids, user["tenant_id"]
        )
    await pg_db.execute(
        "DELETE FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    )

    logger.info(f"Deleted sample {sample_id} with {len(pd_card_ids)} pd_cards")
    return {
        "deleted_sample": sample_id,
        "deleted_pd_cards": len(pd_card_ids),
    }


@crm_router.delete("/samples/{sample_id}/variacoes/{variacao_id}")
async def delete_variacao(sample_id: str, variacao_id: str, request: Request):
    """Deleta uma variação específica (e seu pd_card).
    Bloqueia se a variação já gerou SKU ou se é a última variação."""
    user = await _get_current_user(request)
    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")

    variacoes = sample.get("variacoes") or []
    variacao = next((v for v in variacoes if v["id"] == variacao_id), None)
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")

    if variacao.get("sku_id"):
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível excluir: variação {variacao.get('codigo')} já gerou SKU."
        )

    if len(variacoes) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Não é possível excluir a última variação. Exclua a amostra inteira."
        )

    # Remover pd_card vinculado
    if variacao.get("pd_card_id"):
        await pg_db.execute(
            "DELETE FROM pd_cards WHERE id=$1 AND tenant_id=$2",
            variacao["pd_card_id"], user["tenant_id"]
        )

    # Remover variação do array e recalcular tem_variacoes
    new_variacoes = [v for v in variacoes if v["id"] != variacao_id]
    tem_variacoes = len(new_variacoes) > 1
    await pg_db.execute(
        "UPDATE crm_samples SET variacoes=$1, tem_variacoes=$2, updated_at=NOW() WHERE id=$3 AND tenant_id=$4",
        new_variacoes, tem_variacoes, sample_id, user["tenant_id"]
    )

    logger.info(f"Deleted variação {variacao_id} from sample {sample_id}")
    return {"deleted_variacao": variacao_id, "sample_id": sample_id}


@crm_router.post("/samples/{sample_id}/variacoes")
async def add_variacoes_to_sample(sample_id: str, data: AddVariacoesRequest, request: Request):
    """Adiciona novas variações a uma amostra existente.
    Gera automaticamente próximas letras (se tem A,B,C → adiciona D, E...)."""
    user = await _get_current_user(request)
    sample = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    if not sample:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")

    if not data.variacoes:
        raise HTTPException(status_code=400, detail="Nenhuma variação fornecida")

    now = _now_iso()
    existing = sample.get("variacoes") or []
    # Próximo índice baseado no número de variações existentes (mesmo deletadas no passado o usuario cria sequencia)
    start_index = len(existing)
    numero_amostra = sample.get("numero_amostra", "?")

    new_variacoes = []
    for offset, var in enumerate(data.variacoes):
        idx = start_index + offset
        letra = int_to_letters(idx)
        codigo = f"{numero_amostra}-{letra}"
        variacao_id = _new_id()
        variacao = {
            "id": variacao_id,
            "codigo": codigo,
            "letra": letra,
            "descricao_aplicacao": var.descricao_aplicacao,
            "percentual_fragrancia": var.percentual_fragrancia,
            "referencia_fragrancia": var.referencia_fragrancia,
            "custo_fragrancia": var.custo_fragrancia,
            "observacoes_especificas": var.observacoes_especificas,
            "status": "solicitada",
            "historico_status": [{
                "de": "",
                "para": "solicitada",
                "data": now,
                "usuario": user["name"],
                "usuario_id": user["id"]
            }],
            "motivo_retrabalho": "",
            "historico_retrabalhos": [],
            "feedback_cliente": "",
            "gera_sku": False,
            "sku_id": None,
            "pd_card_id": None,
        }
        new_variacoes.append(variacao)

    # Inserir no array
    all_variacoes = existing + new_variacoes
    await pg_db.execute(
        "UPDATE crm_samples SET variacoes=$1, tem_variacoes=TRUE, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        all_variacoes, sample_id, user["tenant_id"]
    )

    # Criar pd_cards para cada nova variação
    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    for new_var in new_variacoes:
        try:
            await _create_pd_card_for_variacao(updated, new_var, user)
        except Exception as _pd_exc:
            logger.error(f"[add_variacoes_to_sample] _create_pd_card_for_variacao falhou (ignorado): {_pd_exc}", exc_info=True)

    final = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
        sample_id, user["tenant_id"]
    ))
    logger.info(f"Added {len(new_variacoes)} variações to sample {sample_id}")
    return {
        "sample": final,
        "added": len(new_variacoes),
        "new_variacoes": new_variacoes,
    }


@crm_router.post("/samples/{sample_id}/variacoes/{variacao_id}/send-to-pd")
async def send_variacao_to_pd(sample_id: str, variacao_id: str, request: Request):
    """Cria retroativamente um card P&D para uma variação que não tem pd_card_id."""
    user = await _get_current_user(request)
    sample = await assert_sample_exists(user["tenant_id"], sample_id)
    variacoes = sample.get("variacoes") or []
    variacao = next((v for v in variacoes if v["id"] == variacao_id), None)
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")
    if variacao.get("pd_card_id"):
        return {"message": "Variação já possui card P&D", "pd_card_id": variacao["pd_card_id"]}
    await _create_pd_card_for_variacao(sample, variacao, user)
    updated = await assert_sample_exists(user["tenant_id"], sample_id)
    updated_var = next((v for v in (updated.get("variacoes") or []) if v["id"] == variacao_id), None)
    return {"message": "Card P&D criado com sucesso!", "pd_card_id": updated_var.get("pd_card_id") if updated_var else None}


async def _create_sku_from_variacao(sample: dict, variacao: dict, user: dict) -> dict:
    """Auto-create SKU entity when a variação is approved"""
    tenant_id = sample["tenant_id"]

    # Resolve CAT2 and CLI3 for new code format [CAT2]-[CLI3]-[SEQ4]
    categoria = sample.get("categoria", "")
    cat2 = cat2_from_categoria(categoria)
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        sample["cliente_id"], tenant_id
    ))
    raw_cli3 = (client.get("cli3") or client.get("nome_empresa", "") if client else "")
    cli3 = normalise_cli3(raw_cli3)
    seq = await next_sku_per_pair(tenant_id, cat2, cli3)
    codigo = f"{cat2}-{cli3}-{str(seq).zfill(4)}"

    now = _now_iso()
    sku_id = _new_id()

    sku = {
        "id": sku_id,
        "tenant_id": tenant_id,
        "codigo_interno": codigo,
        "cat2": cat2,
        "cli3": cli3,
        "nome_produto": f"{sample['nome_produto']} - {variacao['codigo']}",
        "categoria": categoria,
        "formula_vinculada": "",
        "cliente_id": sample["cliente_id"],
        "cliente_nome": sample.get("cliente_nome", ""),
        "projeto_id": sample["projeto_id"],
        "projeto_nome": sample.get("projeto_nome", ""),
        "amostra_id": sample["id"],
        "amostra_variacao_id": variacao["id"],
        "descricao_aplicacao": variacao.get("descricao_aplicacao", ""),
        "preco_unitario": variacao.get("custo_fragrancia", 0.0),
        "moq": 0,
        "anvisa": {"numero": "", "validade": None},
        "status": "ativo",
        "descontinuado_motivo": None,
        "descontinuado_em": None,
        "descontinuado_por": None,
        "historico_pedidos": [],
        "data_ultimo_pedido": None,
        "frequencia_media_recompra_dias": 0,
        "medias_producao": {
            "media_geral_unh": None,
            "media_12m_unh": None,
            "media_3m_unh": None,
            "media_1m_unh": None,
            "meta_unh": None,
            "ajuste_percentual": 0,
            "meta_set_by": None,
            "meta_set_at": None,
            "historico_producao": [],
        },
        "created_at": now,
        "updated_at": now,
    }

    await pg_db.execute(
        """INSERT INTO skus (
            id, tenant_id, codigo_interno, cat2, cat3, cli3, cli4, nome_produto, categoria,
            formula_vinculada, cliente_id, cliente_nome, projeto_id, projeto_nome,
            amostra_id, amostra_variacao_id, descricao_aplicacao, preco_unitario,
            moq, anvisa, status, historico_pedidos, data_ultimo_pedido,
            frequencia_media_recompra_dias, medias_producao, created_at, updated_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
            $19,$20,$21,$22,$23,$24,$25,NOW(),NOW()
        )""",
        sku_id, tenant_id, codigo, cat2, sku.get("cat3", ""), cli3, sku.get("cli4", ""),
        sku["nome_produto"], categoria, "", sample["cliente_id"],
        sample.get("cliente_nome", ""), sample["projeto_id"], sample.get("projeto_nome", ""),
        sample["id"], variacao["id"], variacao.get("descricao_aplicacao", ""),
        float(variacao.get("custo_fragrancia") or 0.0), 0,
        {"numero": "", "validade": None}, "ativo", [], None, 0,
        sku.get("medias_producao", {})
    )

    # Atualizar variação com SKU ID
    await _update_variacao_in_sample(sample["id"], tenant_id, variacao["id"], {"sku_id": sku_id, "gera_sku": True})

    logger.info(f"Auto-created SKU {codigo} from variação {variacao['codigo']}")
    return sku


# ======================================================================
#  SKU (auto-generated from approved samples)
# ======================================================================

async def _check_sku_dependency_chain(sample: dict, tenant_id: str) -> None:
    """
    R25: Validate full dependency chain before generating SKU.
    Raises HTTPException 409 with the first missing prerequisite.
    Chain: Categoria exists → Cliente com CLI4 → CGI assinado → Projeto →
           Amostra aprovada (define categoria) → Pedido de Industrialização aprovado
    """
    cliente_id = sample.get("cliente_id")
    projeto_id = sample.get("projeto_id")

    # 1. Cliente with CLI4
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2", cliente_id, tenant_id
    ))
    if not client:
        raise HTTPException(status_code=409, detail="[R25] Cliente não encontrado — pré-requisito para geração de SKU")
    if not client.get("cli4"):
        raise HTTPException(status_code=409, detail="[R25] Cliente sem CLI4 definido — cadastre o código CLI4 antes de gerar o SKU")

    # 2. Categoria exists and is active (must be in db.categorias)
    categoria = sample.get("categoria") or ""
    if not categoria:
        project = _row(await pg_db.fetch_one(
            "SELECT categoria FROM crm_projects WHERE id=$1 AND tenant_id=$2", projeto_id, tenant_id
        ))
        categoria = (project or {}).get("categoria", "")
    cat3 = cat3_from_categoria(categoria)
    if cat3 == "GEN":
        raise HTTPException(status_code=409, detail=f"[R25] Categoria '{categoria}' não possui CAT3 mapeado — cadastre a categoria antes de gerar o SKU")

    cat_doc = await db.categorias.find_one({"tenant_id": tenant_id, "cat3": cat3}, {"_id": 0})
    if not cat_doc or cat_doc.get("status") != "ativa":
        status_msg = f"status: {cat_doc.get('status', 'não encontrada')}" if cat_doc else "não cadastrada"
        raise HTTPException(
            status_code=409,
            detail=f"[R25] Categoria CAT3={cat3} ({status_msg}) — só categorias ativas podem gerar SKU"
        )

    # 3. CGI assinado (contratos vinculados ao cliente/projeto)
    cgi = await db.contratos.find_one(
        {"tenant_id": tenant_id, "cliente_id": cliente_id, "status": {"$in": ["assinado", "vigente"]}},
        {"_id": 0, "numero_contrato": 1},
    )
    if not cgi:
        raise HTTPException(
            status_code=409,
            detail="[R25] CGI (Contrato Geral de Industrialização) não assinado — assine o contrato antes de gerar o SKU"
        )

    # 4. Amostra em stage 'aprovada' (already guaranteed by caller, but validate explicitly)
    if sample.get("stage") != "aprovada":
        raise HTTPException(
            status_code=409,
            detail=f"[R25] Amostra deve estar em stage 'aprovada' — atual: {sample.get('stage')}"
        )

    # 5. Pedido de Industrialização aprovado (pedido_aprovado stage on project)
    project = _row(await pg_db.fetch_one(
        "SELECT stage FROM crm_projects WHERE id=$1 AND tenant_id=$2", projeto_id, tenant_id
    ))
    if not project or project.get("stage") not in ("pedido_aprovado", "cliente_fechado"):
        proj_stage = (project or {}).get("stage", "não encontrado")
        raise HTTPException(
            status_code=409,
            detail=f"[R25] Projeto deve estar em 'pedido_aprovado' — atual: {proj_stage}"
        )


async def _create_sku_from_sample(sample: dict, user: dict) -> dict:
    """
    Auto-create SKU entity when a sample is approved.
    Uses new format [CAT3]-[CLI4]-[SEQ4] (R11). Validates R25 chain first.
    """
    tenant_id = sample["tenant_id"]

    # R25: dependency chain
    try:
        await _check_sku_dependency_chain(sample, tenant_id)
    except HTTPException as exc:
        logger.warning(f"SKU generation blocked for sample {sample['id']}: {exc.detail}")
        return {"blocked": True, "reason": exc.detail}

    # Resolve category
    project = _row(await pg_db.fetch_one(
        "SELECT categoria FROM crm_projects WHERE id=$1 AND tenant_id=$2",
        sample["projeto_id"], tenant_id
    ))
    categoria = sample.get("categoria") or (project.get("categoria") if project else "") or ""

    # New format: [CAT3]-[CLI4]-[SEQ4]
    cat3 = cat3_from_categoria(categoria)
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        sample["cliente_id"], tenant_id
    ))
    cli4 = normalise_cli4(client.get("cli4") or client.get("nome_empresa", ""))
    seq = await next_sku_per_pair_v2(tenant_id, cat3, cli4)
    codigo = build_sku_code_v2(cat3, cli4, seq)

    # Legacy fields preserved for backward compat queries
    cat2 = cat2_from_categoria(categoria)
    raw_cli3 = client.get("cli3") or client.get("nome_empresa", "")
    cli3 = normalise_cli3(raw_cli3)

    now = _now_iso()
    sku_id = _new_id()

    sku = {
        "id": sku_id,
        "tenant_id": tenant_id,
        "codigo_interno": codigo,
        "cat3": cat3,
        "cli4": cli4,
        "cat2": cat2,
        "cli3": cli3,
        "nome_produto": sample.get("nome_amostra", "") or sample.get("nome_produto", ""),
        "categoria": categoria,
        "formula_vinculada": "",
        "cliente_id": sample["cliente_id"],
        "cliente_nome": sample.get("cliente_nome", ""),
        "projeto_id": sample["projeto_id"],
        "projeto_nome": sample.get("projeto_nome", ""),
        "amostra_id": sample["id"],
        "produto_pai_id": None,
        "preco_unitario": 0.0,
        "moq": 0,
        "anvisa": {"numero": "", "validade": None},
        "status": "ativo",
        "descontinuado_motivo": None,
        "descontinuado_em": None,
        "descontinuado_por": None,
        "historico_pedidos": [],
        "data_ultimo_pedido": None,
        "frequencia_media_recompra_dias": 0,
        "medias_producao": {
            "media_geral_unh": None,
            "media_12m_unh": None,
            "media_3m_unh": None,
            "media_1m_unh": None,
            "meta_unh": None,
            "ajuste_percentual": 0,
            "meta_set_by": None,
            "meta_set_at": None,
            "historico_producao": [],
        },
        "created_at": now,
        "updated_at": now,
    }

    await pg_db.execute(
        """INSERT INTO skus (
            id, tenant_id, codigo_interno, cat3, cli4, cat2, cli3, nome_produto, categoria,
            formula_vinculada, cliente_id, cliente_nome, projeto_id, projeto_nome,
            amostra_id, produto_pai_id, preco_unitario, moq, anvisa, status,
            historico_pedidos, data_ultimo_pedido, frequencia_media_recompra_dias,
            medias_producao, created_at, updated_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
            $19,$20,$21,$22,$23,$24,NOW(),NOW()
        )""",
        sku_id, tenant_id, codigo, cat3, cli4, cat2, cli3,
        sku["nome_produto"], categoria, "", sample["cliente_id"],
        sample.get("cliente_nome", ""), sample["projeto_id"], sample.get("projeto_nome", ""),
        sample["id"], None, 0.0, 0,
        {"numero": "", "validade": None}, "ativo",
        [], None, 0, sku.get("medias_producao", {})
    )

    # R23: freeze cli4 after first SKU
    if client and not client.get("cli4_congelado"):
        await pg_db.execute(
            "UPDATE crm_clients SET cli4_congelado=TRUE, updated_at=NOW() WHERE id=$1 AND tenant_id=$2",
            sample["cliente_id"], tenant_id
        )

    logger.info(f"Auto-created SKU {codigo} from sample {sample['id']}")
    return sku


@crm_router.get("/skus")
async def list_skus(
    request: Request,
    cliente_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    user = await _get_current_user(request)
    sql = "SELECT * FROM skus WHERE tenant_id=$1"
    params: list = [user["tenant_id"]]
    if cliente_id:
        params.append(cliente_id); sql += f" AND cliente_id=${len(params)}"
    if status:
        params.append(status); sql += f" AND status=${len(params)}"
    if search:
        params.append(f"%{search}%"); n = len(params)
        sql += f" AND (nome_produto ILIKE ${n} OR codigo_interno ILIKE ${n})"
    sql += " ORDER BY created_at DESC LIMIT 5000"
    skus = _rows(await pg_db.fetch_all(sql, *params))
    return skus


@crm_router.get("/skus/preview-code")
async def preview_sku_code(cliente_id: str, categoria: str, request: Request):
    """Return the code that would be generated for a new SKU (without consuming the sequence)."""
    user = await _get_current_user(request)
    cat2 = cat2_from_categoria(categoria)
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2", cliente_id, user["tenant_id"]
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    raw_cli3 = client.get("cli3") or client.get("nome_empresa", "")
    cli3 = normalise_cli3(raw_cli3)
    # Peek at next seq without incrementing (counters keyed as "name:tenant_id")
    counter_key = f"sku_{cat2}_{cli3}:{user['tenant_id']}"
    seq_doc = await db.counters.find_one({"_id": counter_key})
    next_seq = (seq_doc.get("seq", 0) if seq_doc else 0) + 1
    return {
        "codigo": f"{cat2}-{cli3}-{str(next_seq).zfill(4)}",
        "cat2": cat2,
        "cli3": cli3,
        "seq": next_seq,
        "cli3_source": "campo_cli3" if client.get("cli3") else "nome_empresa",
    }


@crm_router.get("/skus/{sku_id}")
async def get_sku(sku_id: str, request: Request):
    user = await _get_current_user(request)
    sku = _row(await pg_db.fetch_one(
        "SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")
    return sku


@crm_router.put("/skus/{sku_id}")
async def update_sku(sku_id: str, data: SKUUpdate, request: Request):
    """Limited update — SKU code is immutable (RN-SK-04), other fields are editable."""
    user = await _get_current_user(request)
    scalar_fields: dict = {}
    anvisa_patch: dict = {}

    if data.nome_produto is not None:
        scalar_fields["nome_produto"] = data.nome_produto
    if data.preco_unitario is not None:
        scalar_fields["preco_unitario"] = data.preco_unitario
    if data.preco_unitario_currency is not None:
        scalar_fields["preco_unitario_currency"] = data.preco_unitario_currency
    if data.moq is not None:
        scalar_fields["moq"] = data.moq
    if data.status is not None:
        if data.status not in ("ativo", "suspenso", "descontinuado"):
            raise HTTPException(status_code=400, detail="Status inválido")
        scalar_fields["status"] = data.status
    if data.anvisa_numero is not None:
        anvisa_patch["numero"] = data.anvisa_numero
    if data.anvisa_validade is not None:
        anvisa_patch["validade"] = data.anvisa_validade

    if not scalar_fields and not anvisa_patch:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    fields = list(scalar_fields.keys())
    params: list = [scalar_fields[k] for k in fields]
    set_parts = [f"{k}=${i+1}" for i, k in enumerate(fields)]
    set_parts.append("updated_at=NOW()")
    if anvisa_patch:
        params.append(json.dumps(anvisa_patch)); set_parts.append(f"anvisa = anvisa || ${len(params)}::jsonb")
    params.extend([sku_id, user["tenant_id"]])
    matched = await pg_db.fetch_val(
        f"UPDATE skus SET {', '.join(set_parts)} WHERE id=${len(params)-1} AND tenant_id=${len(params)} RETURNING id",
        *params
    )
    if not matched:
        raise HTTPException(status_code=404, detail="SKU não encontrado")
    return _row(await pg_db.fetch_one("SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]))


@crm_router.post("/skus/{sku_id}/meta")
async def update_sku_meta(sku_id: str, data: SKUMetaUpdate, request: Request):
    """Update manual Meta un/h and ajuste percentual (RN-SK-05)."""
    user = await _get_current_user(request)
    sku = _row(await pg_db.fetch_one(
        "SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")

    now = _now_iso()
    patch: dict = {}
    if data.meta_unh is not None:
        if data.meta_unh < 0:
            raise HTTPException(status_code=422, detail="meta_unh não pode ser negativa")
        patch["meta_unh"] = data.meta_unh
        patch["meta_set_by"] = user["name"]
        patch["meta_set_at"] = now
    if data.ajuste_percentual is not None:
        if not (-100 <= data.ajuste_percentual <= 100):
            raise HTTPException(status_code=422, detail="ajuste_percentual deve estar entre -100 e +100")
        patch["ajuste_percentual"] = data.ajuste_percentual
    if not patch:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    await pg_db.execute(
        "UPDATE skus SET medias_producao = medias_producao || $1::jsonb, updated_at=$2 WHERE id=$3 AND tenant_id=$4",
        json.dumps(patch), now, sku_id, user["tenant_id"]
    )
    return _row(await pg_db.fetch_one("SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]))


@crm_router.post("/skus/{sku_id}/descontinuar")
async def descontinuar_sku(sku_id: str, data: SKUDescontinuar, request: Request):
    """Mark SKU as discontinued with mandatory reason (RN-SK-03)."""
    user = await _get_current_user(request)
    sku = _row(await pg_db.fetch_one(
        "SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")
    if sku.get("status") == "descontinuado":
        raise HTTPException(status_code=400, detail="SKU já está descontinuado")
    if not data.motivo.strip():
        raise HTTPException(status_code=422, detail="Motivo obrigatório para descontinuar (RN-SK-03)")

    now = _now_iso()
    await pg_db.execute(
        """UPDATE skus SET status='descontinuado', descontinuado_motivo=$1,
           descontinuado_em=$2, descontinuado_por=$3, updated_at=$4
           WHERE id=$5 AND tenant_id=$6""",
        data.motivo.strip(), now, user["name"], now, sku_id, user["tenant_id"]
    )
    return _row(await pg_db.fetch_one("SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]))


@crm_router.get("/skus/{sku_id}/saldo")
async def get_sku_saldo(sku_id: str, request: Request):
    """Return consolidated open balance (saldo aberto) view per order for a SKU."""
    user = await _get_current_user(request)
    sku = _row(await pg_db.fetch_one(
        "SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")

    # Find all orders that contain this SKU's code
    codigo = sku.get("codigo_interno", "")
    orders_cursor = db.orders.find(
        {"tenant_id": user["tenant_id"], "items.codigo_kuryos": codigo},
        {"_id": 0}
    )
    orders = await orders_cursor.to_list(500)

    result = []
    for order in orders:
        items_for_sku = [it for it in (order.get("items") or []) if it.get("codigo_kuryos") == codigo]
        for item in items_for_sku:
            qtd_pedido = item.get("qtd", 0)
            # Find OPs for this order
            ops_cursor = db.ops.find(
                {"tenant_id": user["tenant_id"], "pedido_id": order["id"]},
                {"_id": 0}
            )
            ops = await ops_cursor.to_list(100)
            ops_info = []
            qtd_realizada_total = 0
            qtd_perda_total = 0
            for op in ops:
                qtd_apontada = sum(a.get("qtd_produzida", 0) for a in (op.get("apontamentos") or []))
                qtd_perda = sum(p.get("quantidade", 0) for p in (op.get("perdas") or []))
                qtd_realizada_total += qtd_apontada
                qtd_perda_total += qtd_perda
                # PCP slot for this OP
                pcp_slot = await db.pcp_programacao.find_one({"op_id": op["id"]}, {"_id": 0})
                ops_info.append({
                    "op_id": op["id"],
                    "numero_op": op.get("numero_op"),
                    "status": op.get("status"),
                    "qtd_planejada": op.get("items", [{}])[0].get("qtd", 0) if op.get("items") else 0,
                    "qtd_realizada": qtd_apontada,
                    "qtd_perda": qtd_perda,
                    "pcp_data_inicio": pcp_slot.get("data_inicio") if pcp_slot else None,
                    "pcp_linha": pcp_slot.get("linha_nome") if pcp_slot else None,
                    "pcp_status": pcp_slot.get("status") if pcp_slot else None,
                })
            saldo_aberto = max(qtd_pedido - qtd_realizada_total, 0)
            checklist_ok = all(
                (ci.get("status") == "recebido" or not ci.get("ativo"))
                for ci in (order.get("checklist_insumos") or [])
            )
            result.append({
                "pedido_id": order["id"],
                "numero_pedido": order.get("numero_pedido"),
                "cliente_nome": order.get("cliente", {}).get("nome"),
                "order_status": order.get("status"),
                "item_nome": item.get("item"),
                "qtd_pedido": qtd_pedido,
                "qtd_realizada": qtd_realizada_total,
                "qtd_perda": qtd_perda_total,
                "saldo_aberto": saldo_aberto,
                "checklist_insumos_ok": checklist_ok,
                "ops": ops_info,
            })
    return result


@crm_router.post("/skus/{sku_id}/orders")
async def add_order_to_sku(sku_id: str, data: OrderAdd, request: Request):
    """Add an order to SKU history and recalculate metrics"""
    user = await _get_current_user(request)
    sku = _row(await pg_db.fetch_one(
        "SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")

    now = _now_iso()
    order = {
        "id": _new_id(),
        "data_pedido": data.data_pedido,
        "quantidade": data.quantidade,
        "valor_total": data.valor_total,
        "observacao": data.observacao,
        "registrado_por": user["name"],
        "registrado_em": now,
    }

    # Calculate reorder frequency
    historico = sku.get("historico_pedidos", [])
    historico.append(order)

    freq = 0
    if len(historico) >= 2:
        dates = sorted([h["data_pedido"] for h in historico])
        try:
            date_objs = [datetime.fromisoformat(d.replace("Z", "+00:00")) if isinstance(d, str) else d for d in dates]
            if len(date_objs) >= 2:
                diffs = [(date_objs[i+1] - date_objs[i]).days for i in range(len(date_objs)-1)]
                freq = sum(diffs) / len(diffs) if diffs else 0
        except Exception:
            freq = 0

    await pg_db.execute(
        """UPDATE skus SET
            historico_pedidos = historico_pedidos || jsonb_build_array($1::jsonb),
            data_ultimo_pedido=$2, frequencia_media_recompra_dias=$3, updated_at=$4
           WHERE id=$5 AND tenant_id=$6""",
        json.dumps(order), data.data_pedido, round(freq), now, sku_id, user["tenant_id"]
    )
    return _row(await pg_db.fetch_one("SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]))


# ======================================================================
#  PIPELINE P&D (Cards de desenvolvimento)
# ======================================================================

PD_STATUSES = ["solicitado", "em_desenvolvimento", "em_testes", "aguardando_aprovacao", "retrabalho_interno"]

PD_STATUS_LABELS = {
    "solicitado": "Aberto",
    "em_desenvolvimento": "Em Desenvolvimento",
    "em_testes": "Em Testes",
    "aguardando_aprovacao": "Aguardando Aprovação",
    "retrabalho_interno": "Retrabalho Interno"
}

# Mapeamento: Status P&D → Status CRM3 Variação (simplificado, retrocompatível)
PD_TO_CRM_STATUS_MAP = {
    "solicitado": "solicitada",
    "em_desenvolvimento": "em_elaboracao",
    "em_testes": None,  # Não muda CRM3, só adiciona ao histórico
    "aguardando_aprovacao": "enviada",
    "retrabalho_interno": "retrabalho"
}

# Mapeamento rico: Status P&D → (status_CRM_simplificado, label_visível_ao_comercial)
PD_CARD_STATUS_TO_CRM_DISPLAY = {
    "solicitado":           ("solicitada",    "Aguardando P&D"),
    "em_desenvolvimento":   ("em_elaboracao", "Em Desenvolvimento"),
    "em_testes":            ("em_elaboracao", "Em Testes"),
    "aguardando_aprovacao": ("enviada",       "Aguardando Aprovação CQ"),
    "retrabalho_interno":   ("retrabalho",    "Em Retrabalho"),
}

@crm_router.get("/pd/cards")
async def list_pd_cards(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """Listar cards do Pipeline P&D"""
    user = await _get_current_user(request)
    require_roles(user, PD_READ | COMERCIAL_FULL)
    sql = "SELECT * FROM pd_cards WHERE tenant_id=$1"
    params: list = [user["tenant_id"]]
    if status:
        params.append(status); sql += f" AND status_pd=${len(params)}"
    if search:
        params.append(f"%{search}%"); n = len(params)
        sql += (f" AND (extra->>'numero_completo' ILIKE ${n}"
                f" OR extra->>'produto' ILIKE ${n}"
                f" OR extra->>'cliente' ILIKE ${n})")
    sql += " ORDER BY created_at DESC LIMIT 5000"
    cards = _rows(await pg_db.fetch_all(sql, *params))
    return cards


@crm_router.get("/pd/cards/{card_id}")
async def get_pd_card(card_id: str, request: Request):
    """Obter detalhes de um card P&D"""
    user = await _get_current_user(request)
    require_roles(user, PD_READ | COMERCIAL_FULL)
    card = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_cards WHERE id=$1 AND tenant_id=$2", card_id, user["tenant_id"]
    ))
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")

    # Lazy: garante que existe um pd_request linkado para abrir a tela completa do PDDetail
    if not card.get("pd_request_id"):
        try:
            merged = {**card, **(card.get("extra") or {})}
            await _ensure_pd_request_for_card(merged, user)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Lazy pd_request creation failed for card {card_id}: {exc}")

    # Buscar amostra e variação relacionadas
    if card.get("amostra_id"):
        sample = _row(await pg_db.fetch_one(
            "SELECT * FROM crm_samples WHERE id=$1 AND tenant_id=$2",
            card["amostra_id"], user["tenant_id"]
        ))
        if sample:
            card["amostra_completa"] = sample
            variacao = next((v for v in sample.get("variacoes", []) if v["id"] == card.get("amostra_variacao_id")), None)
            if variacao:
                card["variacao"] = variacao

    return card


@crm_router.post("/pd/cards/sync-all-to-crm")
async def sync_all_pd_cards_to_crm(request: Request):
    """Admin/lider_pd: re-sincroniza todos os pd_cards com suas variações CRM.
    Usar uma vez para corrigir dados inconsistentes já no banco.
    """
    user = await _get_current_user(request)
    require_roles(user, {"admin", "lider_pd"})

    tenant_id = user["tenant_id"]
    pd_cards = _rows(await pg_db.fetch_all(
        "SELECT * FROM pd_cards WHERE tenant_id=$1 AND amostra_variacao_id IS NOT NULL",
        tenant_id
    ))

    synced = 0
    errors = 0
    now = _now_iso()

    for card in pd_cards:
        try:
            status_pd = card.get("status_pd", "solicitado")
            crm_status, crm_label = PD_CARD_STATUS_TO_CRM_DISPLAY.get(
                status_pd,
                (PD_TO_CRM_STATUS_MAP.get(status_pd), PD_STATUS_LABELS.get(status_pd, status_pd)),
            )
            if not crm_status or not card.get("amostra_id") or not card.get("amostra_variacao_id"):
                continue
            await _update_variacao_in_sample(
                card["amostra_id"], tenant_id, card["amostra_variacao_id"],
                {"status": crm_status, "status_pd_label": crm_label,
                 "status_pd_raw": status_pd, "ultima_atualizacao_pd": now}
            )
            synced += 1
        except Exception as exc:
            logger.error(f"sync-all error card {card.get('id')}: {exc}")
            errors += 1

    logger.info(f"sync-all-to-crm: {synced} synced, {errors} errors (tenant={tenant_id})")
    return {
        "synced": synced,
        "errors": errors,
        "total": len(pd_cards),
        "message": f"Sincronizados {synced} de {len(pd_cards)} cards",
    }


class PDCardMove(BaseModel):
    status: str
    observacao: str = ""

@crm_router.put("/pd/cards/{card_id}/move")
async def move_pd_card(card_id: str, data: PDCardMove, request: Request):
    """Mover card no Pipeline P&D e sincronizar com CRM (ERP v3.0: gera tasks de CQ)."""
    user = await _get_current_user(request)
    require_roles(user, PD_WRITE | QA_APPROVERS)
    
    card = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_cards WHERE id=$1 AND tenant_id=$2", card_id, user["tenant_id"]
    ))
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")

    old_status = card["status_pd"]
    new_status = data.status
    
    if new_status not in PD_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status inválido: {new_status}")

    # ERP v3.0: blocking tasks (e.g., CQ approval before closing)
    await assert_no_blocking_tasks(
        tenant_id=user["tenant_id"],
        entity_type="pd_card",
        entity_id=card_id,
        target_stage=new_status,
    )

    # Bloqueio por insumos nao homologados / suspensos antes de aprovacao
    if new_status in ("aguardando_aprovacao",):
        from pd_routes import assert_pd_card_ready_for_approval
        await assert_pd_card_ready_for_approval(card_id, user["tenant_id"])

    now = _now_iso()
    
    # Atualizar card P&D
    hist_mv = {"de": old_status, "para": new_status, "data": now,
               "usuario": user["name"], "usuario_id": user["id"], "observacao": data.observacao}
    await pg_db.execute(
        """UPDATE pd_cards SET status_pd=$1, updated_at=NOW(),
           extra = jsonb_set(
               extra,
               '{historico_movimentacoes}',
               COALESCE(extra->'historico_movimentacoes','[]'::jsonb) || jsonb_build_array($2::jsonb)
           )
           WHERE id=$3 AND tenant_id=$4""",
        new_status, json.dumps(hist_mv), card_id, user["tenant_id"]
    )

    # ERP v3.0: trigger tasks (CQ approval, lab tests)
    new_tasks = []
    try:
        new_tasks = await trigger_tasks_for_transition(
            entity_type="pd_card",
            entity_id=card_id,
            tenant_id=user["tenant_id"],
            old_stage=old_status,
            new_stage=new_status,
            user=user,
        )
    except Exception as exc:
        logger.error(f"[move_pd_card] trigger_tasks_for_transition falhou (ignorado): {exc}", exc_info=True)

    stability_study = None
    if new_status == "em_testes":
        from pd_routes import _ensure_stability_study_for_pd_card
        stability_study = await _ensure_stability_study_for_pd_card(
            {
                **card,
                "status_pd": new_status,
                "updated_at": now,
            },
            user,
        )

    # SINCRONIZAÇÃO: Atualizar status da variação no CRM (sentido único P&D → CRM)
    if card.get("amostra_id") and card.get("amostra_variacao_id"):
        crm_status, crm_label = PD_CARD_STATUS_TO_CRM_DISPLAY.get(
            new_status,
            (PD_TO_CRM_STATUS_MAP.get(new_status), PD_STATUS_LABELS.get(new_status, new_status))
        )

        if crm_status:
            await _update_variacao_in_sample(
                card["amostra_id"], user["tenant_id"], card["amostra_variacao_id"],
                {"status": crm_status, "status_pd_label": crm_label,
                 "status_pd_raw": new_status, "ultima_atualizacao_pd": now, "updated_at": now}
            )
            await _push_variacao_history(
                card["amostra_id"], user["tenant_id"], card["amostra_variacao_id"],
                {"de": "", "para": crm_status, "data": now, "usuario": user["name"],
                 "usuario_id": user["id"], "sincronizado_pd": True,
                 "status_pd": new_status, "label_pd": crm_label}
            )
            logger.info(f"Sincronizado P&D→CRM: Card {card_id} ({new_status}) → Variação {card['amostra_variacao_id']} ({crm_status} / {crm_label})")
        else:
            crm_label_obs = PD_CARD_STATUS_TO_CRM_DISPLAY.get(new_status, (None, PD_STATUS_LABELS.get(new_status, new_status)))[1]
            await _update_variacao_in_sample(
                card["amostra_id"], user["tenant_id"], card["amostra_variacao_id"],
                {"status_pd_label": crm_label_obs, "status_pd_raw": new_status,
                 "ultima_atualizacao_pd": now, "updated_at": now}
            )
            await _push_variacao_history(
                card["amostra_id"], user["tenant_id"], card["amostra_variacao_id"],
                {"de": "", "para": "", "data": now, "usuario": user["name"],
                 "usuario_id": user["id"], "sincronizado_pd": True,
                 "status_pd": new_status, "observacao": f"P&D movido para: {crm_label_obs}"}
            )
            logger.info(f"Histórico P&D→CRM: Card {card_id} ({new_status} / {crm_label_obs}) registrado na variação {card['amostra_variacao_id']}")

    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM pd_cards WHERE id=$1 AND tenant_id=$2", card_id, user["tenant_id"]
    ))
    await _broadcast_pd_card_update(user["tenant_id"], updated, old_status, new_status)

    try:
        await audit_log(
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            user_name=user.get("name", ""),
            action="pd_card_moved",
            entity_type="pd_card",
            entity_id=card_id,
            before={"status_pd": old_status},
            after={"status_pd": new_status, "observacao": data.observacao},
            metadata={
                "amostra_variacao_id": card.get("amostra_variacao_id"),
                "tasks_generated": [t["id"] for t in new_tasks],
            },
        )
    except Exception as exc:
        logger.error(f"[move_pd_card] audit_log falhou (ignorado): {exc}", exc_info=True)

    return {
        "card": updated,
        "from_status": PD_STATUS_LABELS.get(old_status, old_status),
        "to_status": PD_STATUS_LABELS.get(new_status, new_status),
        "synced_to_crm": True,
        "stability_study": stability_study,
        "tasks_generated": new_tasks,
    }


class PDCardUpdate(BaseModel):
    responsavel_pd: Optional[str] = None
    prazo_prometido: Optional[str] = None
    observacoes_especificas: Optional[str] = None

@crm_router.put("/pd/cards/{card_id}")
async def update_pd_card(card_id: str, data: PDCardUpdate, request: Request):
    """Atualizar informações de um card P&D"""
    user = await _get_current_user(request)
    require_roles(user, PD_WRITE)
    
    update_fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    
    update_fields["updated_at"] = _now_iso()
    
    now = _now_iso()
    extra_patch = {k: v for k, v in update_fields.items()}
    extra_patch["updated_at"] = now
    matched = await pg_db.fetch_val(
        "UPDATE pd_cards SET extra = extra || $1::jsonb, updated_at=$2 WHERE id=$3 AND tenant_id=$4 RETURNING id",
        json.dumps(extra_patch), now, card_id, user["tenant_id"]
    )
    if not matched:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    return _row(await pg_db.fetch_one(
        "SELECT * FROM pd_cards WHERE id=$1 AND tenant_id=$2", card_id, user["tenant_id"]
    ))


# ======================================================================
#  ALERTS
# ======================================================================

@crm_router.get("/alerts")
async def list_alerts(
    request: Request,
    status: Optional[str] = None,
    tipo: Optional[str] = None,
):
    user = await _get_current_user(request)
    query = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if tipo:
        query["tipo"] = tipo

    sql = "SELECT * FROM crm_alerts WHERE tenant_id=$1"
    params: list = [user["tenant_id"]]
    if status:
        params.append(status); sql += f" AND status=${len(params)}"
    if tipo:
        params.append(tipo); sql += f" AND tipo=${len(params)}"
    sql += " ORDER BY data_criacao DESC LIMIT 500"
    alerts = _rows(await pg_db.fetch_all(sql, *params))
    return alerts


@crm_router.put("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: str, request: Request):
    user = await _get_current_user(request)
    matched = await pg_db.fetch_val(
        "UPDATE crm_alerts SET status='lido' WHERE id=$1 AND tenant_id=$2 RETURNING id",
        alert_id, user["tenant_id"]
    )
    if not matched:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return {"message": "Alerta marcado como lido"}


@crm_router.put("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, data: AlertResolve, request: Request):
    user = await _get_current_user(request)
    now = _now_iso()
    matched = await pg_db.fetch_val(
        """UPDATE crm_alerts SET status='resolvido', resolved_at=$1, resolved_by=$2, resolved_comment=$3
           WHERE id=$4 AND tenant_id=$5 RETURNING id""",
        now, user["id"], data.comment, alert_id, user["tenant_id"]
    )
    if not matched:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return {"message": "Alerta resolvido"}


@crm_router.post("/alerts/check")
async def trigger_alert_check(request: Request):
    """Manual trigger for alert check"""
    user = await _get_current_user(request)
    count = await check_alerts_for_tenant(user["tenant_id"])
    return {"message": f"{count} alerta(s) gerado(s)", "count": count}


@crm_router.post("/follow-up/schedule")
async def schedule_follow_up(data: FollowUpSchedule, request: Request):
    """RN-FU-03: Agendamento de follow-up manual com data/hora"""
    user = await _get_current_user(request)
    
    # Validar que o cliente existe
    client = _row(await pg_db.fetch_one(
        "SELECT nome_empresa FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        data.client_id, user["tenant_id"]
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Validar data
    try:
        follow_up_date = datetime.fromisoformat(data.data_follow_up.replace("Z", "+00:00"))
        if follow_up_date < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Data de follow-up deve ser futura")
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida. Use formato ISO 8601")
    
    # Criar tarefa pendente de follow-up
    task_id = _new_id()
    task = {
        "id": task_id,
        "tenant_id": user["tenant_id"],
        "tipo": "follow_up_manual",
        "entidade_tipo": "client",
        "entidade_ref": data.client_id,
        "entidade_nome": client.get("nome_empresa", ""),
        "titulo": f"Follow-up agendado: {client.get('nome_empresa', '')}",
        "descricao": data.observacao or "Follow-up manual agendado",
        "data_agendada": data.data_follow_up,
        "status": "pendente",
        "responsavel": user["id"],
        "criado_por": user["id"],
        "criado_por_nome": user.get("name", ""),
        "data_criacao": _now_iso(),
    }
    
    await db.crm_tasks.insert_one(task)
    
    return {
        "message": "Follow-up agendado com sucesso",
        "task": task
    }


@crm_router.get("/follow-up/scheduled")
async def list_scheduled_follow_ups(request: Request):
    """Listar follow-ups agendados"""
    user = await _get_current_user(request)
    
    tasks = await db.crm_tasks.find(
        {"tenant_id": user["tenant_id"], "tipo": "follow_up_manual", "status": "pendente"},
        {"_id": 0}
    ).sort("data_agendada", 1).to_list(500)
    
    return tasks


async def check_alerts_for_tenant(tenant_id: str) -> int:
    """Check and generate alerts for a tenant"""
    now = datetime.now(timezone.utc)
    created_count = 0

    try:
        async def _alert_exists(tipo: str, ref: str) -> bool:
            r = await pg_db.fetch_val(
                "SELECT 1 FROM crm_alerts WHERE tenant_id=$1 AND tipo=$2 AND entidade_ref=$3 AND status!='resolvido'",
                tenant_id, tipo, ref
            )
            return bool(r)

        async def _insert_alert(tipo: str, ref: str, etipo: str, enome: str, msg: str, resp: str = "") -> None:
            nonlocal created_count
            await pg_db.execute(
                """INSERT INTO crm_alerts (id, tenant_id, tipo, entidade_ref, entidade_tipo, entidade_nome,
                   mensagem, data_criacao, status, responsavel) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'pendente',$9)""",
                _new_id(), tenant_id, tipo, ref, etipo, enome, msg, _now_iso(), resp
            )
            created_count += 1

        # ALERT_001: Sample in "enviada" > 7 days
        samples_enviadas = _rows(await pg_db.fetch_all(
            "SELECT * FROM crm_samples WHERE tenant_id=$1 AND stage='enviada'", tenant_id
        ))
        for s in samples_enviadas:
            updated = s.get("updated_at") or s.get("created_at", "")
            try:
                dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                if (now - dt).days > 7 and not await _alert_exists("ALERT_001", s["id"]):
                    await _insert_alert("ALERT_001", s["id"], "sample", s.get("nome_amostra", ""),
                        f"Amostra '{s.get('nome_amostra', '')}' está em 'Enviada' há mais de 7 dias sem movimentação.",
                        s.get("responsavel_pd") or s.get("created_by", ""))
            except Exception:
                pass

        # ALERT_002: Client in "negociacao" > 30 days
        clients_neg = _rows(await pg_db.fetch_all(
            "SELECT * FROM crm_clients WHERE tenant_id=$1 AND stage='negociacao'", tenant_id
        ))
        for c in clients_neg:
            updated = c.get("updated_at") or c.get("created_at", "")
            try:
                dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                if (now - dt).days > 30 and not await _alert_exists("ALERT_002", c["id"]):
                    await _insert_alert("ALERT_002", c["id"], "client", c.get("nome_empresa", ""),
                        f"Cliente '{c.get('nome_empresa', '')}' está em 'Negociação' há mais de 30 dias.",
                        c.get("created_by", ""))
            except Exception:
                pass

        # ALERT_003: Active SKU without order > 60 days
        active_skus = _rows(await pg_db.fetch_all(
            "SELECT * FROM skus WHERE tenant_id=$1 AND status='ativo'", tenant_id
        ))
        clients_perdidos = _rows(await pg_db.fetch_all(
            "SELECT * FROM crm_clients WHERE tenant_id=$1 AND stage='cliente_perdido'", tenant_id
        ))
        for c in clients_perdidos:
            ref_date = c.get("updated_at") or c.get("created_at", "")
            try:
                dt = datetime.fromisoformat(str(ref_date).replace("Z", "+00:00"))
                if (now - dt).days >= 90 and not await _alert_exists("ALERT_008", c["id"]):
                    await _insert_alert("ALERT_008", c["id"], "client", c.get("nome_empresa", ""),
                        f"Cliente perdido '{c.get('nome_empresa', '')}' pode ser reativado após 90 dias.",
                        c.get("created_by", ""))
            except Exception:
                pass

        for sku in active_skus:
            ref_date = sku.get("data_ultimo_pedido") or sku.get("created_at", "")
            try:
                dt = datetime.fromisoformat(str(ref_date).replace("Z", "+00:00"))
                if (now - dt).days > 60 and not await _alert_exists("ALERT_003", sku["id"]):
                    await _insert_alert("ALERT_003", sku["id"], "sku",
                        f"{sku.get('codigo_interno', '')} - {sku.get('nome_produto', '')}",
                        f"SKU '{sku.get('codigo_interno', '')}' ativo sem pedido registrado há mais de 60 dias.")
            except Exception:
                pass

        # ALERT_004: Client in "cliente_fechado" without new project > 90 days
        clients_fechado = _rows(await pg_db.fetch_all(
            "SELECT * FROM crm_clients WHERE tenant_id=$1 AND stage='cliente_fechado'", tenant_id
        ))
        for c in clients_fechado:
            last_proj = _row(await pg_db.fetch_one(
                "SELECT created_at FROM crm_projects WHERE cliente_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 1",
                c["id"], tenant_id
            ))
            ref_date = (last_proj.get("created_at") if last_proj else None) or c.get("updated_at") or c.get("created_at", "")
            try:
                dt = datetime.fromisoformat(str(ref_date).replace("Z", "+00:00"))
                if (now - dt).days > 90 and not await _alert_exists("ALERT_004", c["id"]):
                    await _insert_alert("ALERT_004", c["id"], "client", c.get("nome_empresa", ""),
                        f"Cliente fechado '{c.get('nome_empresa', '')}' sem novo projeto há mais de 90 dias.",
                        c.get("created_by", ""))
            except Exception:
                pass

        # ALERT_005: SKU ANVISA expiring in ≤ 60 days
        for sku in active_skus:
            anvisa_val = (sku.get("anvisa") or {}).get("validade")
            if anvisa_val:
                try:
                    dt = datetime.fromisoformat(str(anvisa_val).replace("Z", "+00:00"))
                    if 0 <= (dt - now).days <= 60 and not await _alert_exists("ALERT_005", sku["id"]):
                        await _insert_alert("ALERT_005", sku["id"], "sku",
                            f"{sku.get('codigo_interno', '')} - {sku.get('nome_produto', '')}",
                            f"ANVISA do SKU '{sku.get('codigo_interno', '')}' vence em {(dt - now).days} dias.")
                except Exception:
                    pass

        # ALERT_006: previsao_segundo_pedido D-7
        clients_with_previsao = _rows(await pg_db.fetch_all(
            "SELECT * FROM crm_clients WHERE tenant_id=$1 AND previsao_segundo_pedido IS NOT NULL", tenant_id
        ))
        for c in clients_with_previsao:
            previsao = c.get("previsao_segundo_pedido")
            if previsao:
                try:
                    dt = datetime.fromisoformat(str(previsao).replace("Z", "+00:00"))
                    days_until = (dt - now).days
                    if 0 <= days_until <= 7 and not await _alert_exists("ALERT_006", c["id"]):
                        await _insert_alert("ALERT_006", c["id"], "client", c.get("nome_empresa", ""),
                            f"Previsão de segundo pedido de '{c.get('nome_empresa', '')}' em {days_until} dia(s).",
                            c.get("created_by", ""))
                except Exception:
                    pass

        # ALERT_007: Variação em "solicitada" sem P&D aceitar > 2 dias úteis
        samples_with_variacoes = _rows(await pg_db.fetch_all(
            "SELECT * FROM crm_samples WHERE tenant_id=$1 AND jsonb_array_length(variacoes) > 0", tenant_id
        ))
        for sample in samples_with_variacoes:
            for variacao in sample.get("variacoes", []):
                if variacao.get("status") == "solicitada":
                    pd_card = _row(await pg_db.fetch_one(
                        "SELECT id, created_at FROM pd_cards WHERE amostra_variacao_id=$1 AND status_pd='solicitado' AND tenant_id=$2",
                        variacao["id"], tenant_id
                    ))
                    if pd_card:
                        created = pd_card.get("created_at", "")
                        try:
                            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                            days_elapsed = (now - dt).days
                            if days_elapsed > 2 and not await _alert_exists("ALERT_007", variacao["id"]):
                                await _insert_alert("ALERT_007", variacao["id"], "variacao",
                                    f"{sample.get('nome_produto', '')} - {variacao.get('codigo', '')}",
                                    f"Variação '{variacao.get('codigo', '')}' está em 'Solicitada' há {days_elapsed} dias sem aceite do P&D.",
                                    sample.get("responsavel_pd", ""))
                        except Exception:
                            pass

        # RN-FU-01: Follow-up automático por etapa
        for stage, prazo_dias in FOLLOW_UP_PRAZOS.items():
            if stage in ["cliente_fechado", "cliente_perdido"]:
                continue
            clients_in_stage = _rows(await pg_db.fetch_all(
                "SELECT * FROM crm_clients WHERE tenant_id=$1 AND stage=$2", tenant_id, stage
            ))
            for c in clients_in_stage:
                last_interaction = c.get("updated_at") or c.get("created_at", "")
                historico = c.get("historico_movimentacoes", [])
                if historico:
                    last_interaction = historico[-1].get("data", last_interaction)
                try:
                    dt = datetime.fromisoformat(str(last_interaction).replace("Z", "+00:00"))
                    days_without_interaction = (now - dt).days
                    if days_without_interaction > prazo_dias and not await _alert_exists("FOLLOW_UP", c["id"]):
                        stage_label = STAGE_LABELS.get(stage, stage)
                        await _insert_alert("FOLLOW_UP", c["id"], "client", c.get("nome_empresa", ""),
                            f"Cliente '{c.get('nome_empresa', '')}' está em '{stage_label}' há {days_without_interaction} dias sem interação (prazo: {prazo_dias} dias).",
                            c.get("responsavel_comercial") or c.get("created_by", ""))
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Alert check error for tenant {tenant_id}: {e}")

    return created_count


async def run_alert_scheduler():
    """Background task that checks alerts every hour for all tenants"""
    await asyncio.sleep(30)  # Wait 30s after startup
    while True:
        try:
            tenants = await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(500)
            total = 0
            for t in tenants:
                count = await check_alerts_for_tenant(t["id"])
                total += count
            if total > 0:
                logger.info(f"Alert scheduler: created {total} alerts across {len(tenants)} tenants")
        except Exception as e:
            logger.error(f"Alert scheduler error: {e}")
        await asyncio.sleep(3600)  # Every hour


# ======================================================================
#  DASHBOARD & REPORTS
# ======================================================================

@crm_router.get("/dashboard")
async def crm_dashboard(request: Request):
    user = await _get_current_user(request)
    tid = user["tenant_id"]

    # Funnel: count per stage
    funnel = []
    for stage in CLIENT_STAGES:
        count = await pg_db.fetch_val(
            "SELECT COUNT(*) FROM crm_clients WHERE tenant_id=$1 AND stage=$2", tid, stage
        ) or 0
        funnel.append({"stage": stage, "label": STAGE_LABELS.get(stage, stage), "count": count})

    # Conversion rates
    total_clients = sum(s["count"] for s in funnel)
    for s in funnel:
        s["percentage"] = round((s["count"] / total_clients * 100), 1) if total_clients > 0 else 0

    # Metrics
    active_clients = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM crm_clients WHERE tenant_id=$1 AND stage != 'cliente_perdido'", tid
    ) or 0
    samples_in_progress = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM crm_samples WHERE tenant_id=$1 AND stage = ANY($2::text[])",
        tid, ["solicitada", "em_elaboracao", "retrabalho", "enviada"]
    ) or 0
    active_skus = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM skus WHERE tenant_id=$1 AND status='ativo'", tid
    ) or 0
    pending_alerts = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM crm_alerts WHERE tenant_id=$1 AND status='pendente'", tid
    ) or 0
    total_projects = await pg_db.fetch_val(
        "SELECT COUNT(*) FROM crm_projects WHERE tenant_id=$1", tid
    ) or 0

    # Today's alerts
    today_alerts = _rows(await pg_db.fetch_all(
        "SELECT * FROM crm_alerts WHERE tenant_id=$1 AND status='pendente' ORDER BY data_criacao DESC LIMIT 20",
        tid
    ))

    return {
        "funnel": funnel,
        "metrics": {
            "total_clients": total_clients,
            "active_clients": active_clients,
            "total_projects": total_projects,
            "samples_in_progress": samples_in_progress,
            "active_skus": active_skus,
            "pending_alerts": pending_alerts,
        },
        "today_alerts": today_alerts,
    }


@crm_router.get("/reports/client/{client_id}")
async def client_report(client_id: str, request: Request):
    user = await _get_current_user(request)
    client = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_clients WHERE id=$1 AND tenant_id=$2", client_id, user["tenant_id"]
    ))
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # SKUs linked to this client
    skus = _rows(await pg_db.fetch_all(
        "SELECT * FROM skus WHERE cliente_id=$1 AND tenant_id=$2", client_id, user["tenant_id"]
    ))

    # Aggregate orders across all SKUs
    all_orders = []
    for sku in skus:
        for order in sku.get("historico_pedidos", []):
            order["sku_codigo"] = sku["codigo_interno"]
            order["sku_nome"] = sku["nome_produto"]
            all_orders.append(order)

    total_orders = len(all_orders)
    total_value = sum(o.get("valor_total", 0) for o in all_orders)
    quantities = [o.get("quantidade", 0) for o in all_orders]

    avg_quantity = sum(quantities) / len(quantities) if quantities else 0
    max_quantity = max(quantities) if quantities else 0
    min_quantity = min(quantities) if quantities else 0

    # Last order
    last_order = None
    if all_orders:
        sorted_orders = sorted(all_orders, key=lambda x: x.get("data_pedido", ""), reverse=True)
        last_order = sorted_orders[0]

    # Reorder frequency (average across SKUs)
    freqs = [s.get("frequencia_media_recompra_dias", 0) for s in skus if s.get("frequencia_media_recompra_dias", 0) > 0]
    avg_freq = sum(freqs) / len(freqs) if freqs else 0

    # Projects
    projects = _rows(await pg_db.fetch_all(
        "SELECT * FROM crm_projects WHERE cliente_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 500",
        client_id, user["tenant_id"]
    ))

    # Samples
    samples = _rows(await pg_db.fetch_all(
        "SELECT * FROM crm_samples WHERE cliente_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 500",
        client_id, user["tenant_id"]
    ))

    return {
        "client": client,
        "orders": {
            "total_orders": total_orders,
            "total_value": total_value,
            "last_order": last_order,
            "avg_quantity": round(avg_quantity, 1),
            "max_quantity": max_quantity,
            "min_quantity": min_quantity,
            "avg_reorder_frequency_days": round(avg_freq),
        },
        "skus_ativos": [s for s in skus if s.get("status") == "ativo"],
        "all_skus": skus,
        "projects": projects,
        "samples": samples,
        "timeline": client.get("historico_movimentacoes", []),
    }


@crm_router.get("/reports/sku/{sku_id}")
async def sku_report(sku_id: str, request: Request):
    user = await _get_current_user(request)
    sku = _row(await pg_db.fetch_one(
        "SELECT * FROM skus WHERE id=$1 AND tenant_id=$2", sku_id, user["tenant_id"]
    ))
    if not sku:
        raise HTTPException(status_code=404, detail="SKU não encontrado")

    orders = sku.get("historico_pedidos", [])
    total_produced = sum(o.get("quantidade", 0) for o in orders)
    total_orders = len(orders)

    # Last production date
    last_production = None
    if orders:
        sorted_orders = sorted(orders, key=lambda x: x.get("data_pedido", ""), reverse=True)
        last_production = sorted_orders[0].get("data_pedido")

    # Find all clients that have this SKU (via amostras_aprovadas or skus_confirmados)
    clients_with_sku = _rows(await pg_db.fetch_all(
        """SELECT id, nome_empresa FROM crm_clients WHERE tenant_id=$1
           AND (amostras_aprovadas @> $2::jsonb OR skus_confirmados @> $2::jsonb)""",
        user["tenant_id"], json.dumps([sku_id])
    ))

    # Also check via the direct cliente_id
    main_client = _row(await pg_db.fetch_one(
        "SELECT id, nome_empresa FROM crm_clients WHERE id=$1 AND tenant_id=$2",
        sku["cliente_id"], user["tenant_id"]
    ))

    all_client_ids = set(c["id"] for c in clients_with_sku)
    if main_client and main_client["id"] not in all_client_ids:
        clients_with_sku.append(main_client)

    # ANVISA status
    anvisa = sku.get("anvisa", {})
    anvisa_status = "N/A"
    if anvisa.get("numero"):
        if anvisa.get("validade"):
            try:
                val_dt = datetime.fromisoformat(str(anvisa["validade"]).replace("Z", "+00:00"))
                days_left = (val_dt - datetime.now(timezone.utc)).days
                if days_left < 0:
                    anvisa_status = "Vencido"
                elif days_left <= 60:
                    anvisa_status = f"Vence em {days_left} dias"
                else:
                    anvisa_status = "Válido"
            except Exception:
                anvisa_status = "Válido"
        else:
            anvisa_status = "Sem validade"

    return {
        "sku": sku,
        "last_production_date": last_production,
        "total_produced": total_produced,
        "total_orders": total_orders,
        "order_frequency_days": sku.get("frequencia_media_recompra_dias", 0),
        "clients": clients_with_sku,
        "anvisa_status": anvisa_status,
        "orders": orders,
    }


# ======================================================================
#  CRM CONFIG — Customizable Columns & Fields (Pipefy-style)
# ======================================================================

DEFAULT_CRM_COLUMNS = {
    "clients": [
        {"key": "prospeccao", "label": "Prospecção", "color": "bg-blue-500", "order": 0, "is_system": True},
        {"key": "qualificado", "label": "Qualificado", "color": "bg-cyan-500", "order": 1, "is_system": True},
        {"key": "projeto_em_discussao", "label": "Projeto em Discussão", "color": "bg-violet-500", "order": 2, "is_system": True},
        {"key": "negociacao", "label": "Negociação", "color": "bg-amber-500", "order": 3, "is_system": True},
        {"key": "cliente_fechado", "label": "Cliente Fechado", "color": "bg-emerald-500", "order": 4, "is_system": True},
        {"key": "cliente_perdido", "label": "Cliente Perdido", "color": "bg-red-500", "order": 5, "is_system": True},
    ],
    "projects": [
        {"key": "projeto_em_discussao", "label": "Projeto em Discussão", "color": "bg-violet-500", "order": 0, "is_system": True},
        {"key": "amostras", "label": "Amostras", "color": "bg-emerald-500", "order": 1, "is_system": True},
    ],
    "samples": [
        {"key": "solicitada", "label": "Solicitada", "color": "bg-slate-400", "order": 0, "is_system": True},
        {"key": "em_elaboracao", "label": "Em Elaboração", "color": "bg-blue-500", "order": 1, "is_system": True},
        {"key": "retrabalho", "label": "Retrabalho", "color": "bg-amber-500", "order": 2, "is_system": True},
        {"key": "enviada", "label": "Enviada", "color": "bg-cyan-500", "order": 3, "is_system": True},
        {"key": "aprovada", "label": "Aprovada", "color": "bg-emerald-500", "order": 4, "is_system": True},
        {"key": "reprovada", "label": "Reprovada", "color": "bg-red-500", "order": 5, "is_system": True},
    ],
}

FIELD_TYPES = ["text", "number", "date", "select", "textarea", "boolean", "email", "phone"]


class CRMColumnCreate(BaseModel):
    crm_type: str
    label: str
    color: str = "bg-gray-500"

class CRMColumnUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None

class CRMColumnReorder(BaseModel):
    column_ids: List[str]

class CRMFieldCreate(BaseModel):
    column_id: str
    label: str
    type: str = "text"
    required: bool = False
    options: List[str] = []

class CRMFieldUpdate(BaseModel):
    label: Optional[str] = None
    type: Optional[str] = None
    required: Optional[bool] = None
    options: Optional[List[str]] = None


async def _ensure_crm_config(tenant_id: str, crm_type: str):
    """Seed default CRM config if not exists"""
    existing = await pg_db.fetch_val(
        "SELECT 1 FROM crm_column_configs WHERE tenant_id=$1 AND crm_type=$2 LIMIT 1",
        tenant_id, crm_type
    )
    if existing:
        return

    defaults = DEFAULT_CRM_COLUMNS.get(crm_type, [])
    for col_def in defaults:
        col_id = _new_id()
        await pg_db.execute(
            """INSERT INTO crm_column_configs (id, tenant_id, crm_type, key, label, color, "order", is_system, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            col_id, tenant_id, crm_type,
            col_def["key"], col_def["label"], col_def["color"], col_def["order"],
            col_def.get("is_system", False), _now_iso()
        )
    logger.info(f"Seeded CRM config for {crm_type} tenant {tenant_id}")


# ======================================================================
#  LEAD SOURCES CONFIG (CRM-12: configurable canal_origem)
# ======================================================================

class LeadSourceCreate(BaseModel):
    nome: str
    valor: str
    grupo: str = ""
    ativo: bool = True

class LeadSourceUpdate(BaseModel):
    nome: Optional[str] = None
    ativo: Optional[bool] = None
    grupo: Optional[str] = None


async def _get_valid_lead_sources(tenant_id: str) -> list:
    """Returns valid valor slugs: hardcoded defaults plus any DB-added sources."""
    sources = _rows(await pg_db.fetch_all(
        "SELECT valor FROM lead_sources WHERE tenant_id=$1 AND ativo=TRUE",
        tenant_id
    ))
    combined = list(CANAL_ORIGEM_OPTIONS)
    for s in sources:
        if s["valor"] not in combined:
            combined.append(s["valor"])
    return combined


@crm_router.get("/config/lead-sources")
async def list_lead_sources(request: Request):
    user = await _get_current_user(request)
    sources = _rows(await pg_db.fetch_all(
        "SELECT id, tenant_id, valor, nome, grupo, ativo FROM lead_sources WHERE tenant_id=$1 ORDER BY grupo",
        user["tenant_id"]
    ))
    if not sources:
        return [
            {"id": v, "valor": v, "nome": v.replace("_", " ").title(), "grupo": _slug_to_group(v), "ativo": True}
            for v in CANAL_ORIGEM_OPTIONS
        ]
    return sources


def _slug_to_group(valor: str) -> str:
    for group, members in CANAL_ORIGEM_GROUPS.items():
        if valor in members:
            return group
    return "outros"


@crm_router.post("/config/lead-sources")
async def create_lead_source(body: LeadSourceCreate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, ADMIN_ONLY)
    existing = await pg_db.fetch_val(
        "SELECT 1 FROM lead_sources WHERE tenant_id=$1 AND valor=$2",
        user["tenant_id"], body.valor
    )
    if existing:
        raise HTTPException(status_code=409, detail="Já existe uma fonte com esse valor/slug")
    await pg_db.execute(
        "INSERT INTO lead_sources (id, tenant_id, valor, nome, grupo, ativo, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7)",
        body.valor, user["tenant_id"], body.valor, body.nome.strip(), body.grupo.strip(), body.ativo, _now_iso()
    )
    return {
        "id": body.valor, "valor": body.valor, "nome": body.nome.strip(),
        "grupo": body.grupo.strip(), "ativo": body.ativo,
        "tenant_id": user["tenant_id"], "created_at": _now_iso(),
    }


@crm_router.patch("/config/lead-sources/{source_id}")
async def update_lead_source(source_id: str, body: LeadSourceUpdate, request: Request):
    user = await _get_current_user(request)
    require_roles(user, ADMIN_ONLY)
    source = _row(await pg_db.fetch_one(
        "SELECT id, ativo FROM lead_sources WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], source_id
    ))
    if not source:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    if body.ativo is False and source.get("ativo", True):
        in_use = await pg_db.fetch_val(
            "SELECT 1 FROM crm_clients WHERE tenant_id=$1 AND canal_origem=$2 LIMIT 1",
            user["tenant_id"], source_id
        )
        if in_use:
            raise HTTPException(
                status_code=409,
                detail="Não é possível desativar: há clientes usando este canal de origem"
            )
    params: list = []
    set_parts: list[str] = []
    if body.nome is not None:
        params.append(body.nome.strip()); set_parts.append(f"nome=${len(params)}")
    if body.ativo is not None:
        params.append(body.ativo); set_parts.append(f"ativo=${len(params)}")
    if body.grupo is not None:
        params.append(body.grupo.strip()); set_parts.append(f"grupo=${len(params)}")
    if set_parts:
        params.extend([user["tenant_id"], source_id])
        await pg_db.execute(
            f"UPDATE lead_sources SET {', '.join(set_parts)} WHERE tenant_id=${len(params)-1} AND id=${len(params)}",
            *params
        )
    return {"ok": True}


# ======================================================================
#  CONSTANTS ENDPOINT (PRD Lists)
# ======================================================================

@crm_router.get("/constants")
async def get_crm_constants(request: Request):
    """Retorna todas as constantes do PRD para o frontend"""
    user = await _get_current_user(request)
    db_sources = _rows(await pg_db.fetch_all(
        "SELECT valor, grupo FROM lead_sources WHERE tenant_id=$1 AND ativo=TRUE ORDER BY grupo",
        user["tenant_id"]
    ))
    if db_sources:
        canal_origem_list = [s["valor"] for s in db_sources]
        canal_origem_groups: dict = {}
        for s in db_sources:
            g = s.get("grupo", "outros") or "outros"
            canal_origem_groups.setdefault(g, []).append(s["valor"])
    else:
        canal_origem_list = CANAL_ORIGEM_OPTIONS
        canal_origem_groups = CANAL_ORIGEM_GROUPS

    return {
        "canal_origem": canal_origem_list,
        "canal_origem_grupos": canal_origem_groups,
        "categoria_interesse": CATEGORIA_INTERESSE_OPTIONS,
        "categorias_grau2": CATEGORIAS_GRAU2,
        "origem_lead": ORIGEM_LEAD_OPTIONS,
        "volume_estimado": VOLUME_ESTIMADO_OPTIONS,
        "tem_anvisa": TEM_ANVISA_OPTIONS,
        "motivo_perda": MOTIVO_PERDA_OPTIONS,
        "segmento": SEGMENTO_CLIENTE_OPTIONS,
        "porte": PORTE_CLIENTE_OPTIONS,
        "temperatura_lead": TEMPERATURA_LEAD_OPTIONS,
        "cargo_decisor": CARGO_DECISOR_OPTIONS,
        "ufs": UF_OPTIONS,
        "project_posicionamento": PROJECT_POSICIONAMENTO_OPTIONS,
        "project_tipo_servico": PROJECT_TIPO_SERVICO_OPTIONS,
        "project_restricoes_tecnicas": PROJECT_RESTRICAO_TECNICA_OPTIONS,
        "sample_tipos": TIPO_AMOSTRA_OPTIONS,
        "sample_unidades": UNIDADE_QUANTIDADE_AMOSTRA_OPTIONS,
        "sample_parametros_variacao": SAMPLE_VARIATION_PARAM_OPTIONS,
        "sample_resultados": SAMPLE_RESULTADO_OPTIONS,
        "follow_up_prazos": FOLLOW_UP_PRAZOS,
        "client_stages": CLIENT_STAGES,
        "project_stages": PROJECT_STAGES,
        "sample_stages": SAMPLE_STAGES,
        "stage_labels": STAGE_LABELS,
    }


@crm_router.get("/config/{crm_type}/columns")
async def get_crm_columns(crm_type: str, request: Request):
    user = await _get_current_user(request)
    if crm_type not in ("clients", "projects", "samples"):
        raise HTTPException(status_code=400, detail="Tipo de CRM inválido")

    await _ensure_crm_config(user["tenant_id"], crm_type)

    columns = _rows(await pg_db.fetch_all(
        """SELECT id, tenant_id, crm_type, key, label, color, "order", is_system
           FROM crm_column_configs WHERE tenant_id=$1 AND crm_type=$2 ORDER BY "order" """,
        user["tenant_id"], crm_type
    ))

    col_ids = [c["id"] for c in columns]
    fields: list = []
    if col_ids:
        fields = _rows(await pg_db.fetch_all(
            """SELECT id, tenant_id, column_id, label, type, required, "order", options
               FROM crm_field_configs WHERE column_id = ANY($1::text[]) AND tenant_id=$2 ORDER BY "order" """,
            col_ids, user["tenant_id"]
        ))

    fields_by_col: dict = {}
    for f in fields:
        fields_by_col.setdefault(f["column_id"], []).append(f)

    for col in columns:
        col["fields"] = fields_by_col.get(col["id"], [])

    return {"columns": columns, "field_types": FIELD_TYPES}


@crm_router.post("/config/columns")
async def create_crm_column(data: CRMColumnCreate, request: Request):
    user = await _get_current_user(request)
    if data.crm_type not in ("clients", "projects", "samples"):
        raise HTTPException(status_code=400, detail="Tipo de CRM inválido")

    await _ensure_crm_config(user["tenant_id"], data.crm_type)

    next_order = await pg_db.fetch_val(
        """SELECT COALESCE(MAX("order") + 1, 0) FROM crm_column_configs WHERE tenant_id=$1 AND crm_type=$2""",
        user["tenant_id"], data.crm_type
    ) or 0

    col_id = _new_id()
    key = data.label.lower().replace(" ", "_").replace("/", "_")
    await pg_db.execute(
        """INSERT INTO crm_column_configs (id, tenant_id, crm_type, key, label, color, "order", is_system, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
        col_id, user["tenant_id"], data.crm_type, key, data.label, data.color, next_order, False, _now_iso()
    )
    _update_stage_config(data.crm_type, key)

    return {
        "id": col_id, "tenant_id": user["tenant_id"], "crm_type": data.crm_type,
        "key": key, "label": data.label, "color": data.color, "order": next_order,
        "is_system": False, "created_at": _now_iso(), "fields": []
    }


@crm_router.put("/config/columns/{column_id}")
async def update_crm_column(column_id: str, data: CRMColumnUpdate, request: Request):
    user = await _get_current_user(request)
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nada para atualizar")

    params: list = []
    set_parts: list[str] = []
    for k, v in updates.items():
        pg_col = '"order"' if k == "order" else k
        params.append(v); set_parts.append(f"{pg_col}=${len(params)}")
    params.extend([user["tenant_id"], column_id])
    matched = await pg_db.fetch_val(
        f"UPDATE crm_column_configs SET {', '.join(set_parts)} WHERE tenant_id=${len(params)-1} AND id=${len(params)} RETURNING id",
        *params
    )
    if not matched:
        raise HTTPException(status_code=404, detail="Coluna não encontrada")
    return _row(await pg_db.fetch_one(
        """SELECT id, tenant_id, crm_type, key, label, color, "order", is_system FROM crm_column_configs WHERE id=$1""",
        column_id
    ))


@crm_router.delete("/config/columns/{column_id}")
async def delete_crm_column(column_id: str, request: Request):
    user = await _get_current_user(request)
    col = _row(await pg_db.fetch_one(
        """SELECT id, crm_type, key, is_system FROM crm_column_configs WHERE id=$1 AND tenant_id=$2""",
        column_id, user["tenant_id"]
    ))
    if not col:
        raise HTTPException(status_code=404, detail="Coluna não encontrada")

    if col.get("is_system"):
        raise HTTPException(status_code=400, detail="Não é possível excluir coluna do sistema")

    table_map = {"clients": "crm_clients", "projects": "crm_projects", "samples": "crm_samples"}
    tbl = table_map.get(col["crm_type"])
    if tbl:
        count = await pg_db.fetch_val(
            f"SELECT COUNT(*) FROM {tbl} WHERE tenant_id=$1 AND stage=$2",
            user["tenant_id"], col["key"]
        )
        if count:
            raise HTTPException(status_code=400, detail=f"Não é possível excluir: {count} item(ns) nesta coluna")

    await pg_db.execute("DELETE FROM crm_field_configs WHERE column_id=$1", column_id)
    await pg_db.execute("DELETE FROM crm_column_configs WHERE id=$1 AND tenant_id=$2", column_id, user["tenant_id"])
    return {"message": "Coluna removida"}


@crm_router.put("/config/columns/reorder")
async def reorder_crm_columns(data: CRMColumnReorder, request: Request):
    user = await _get_current_user(request)
    for i, cid in enumerate(data.column_ids):
        await pg_db.execute(
            """UPDATE crm_column_configs SET "order"=$1 WHERE id=$2 AND tenant_id=$3""",
            i, cid, user["tenant_id"]
        )
    return {"message": "Colunas reordenadas"}


@crm_router.post("/config/fields")
async def create_crm_field(data: CRMFieldCreate, request: Request):
    user = await _get_current_user(request)
    col_exists = await pg_db.fetch_val(
        "SELECT 1 FROM crm_column_configs WHERE id=$1 AND tenant_id=$2",
        data.column_id, user["tenant_id"]
    )
    if not col_exists:
        raise HTTPException(status_code=404, detail="Coluna não encontrada")

    if data.type not in FIELD_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de campo inválido: {data.type}")

    next_order = await pg_db.fetch_val(
        """SELECT COALESCE(MAX("order") + 1, 0) FROM crm_field_configs WHERE column_id=$1""",
        data.column_id
    ) or 0

    field_id = _new_id()
    await pg_db.execute(
        """INSERT INTO crm_field_configs (id, tenant_id, column_id, label, type, required, options, "order", created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
        field_id, user["tenant_id"], data.column_id, data.label, data.type,
        data.required, data.options, next_order, _now_iso()
    )
    return {
        "id": field_id, "tenant_id": user["tenant_id"], "column_id": data.column_id,
        "label": data.label, "type": data.type, "required": data.required,
        "options": data.options, "order": next_order, "created_at": _now_iso(),
    }


@crm_router.put("/config/fields/{field_id}")
async def update_crm_field(field_id: str, data: CRMFieldUpdate, request: Request):
    user = await _get_current_user(request)
    updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nada para atualizar")

    params: list = []
    set_parts: list[str] = []
    for k, v in updates.items():
        pg_col = '"order"' if k == "order" else k
        params.append(v); set_parts.append(f"{pg_col}=${len(params)}")
    params.extend([user["tenant_id"], field_id])
    matched = await pg_db.fetch_val(
        f"UPDATE crm_field_configs SET {', '.join(set_parts)} WHERE tenant_id=${len(params)-1} AND id=${len(params)} RETURNING id",
        *params
    )
    if not matched:
        raise HTTPException(status_code=404, detail="Campo não encontrado")
    return _row(await pg_db.fetch_one(
        """SELECT id, tenant_id, column_id, label, type, required, "order", options FROM crm_field_configs WHERE id=$1""",
        field_id
    ))


@crm_router.delete("/config/fields/{field_id}")
async def delete_crm_field(field_id: str, request: Request):
    user = await _get_current_user(request)
    deleted = await pg_db.fetch_val(
        "DELETE FROM crm_field_configs WHERE id=$1 AND tenant_id=$2 RETURNING id",
        field_id, user["tenant_id"]
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Campo não encontrado")
    return {"message": "Campo removido"}


def _update_stage_config(crm_type: str, new_key: str):
    """Add new custom key to runtime stage/transition configs"""
    global CLIENT_STAGES, CLIENT_TRANSITIONS, PROJECT_STAGES, PROJECT_TRANSITIONS, SAMPLE_STAGES, SAMPLE_TRANSITIONS
    if crm_type == "clients":
        if new_key not in CLIENT_STAGES:
            # Insert before last 2 (fechado, perdido)
            idx = max(0, len(CLIENT_STAGES) - 2)
            CLIENT_STAGES.insert(idx, new_key)
            CLIENT_TRANSITIONS[new_key] = [CLIENT_STAGES[idx + 1] if idx + 1 < len(CLIENT_STAGES) else "cliente_perdido", "cliente_perdido"]
            # Allow previous stage to transition to new stage
            if idx > 0:
                prev = CLIENT_STAGES[idx - 1]
                if new_key not in CLIENT_TRANSITIONS.get(prev, []):
                    CLIENT_TRANSITIONS[prev].insert(0, new_key)
    elif crm_type == "projects":
        if new_key not in PROJECT_STAGES:
            PROJECT_STAGES.insert(-1, new_key)
            PROJECT_TRANSITIONS[new_key] = [PROJECT_STAGES[-1]]
    elif crm_type == "samples":
        if new_key not in SAMPLE_STAGES:
            idx = max(0, len(SAMPLE_STAGES) - 2)
            SAMPLE_STAGES.insert(idx, new_key)
            SAMPLE_TRANSITIONS[new_key] = [SAMPLE_STAGES[idx + 1] if idx + 1 < len(SAMPLE_STAGES) else "reprovada"]


# ======================================================================
#  ENUM OPTIONS (for frontend forms)
# ======================================================================

@crm_router.get("/options")
async def get_options(request: Request):
    """Return all enum options for frontend forms"""
    await _get_current_user(request)
    return {
        "canal_origem": CANAL_ORIGEM_OPTIONS,
        "canal_origem_grupos": CANAL_ORIGEM_GROUPS,
        "categoria_interesse": CATEGORIA_INTERESSE_OPTIONS,
        "origem_lead": ORIGEM_LEAD_OPTIONS,
        "volume_estimado_mensal": VOLUME_ESTIMADO_OPTIONS,
        "tem_anvisa": TEM_ANVISA_OPTIONS,
        "segmento": SEGMENTO_CLIENTE_OPTIONS,
        "porte": PORTE_CLIENTE_OPTIONS,
        "temperatura_lead": TEMPERATURA_LEAD_OPTIONS,
        "cargo_decisor": CARGO_DECISOR_OPTIONS,
        "ufs": UF_OPTIONS,
        "client_stages": [{"value": s, "label": STAGE_LABELS.get(s, s)} for s in CLIENT_STAGES],
        "project_stages": [{"value": s, "label": STAGE_LABELS.get(s, s)} for s in PROJECT_STAGES],
        "sample_stages": [{"value": s, "label": STAGE_LABELS.get(s, s)} for s in SAMPLE_STAGES],
    }


@crm_router.get("/users-list")
async def list_crm_users(request: Request):
    """List users for assignment dropdowns"""
    user = await _get_current_user(request)
    users = await db.users.find(
        {"tenant_id": user["tenant_id"]},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(100)
    return users
