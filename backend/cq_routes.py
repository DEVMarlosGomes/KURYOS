"""
CQ Module — Controle de Qualidade (PostgreSQL backend)

Collections (all immutable — no DELETE endpoints):
  cq_registros_analise, cq_checklists, cq_rncs,
  cq_retencoes, cq_instrumentos, cq_status_lote
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import logging

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from rbac import require_roles, has_role
from workflow_engine import audit_log, create_workflow_task
import database as pg_db

logger = logging.getLogger(__name__)

cq_router = APIRouter(prefix="/api/cq")

# ── Module state ───────────────────────────────────────────────────────────────
db = None            # MongoDB — cross-module: pd_documents, crm_clients, workflow_tasks
get_current_user = None
new_id_func = None
now_iso_func = None
_broadcast_event = None


def init_cq(database, auth_func, id_func, iso_func, broadcast_event_fn=None):
    global db, get_current_user, new_id_func, now_iso_func, _broadcast_event
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func
    _broadcast_event = broadcast_event_fn
    logger.info("CQ module initialized (PostgreSQL)")


def new_id() -> str:
    return new_id_func()


def now_iso() -> str:
    return now_iso_func()


# ══════════════════════════════════════════════════════════════════════════════
#   HARD STOPS — importáveis por outros módulos
#   db param kept for backward-compat but ignored — PG used directly
# ══════════════════════════════════════════════════════════════════════════════

async def cq_verificar_assepsia_manipulacao(_db, tenant_id: str, om_id: str):
    ok = await pg_db.fetch_one(
        "SELECT id FROM cq_checklists WHERE op_id=$1 AND tipo='CK-3' AND status='aprovado' AND tenant_id=$2",
        om_id, tenant_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail={
            "error": "hard_stop_assepsia_manipulacao",
            "message": "Ordem de Manipulação não pode iniciar sem CK-3 (Assépsia) aprovado pelo CQ.",
        })


async def cq_verificar_assepsia_envase(_db, tenant_id: str, op_id: str):
    ok = await pg_db.fetch_one(
        "SELECT id FROM cq_checklists WHERE op_id=$1 AND tipo='CK-4' AND status='aprovado' AND tenant_id=$2",
        op_id, tenant_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail={
            "error": "hard_stop_assepsia_envase",
            "message": "Ordem de Produção não pode iniciar sem CK-4 (Assépsia de Linha) aprovado.",
        })


async def cq_verificar_setup_linha(_db, tenant_id: str, op_id: str):
    ok = await pg_db.fetch_one(
        "SELECT id FROM cq_checklists WHERE op_id=$1 AND tipo='CK-5' AND status='aprovado' AND tenant_id=$2",
        op_id, tenant_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail={
            "error": "hard_stop_setup_linha",
            "message": "Produção não pode iniciar sem CK-5 (Setup/First Article) aprovado.",
        })


async def cq_verificar_lote_aprovado(_db, tenant_id: str, lote_id: str):
    if not lote_id:
        return
    ultimo = await pg_db.fetch_one(
        "SELECT status_novo FROM cq_status_lote WHERE lote_id=$1 AND tenant_id=$2 ORDER BY created_at DESC LIMIT 1",
        lote_id, tenant_id,
    )
    if ultimo and dict(ultimo).get("status_novo") == "reprovado":
        raise HTTPException(status_code=400, detail={
            "error": "hard_stop_lote_reprovado",
            "message": "Lote está REPROVADO — movimentação bloqueada. Registre disposição via RNC.",
        })


async def cq_verificar_liberacao_palete(_db, tenant_id: str, lote_id: str):
    if not lote_id:
        return
    ok = await pg_db.fetch_one(
        "SELECT id FROM cq_checklists WHERE lote_id=$1 AND tipo='CK-7' AND status='aprovado' AND tenant_id=$2",
        lote_id, tenant_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail={
            "error": "hard_stop_liberacao_palete",
            "message": "Palete não pode ser expedido sem CK-7 (Liberação de Palete) aprovado pelo CQ.",
        })


# ── RBAC ──────────────────────────────────────────────────────────────────────
CQ_FULL     = {"admin", "qa", "lider_pd"}
CQ_ANALISTA = {"admin", "qa", "lider_pd", "formulador"}
CQ_READ     = {"admin", "qa", "lider_pd", "formulador", "engenharia_produto", "compras", "sales_ops"}


# ── Numbering ─────────────────────────────────────────────────────────────────
async def _next_ra_number(tenant_id: str) -> str:
    from workflow_engine import next_sequence_pg
    year = datetime.now(timezone.utc).year
    seq = await next_sequence_pg(tenant_id, f"cq_ra_{year}", start=0)
    return f"RA-{year}-{seq:04d}"


async def _next_rnc_number(tenant_id: str) -> str:
    from workflow_engine import next_sequence_pg
    year = datetime.now(timezone.utc).year
    seq = await next_sequence_pg(tenant_id, f"cq_rnc_{year}", start=0)
    return f"RNC-{year}-{seq:04d}"


async def _next_ret_number(tenant_id: str) -> str:
    from workflow_engine import next_sequence_pg
    year = datetime.now(timezone.utc).year
    seq = await next_sequence_pg(tenant_id, f"cq_ret_{year}", start=0)
    return f"RET-{year}-{seq:04d}"


async def _next_ck_number(tenant_id: str, tipo: str) -> str:
    from workflow_engine import next_sequence_pg
    tipo_num = tipo.replace("CK-", "").strip() if tipo.upper().startswith("CK-") else tipo
    year = datetime.now(timezone.utc).year
    seq = await next_sequence_pg(tenant_id, f"cq_ck_{year}", start=0)
    return f"CK-{tipo_num}-{year}-{seq:04d}"


# ── Date helpers ───────────────────────────────────────────────────────────────
def _add_days_iso(iso_date: Optional[str], days: int) -> str:
    if iso_date:
        try:
            base = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            base = datetime.now(timezone.utc)
    else:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=days)).date().isoformat()


def _add_business_days(base: datetime, days: int) -> str:
    result = base
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result.date().isoformat()


# ── Instrumento status helper (used by preencher_item and listar_instrumentos) ─
def _calc_instrumento_status(instr: dict) -> str:
    stored = instr.get("status", "calibrado")
    if stored in ("em_calibracao", "bloqueado"):
        return stored
    proxima = instr.get("proxima_calibracao")
    if proxima:
        today = datetime.now(timezone.utc).date().isoformat()
        if proxima < today:
            return "vencido"
    return stored


# ══════════════════════════════════════════════════════════════════════════════
#   SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class ParametroSchema(BaseModel):
    id: str = ""
    nome: str
    unidade: Optional[str] = None
    metodo: Optional[str] = None
    especificacao_min: Optional[float] = None
    especificacao_max: Optional[float] = None
    resultado: Optional[Any] = None
    conforme: Optional[bool] = None
    observacao: Optional[str] = None


class RACreate(BaseModel):
    lote_id: str
    lote_numero: str
    tipo: str
    item_id: Optional[str] = None
    item_nome: Optional[str] = None
    item_tipo: Optional[str] = None
    fornecedor_id: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    nf_numero: Optional[str] = None
    nf_data: Optional[str] = None
    quantidade_recebida: Optional[float] = None
    unidade: Optional[str] = None
    numero_lote_fornecedor: Optional[str] = None
    data_fabricacao_fornecedor: Optional[str] = None
    data_validade_fornecedor: Optional[str] = None
    parametros: Optional[List[ParametroSchema]] = None


class ParametroResultadoInput(BaseModel):
    id: str
    resultado: Optional[Any] = None
    observacao: Optional[str] = None


class RAParametrosUpdate(BaseModel):
    parametros: List[ParametroResultadoInput]


class AprovarInput(BaseModel):
    decisao: str
    observacoes: Optional[str] = None
    justificativa_concessao: Optional[str] = None
    disposicao_imediata: Optional[str] = None


class RegistrarEnvioCoAInput(BaseModel):
    cliente_id: Optional[str] = None
    cliente_nome: Optional[str] = None
    canal: Optional[str] = None
    observacoes: Optional[str] = None


class ChecklistItemInput(BaseModel):
    id: Optional[str] = None
    secao: Optional[str] = None
    ordem: Optional[int] = None
    descricao: str
    tipo_resposta: str = "snna"
    somente_cq: bool = False
    resposta: Optional[Any] = None
    conforme: Optional[bool] = None
    observacao: Optional[str] = None
    foto_file_ids: Optional[List[str]] = None
    nc_classificacao: Optional[str] = None
    acao_imediata: Optional[str] = None


class ChecklistCreate(BaseModel):
    tipo: str
    nome: Optional[str] = None
    op_id: Optional[str] = None
    op_numero: Optional[str] = None
    lote_id: Optional[str] = None
    linha: Optional[str] = None
    turno: Optional[str] = None
    subtipo_insumo: Optional[str] = None
    horario_previsto_ronda: Optional[str] = None
    ra_id: Optional[str] = None
    itens: Optional[List[ChecklistItemInput]] = None


class ChecklistItemUpdate(BaseModel):
    resposta: Optional[Any] = None
    conforme: Optional[bool] = None
    observacao: Optional[str] = None
    foto_file_ids: Optional[List[str]] = None
    nc_classificacao: Optional[str] = None
    acao_imediata: Optional[str] = None
    instrumento_id: Optional[str] = None


class AprovarChecklistInput(BaseModel):
    decisao: str
    observacoes: Optional[str] = None


class RNCCreate(BaseModel):
    classificacao: str
    origem: str
    descricao: str
    disposicao_imediata: str
    ra_id: Optional[str] = None
    ck_id: Optional[str] = None
    lote_id: Optional[str] = None
    lote_numero: Optional[str] = None
    item_nome: Optional[str] = None
    fornecedor_id: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    quantidade_afetada: Optional[float] = None
    unidade: Optional[str] = None
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = None
    prazo_resolucao: Optional[str] = None


class RNCUpdate(BaseModel):
    classificacao: Optional[str] = None
    descricao: Optional[str] = None
    responsavel_id: Optional[str] = None
    responsavel_nome: Optional[str] = None
    prazo_resolucao: Optional[str] = None
    capa_descricao: Optional[str] = None
    observacao: Optional[str] = None


class RNCEncerrarPayload(BaseModel):
    evidencia_resolucao: str
    com_concessao: bool = False
    autorizacao_concessao: Optional[str] = None
    observacoes: Optional[str] = None


class ComunicarFornecedorInput(BaseModel):
    email_destinatario: Optional[str] = None
    observacoes: Optional[str] = None


class RetencaoCreate(BaseModel):
    tipo: str
    ra_id: Optional[str] = None
    lote_id: Optional[str] = None
    lote_numero: Optional[str] = None
    item_nome: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    quantidade_retida: Optional[float] = None
    unidade: Optional[str] = None
    localizacao_fisica: Optional[str] = None
    data_coleta: Optional[str] = None


class InstrumentoCreate(BaseModel):
    nome: str
    codigo_interno: str
    tipo: str
    localizacao: Optional[str] = None
    frequencia_calibracao_dias: int = 365
    ultima_calibracao: Optional[str] = None
    certificado_file_id: Optional[str] = None


class InstrumentoUpdate(BaseModel):
    nome: Optional[str] = None
    localizacao: Optional[str] = None
    frequencia_calibracao_dias: Optional[int] = None
    status: Optional[str] = None
    certificado_file_id: Optional[str] = None


class RegistrarCalibracaoInput(BaseModel):
    data_calibracao: str
    laboratorio: Optional[str] = None
    certificado_numero: Optional[str] = None
    resultado: str = "aprovado"
    certificado_file_id: Optional[str] = None


LOTE_STATUSES = {
    "quarentena", "em_analise", "aprovado", "reprovado",
    "concessao", "reprocesso", "devolvido", "descartado",
}


# ══════════════════════════════════════════════════════════════════════════════
#   INDEX CREATION — no-op (indexes in 003_cq_fix_schema.sql)
# ══════════════════════════════════════════════════════════════════════════════

async def create_cq_indexes():
    pass


# ══════════════════════════════════════════════════════════════════════════════
#   ROW HELPERS
# ══════════════════════════════════════════════════════════════════════════════

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
#   INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _registrar_status_lote(
    *,
    tenant_id: str,
    lote_id: str,
    lote_numero: str,
    status_anterior: Optional[str],
    status_novo: str,
    motivo: Optional[str],
    user: dict,
    ra_id: Optional[str] = None,
    rnc_id: Optional[str] = None,
) -> dict:
    entry_id = new_id()
    await pg_db.execute(
        """
        INSERT INTO cq_status_lote(
          id, tenant_id, lote_id, lote_numero,
          status_anterior, status_novo, motivo,
          ra_id, rnc_id, alterado_por_id, alterado_por_nome, created_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW())
        """,
        entry_id, tenant_id, lote_id, lote_numero,
        status_anterior, status_novo, motivo,
        ra_id, rnc_id, user["id"], user.get("name", ""),
    )
    return {"id": entry_id, "tenant_id": tenant_id, "lote_id": lote_id,
            "status_anterior": status_anterior, "status_novo": status_novo}


async def _criar_ret_auto(tenant_id: str, ra: dict, user: dict) -> dict:
    numero_ret = await _next_ret_number(tenant_id)
    if ra["tipo"] in ("recepcao_mp", "recepcao_embalagem"):
        tipo_ret = "mp"
        base_date = ra.get("nf_data") or ra.get("created_at")
    else:
        tipo_ret = "produto_acabado"
        base_date = ra.get("data_validade_fornecedor") or ra.get("created_at")

    ret_id = new_id()
    data_limite = _add_days_iso(base_date, 180)
    await pg_db.execute(
        """
        INSERT INTO cq_retencoes(
          id, tenant_id, numero_ret, tipo, ra_id,
          lote_id, lote_numero, item_nome, fornecedor_nome,
          quantidade_retida, unidade, localizacao_fisica,
          data_coleta, data_limite_guarda, status, created_at, updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NULL,$12,$13,'em_guarda',NOW(),NOW())
        """,
        ret_id, tenant_id, numero_ret, tipo_ret, ra["id"],
        ra.get("lote_id"), ra.get("lote_numero"), ra.get("item_nome"),
        ra.get("fornecedor_nome"), ra.get("quantidade_recebida"), ra.get("unidade"),
        now_iso()[:10], data_limite,
    )
    return {"id": ret_id, "numero_ret": numero_ret, "data_limite_guarda": data_limite}


async def _criar_rnc_auto(tenant_id: str, ra: dict, disposicao_imediata: str, user: dict) -> dict:
    numero_rnc = await _next_rnc_number(tenant_id)
    rnc_id = new_id()
    descricao = (
        f"RA {ra['numero_ra']} reprovado — resultado geral não conforme. "
        f"Item: {ra.get('item_nome') or '—'}. Lote: {ra.get('lote_numero') or '—'}."
    )
    await pg_db.execute(
        """
        INSERT INTO cq_rncs(
          id, tenant_id, numero_rnc, classificacao, origem,
          descricao, status, ra_id, lote_id, lote_numero, item_nome,
          fornecedor_id, fornecedor_nome, quantidade_afetada,
          fotos_file_ids, disposicao_imediata,
          responsavel_id, responsavel_nome,
          comunicado_fornecedor_enviado, log_auditoria, created_at, updated_at
        ) VALUES(
          $1,$2,$3,'maior',$4,$5,'aberta',$6,$7,$8,$9,$10,$11,$12,
          '[]',$13,$14,$15,FALSE,'[]',NOW(),NOW()
        )
        """,
        rnc_id, tenant_id, numero_rnc, ra["tipo"],
        descricao, ra["id"], ra.get("lote_id"), ra.get("lote_numero"),
        ra.get("item_nome"), ra.get("fornecedor_id"), ra.get("fornecedor_nome"),
        ra.get("quantidade_recebida"),
        disposicao_imediata, user["id"], user.get("name", ""),
    )
    return {"id": rnc_id, "numero_rnc": numero_rnc, "status": "aberta"}


async def _buscar_parametros_ft(tenant_id: str, item_id: Optional[str]) -> List[dict]:
    """Load quality specs from the latest approved Ficha Técnica (MongoDB — pd_documents not migrated)."""
    if not item_id:
        return []
    docs = await db.pd_documents.find(
        {"tenant_id": tenant_id, "doc_type": "ficha_tecnica",
         "item_id": item_id, "status": "aprovado"},
        {"_id": 0},
    ).sort("created_at", -1).limit(1).to_list(1)
    if not docs:
        return []
    doc = docs[0]
    params: List[dict] = []
    for field_name in ("parametros_in_process", "especificacoes_produto_acabado"):
        specs = doc.get(field_name)
        if not isinstance(specs, dict):
            continue
        for key, val in specs.items():
            if not isinstance(val, dict):
                continue
            params.append({
                "id": new_id(), "nome": val.get("label") or key,
                "unidade": val.get("unidade"), "metodo": val.get("metodo"),
                "especificacao_min": val.get("min") or val.get("especificacao_min"),
                "especificacao_max": val.get("max") or val.get("especificacao_max"),
                "resultado": None, "conforme": None, "observacao": None,
            })
        if params:
            break
    return params


# ══════════════════════════════════════════════════════════════════════════════
#   COA HTML / PDF
# ══════════════════════════════════════════════════════════════════════════════

def _build_coa_html(ra: dict, tipo_coa: str, empresa: str) -> str:
    watermark_css = (
        "body::before { content:'DOCUMENTO CONTROLADO — não copiar'; position:fixed; "
        "top:42%; left:-18%; width:140%; text-align:center; font-size:2.2em; "
        "font-weight:bold; color:rgba(180,0,0,0.10); transform:rotate(-32deg); "
        "z-index:0; pointer-events:none; white-space:nowrap; }"
        if tipo_coa == "comercial" else ""
    )
    status_labels = {"aprovado": "APROVADO", "concessao": "APROVADO POR CONCESSÃO", "reprovado": "REPROVADO"}
    status_label = status_labels.get(ra.get("status", ""), (ra.get("status") or "").upper())
    resultado_geral = ra.get("resultado_geral") or "—"
    rg_color = "#1a7f37" if resultado_geral == "conforme" else "#cf222e" if resultado_geral == "nao_conforme" else "#666"
    rg_label = "CONFORME" if resultado_geral == "conforme" else "NÃO CONFORME" if resultado_geral == "nao_conforme" else resultado_geral.upper()
    params_rows = ""
    for p in ra.get("parametros", []):
        resultado = p.get("resultado")
        conforme = p.get("conforme")
        cell_color, badge = ("#1a7f37", "✓ CONFORME") if conforme is True else ("#cf222e", "✗ NÃO CONFORME") if conforme is False else ("#555", "—")
        mn, mx = p.get("especificacao_min"), p.get("especificacao_max")
        spec_range = f"{mn} – {mx}" if mn is not None and mx is not None else (f"≥ {mn}" if mn is not None else (f"≤ {mx}" if mx is not None else "—"))
        params_rows += (
            f"<tr><td>{p.get('nome') or '—'}</td><td>{p.get('unidade') or '—'}</td>"
            f"<td>{p.get('metodo') or '—'}</td><td>{spec_range}</td>"
            f"<td style='color:{cell_color};font-weight:600;'>{resultado if resultado is not None else '—'}</td>"
            f"<td style='color:{cell_color};font-weight:600;'>{badge}</td></tr>"
        )
    if not params_rows:
        params_rows = '<tr><td colspan="6" style="text-align:center;color:#999;padding:16px;">Nenhum parâmetro registrado</td></tr>'
    data_analise = ra.get("data_analise") or (ra.get("updated_at") or "")[:10]
    gerado_em = now_iso()[:10]
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/>
<title>CoA — {ra.get('numero_ra','')}</title>
<style>{watermark_css}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:Arial,Helvetica,sans-serif;font-size:11pt;color:#1c1c1e;padding:36px 40px;position:relative;z-index:1;}}
h1{{font-size:20pt;text-align:center;margin-bottom:2px;}}
.subtitle{{text-align:center;font-size:10pt;color:#555;margin-bottom:28px;}}
.section{{margin-bottom:22px;}}.section h2{{font-size:10pt;text-transform:uppercase;letter-spacing:.6px;background:#f3f4f6;border-left:4px solid #2563eb;padding:4px 10px;margin-bottom:10px;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;}}
.field-label{{font-size:8.5pt;color:#666;margin-bottom:1px;}}.field-value{{font-size:10pt;font-weight:600;}}
table{{width:100%;border-collapse:collapse;font-size:9.5pt;}}
thead th{{background:#2563eb;color:#fff;padding:6px 8px;text-align:left;font-size:9pt;}}
tbody td{{border-bottom:1px solid #e5e7eb;padding:5px 8px;vertical-align:middle;}}
tbody tr:nth-child(even) td{{background:#f9fafb;}}
.resultado-geral{{margin-top:16px;padding:12px;border:2px solid {rg_color};border-radius:6px;font-size:13pt;font-weight:bold;text-align:center;color:{rg_color};}}
.footer{{margin-top:48px;display:flex;justify-content:space-between;align-items:flex-end;}}
.assinatura{{width:220px;text-align:center;border-top:1px solid #555;padding-top:4px;font-size:9pt;}}
.meta{{font-size:8pt;color:#aaa;text-align:right;line-height:1.6;}}</style></head>
<body><h1>{empresa}</h1>
<div class="subtitle">Certificado de Análise (CoA) — {tipo_coa.upper()}</div>
<div class="section"><h2>Identificação do Registro</h2><div class="grid">
<div><div class="field-label">Número RA</div><div class="field-value">{ra.get('numero_ra') or '—'}</div></div>
<div><div class="field-label">Status</div><div class="field-value">{status_label}</div></div>
<div><div class="field-label">Tipo de Análise</div><div class="field-value">{(ra.get('tipo') or '').replace('_',' ').title()}</div></div>
<div><div class="field-label">Data da Análise</div><div class="field-value">{data_analise or '—'}</div></div>
<div><div class="field-label">Analista</div><div class="field-value">{ra.get('analista_nome') or '—'}</div></div>
</div></div>
<div class="section"><h2>Identificação do Item / Lote</h2><div class="grid">
<div><div class="field-label">Item</div><div class="field-value">{ra.get('item_nome') or '—'}</div></div>
<div><div class="field-label">Lote Interno</div><div class="field-value">{ra.get('lote_numero') or '—'}</div></div>
<div><div class="field-label">Fornecedor</div><div class="field-value">{ra.get('fornecedor_nome') or '—'}</div></div>
<div><div class="field-label">Lote Fornecedor</div><div class="field-value">{ra.get('numero_lote_fornecedor') or '—'}</div></div>
<div><div class="field-label">Qtd. Recebida</div><div class="field-value">{ra.get('quantidade_recebida') or '—'} {ra.get('unidade') or ''}</div></div>
<div><div class="field-label">NF</div><div class="field-value">{ra.get('nf_numero') or '—'}</div></div>
<div><div class="field-label">Fabricação (Forn.)</div><div class="field-value">{ra.get('data_fabricacao_fornecedor') or '—'}</div></div>
<div><div class="field-label">Validade (Forn.)</div><div class="field-value">{ra.get('data_validade_fornecedor') or '—'}</div></div>
</div></div>
<div class="section"><h2>Resultados de Análise</h2>
<table><thead><tr><th>Parâmetro</th><th>Unidade</th><th>Método</th><th>Especificação</th><th>Resultado</th><th>Conformidade</th></tr></thead>
<tbody>{params_rows}</tbody></table>
<div class="resultado-geral">Resultado Geral: {rg_label}</div></div>
<div class="footer">
<div><div class="assinatura"><div style="height:44px;"></div>{ra.get('analista_nome') or 'Analista CQ'}</div>
<div class="field-label" style="margin-top:4px;">Analista Responsável</div></div>
<div class="meta">Gerado em {gerado_em}<br/>{ra.get('numero_ra') or ''} — uso interno controlado</div>
</div></body></html>"""


def _html_to_pdf(html: str) -> Optional[bytes]:
    try:
        from weasyprint import HTML as _WP  # type: ignore
        return _WP(string=html).write_pdf()
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("WeasyPrint failed: %s", exc)
        return None


def _build_comunicado_fornecedor_html(rnc: dict, empresa: str) -> str:
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"/>
<title>Comunicado NC — {rnc.get('numero_rnc','')}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:Arial,Helvetica,sans-serif;font-size:11pt;color:#1c1c1e;padding:36px 40px;}}
h1{{font-size:18pt;text-align:center;margin-bottom:4px;}}
.subtitle{{text-align:center;color:#555;font-size:10pt;margin-bottom:28px;}}
.section{{margin-bottom:20px;}}.section h2{{font-size:10pt;text-transform:uppercase;background:#fef2f2;border-left:4px solid #dc2626;padding:4px 10px;margin-bottom:10px;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;}}
.fl{{font-size:8.5pt;color:#666;}}.fv{{font-size:10pt;font-weight:600;}}
.box{{border-radius:4px;padding:10px;font-size:10pt;margin-top:4px;}}
.desc{{background:#fef9ec;border:1px solid #fcd34d;}}.disp{{background:#fff1f2;border:1px solid #fca5a5;color:#dc2626;font-weight:bold;}}
.capa{{background:#f0fdf4;border:1px solid #86efac;}}
.foot{{margin-top:48px;border-top:1px solid #e5e7eb;padding-top:12px;font-size:8pt;color:#888;}}
</style></head>
<body><h1>{empresa}</h1>
<div class="subtitle">COMUNICADO DE NÃO CONFORMIDADE AO FORNECEDOR</div>
<div class="section"><h2>Identificação da RNC</h2><div class="grid">
<div><div class="fl">Número RNC</div><div class="fv">{rnc.get('numero_rnc') or '—'}</div></div>
<div><div class="fl">Classificação</div><div class="fv">{(rnc.get('classificacao') or '').upper()}</div></div>
<div><div class="fl">Data de Abertura</div><div class="fv">{(rnc.get('created_at') or '')[:10]}</div></div>
<div><div class="fl">Prazo para CAPA</div><div class="fv">{rnc.get('prazo_resolucao') or '—'}</div></div>
</div></div>
<div class="section"><h2>Material e Fornecedor</h2><div class="grid">
<div><div class="fl">Material / Item</div><div class="fv">{rnc.get('item_nome') or '—'}</div></div>
<div><div class="fl">Fornecedor</div><div class="fv">{rnc.get('fornecedor_nome') or '—'}</div></div>
<div><div class="fl">Lote</div><div class="fv">{rnc.get('lote_numero') or '—'}</div></div>
<div><div class="fl">Quantidade Afetada</div><div class="fv">{rnc.get('quantidade_afetada') or '—'} {rnc.get('unidade') or ''}</div></div>
</div></div>
<div class="section"><h2>Descrição da Não Conformidade</h2><div class="box desc">{rnc.get('descricao') or '—'}</div></div>
<div class="section"><h2>Disposição Imediata</h2><div class="box disp">{(rnc.get('disposicao_imediata') or '—').upper().replace('_',' ')}</div></div>
<div class="section"><h2>Ação Corretiva e Preventiva (CAPA) Solicitada</h2>
<div class="box capa">Solicitamos que V.Sa. encaminhe no prazo indicado um plano de ação contendo:<br/>
1. Análise de causa raiz (5 Porquês ou Ishikawa);<br/>2. Ações corretivas implementadas;<br/>
3. Ações preventivas para evitar recorrência;<br/>4. Evidências objetivas da implementação.</div></div>
<div class="foot">Comunicado gerado em {now_iso()[:10]} — {empresa} — Sistema de Gestão da Qualidade</div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
#   CHECKLIST TEMPLATES (pure Python — no DB access)
# ══════════════════════════════════════════════════════════════════════════════

def _ck_tipo_to_origem(tipo: str) -> str:
    return {
        "CK-1": "recepcao_embalagem", "CK-2": "recepcao_mp",
        "CK-3": "processo_manipulacao", "CK-4": "processo_envase",
        "CK-5": "processo_envase", "CK-6": "processo_envase",
        "CK-7": "produto_acabado", "CK-8": "processo_manipulacao",
    }.get(tipo, "processo_manipulacao")


def _make_item(secao, ordem, descricao, tipo_resposta="snna", somente_cq=False) -> dict:
    return {
        "id": new_id(), "secao": secao, "ordem": ordem, "descricao": descricao,
        "tipo_resposta": tipo_resposta, "somente_cq": somente_cq,
        "resposta": None, "conforme": None, "observacao": None,
        "foto_file_ids": [], "nc_classificacao": None, "acao_imediata": None,
    }


_CK1_SECAO4_LABEL = {
    "frasco": "4. Frascos", "tampa": "4. Tampas", "rotulo": "4. Rótulos",
    "valvula": "4. Válvulas", "cartucho": "4. Cartuchos", "caixa": "4. Caixas Master",
}
_CK1_SECAO4_ITENS: Dict[str, List[tuple]] = {
    "frasco":   [("Volume nominal confere com a especificação","snna"),("Cor/transparência confere com o padrão aprovado","snna"),("Pescoço e encaixe compatíveis com a tampa especificada","snna"),("Ausência de defeitos visuais (bolhas, manchas, deformidades)","snna"),("Peso do frasco vazio dentro da tolerância (g)","numerico")],
    "tampa":    [("Rosca compatível com o frasco especificado","snna"),("Torque de abertura dentro do especificado (N.m)","numerico"),("Ausência de defeitos visuais (rebarbas, rachaduras, cor incorreta)","snna"),("Vedação adequada — sem vazamento ao pressionar","snna")],
    "rotulo":   [("Texto INCI correto conforme aprovação ANVISA","snna"),("CNPJ e razão social da empresa corretos","snna"),("Código de barras legível (verificado com scanner)","snna"),("Cor e layout conformes com a arte aprovada","snna"),("Informações obrigatórias presentes (lote, validade, modo de uso)","snna")],
    "valvula":  [("Pressão de spray conforme especificação","snna"),("Vedação sem vazamento ao pressionar","snna"),("Compatibilidade dimensional com o frasco","snna")],
    "cartucho": [("Dimensões conferem com o frasco especificado","snna"),("Impressão correta (layout, textos, cores)","snna"),("Sem amassados, rasgos ou danos na impressão","snna"),("Janela de visualização posicionada corretamente (se aplicável)","snna")],
    "caixa":    [("Dimensões corretas para unitização no palete","snna"),("Impressão e identificação corretas","snna"),("Resistência e integridade da caixa adequadas","snna"),("Quantidade por caixa confere com a especificação","snna")],
}


def _itens_ck1(subtipo: str) -> List[dict]:
    itens = [
        _make_item("1. Documentação",  1, "NF presente e conferida com o pedido de compra"),
        _make_item("1. Documentação",  2, "Dados da NF corretos (CNPJ, produto, quantidade)"),
        _make_item("1. Documentação",  3, "Laudo ou CoA do fornecedor disponível"),
        _make_item("2. Transporte",    4, "Veículo em condições adequadas de higiene"),
        _make_item("2. Transporte",    5, "Embalagens sem danos causados pelo transporte"),
        _make_item("2. Transporte",    6, "Sem odores ou evidências de contaminação"),
        _make_item("3. AQL NBR 5426",  7, "Plano de amostragem definido conforme NBR 5426"),
        _make_item("3. AQL NBR 5426",  8, "Tamanho de amostra confere com o plano"),
        _make_item("3. AQL NBR 5426",  9, "Critério de aceitação aplicado corretamente"),
        _make_item("3. AQL NBR 5426", 10, "Resultado AQL: lote aceito?"),
    ]
    secao4 = _CK1_SECAO4_LABEL.get(subtipo, f"4. {subtipo.capitalize()}")
    for i, (desc, tipo_r) in enumerate(_CK1_SECAO4_ITENS.get(subtipo, []), start=11):
        itens.append(_make_item(secao4, i, desc, tipo_resposta=tipo_r))
    return itens


def _itens_ck2() -> List[dict]:
    return [
        _make_item("1. Recebimento", 1, "Nota Fiscal presente e conferida"),
        _make_item("1. Recebimento", 2, "Laudo do fornecedor (CoA) disponível"),
        _make_item("1. Recebimento", 3, "FISPQ (ficha de segurança) disponível"),
        _make_item("1. Recebimento", 4, "Embalagem íntegra — sem vazamentos ou danos"),
        _make_item("1. Recebimento", 5, "Identificação do produto visível e correta"),
        _make_item("1. Recebimento", 6, "Dentro do prazo de validade do fornecedor"),
        _make_item("1. Recebimento", 7, "Quantidade recebida confere com o pedido"),
        _make_item("1. Recebimento", 8, "Contraprova coletada e devidamente identificada"),
    ]


def _itens_ck3() -> List[dict]:
    return [
        _make_item("1. Higienização dos Tachos", 1, "Tacho lavado com água quente e detergente neutro"),
        _make_item("1. Higienização dos Tachos", 2, "Tacho enxaguado com água purificada"),
        _make_item("1. Higienização dos Tachos", 3, "Tacho sanitizado com álcool 70°"),
        _make_item("1. Higienização dos Tachos", 4, "Tacho seco — sem resíduos de umidade"),
        _make_item("2. Utensílios e Área",        5, "Utensílios (espátulas, batedores) higienizados"),
        _make_item("2. Utensílios e Área",        6, "Balança verificada e zerada"),
        _make_item("2. Utensílios e Área",        7, "Bancada e área de manipulação limpas e desinfetadas"),
        _make_item("2. Utensílios e Área",        8, "Sem materiais ou resíduos de outros produtos na área"),
        _make_item("3. Aprovação CQ",             9, "CQ verificou e aprova as condições para iniciar a manipulação?", somente_cq=True),
    ]


def _itens_ck4() -> List[dict]:
    return [
        _make_item("1. Limpeza de Equipamentos",  1, "Esteira de envase limpa e desinfetada"),
        _make_item("1. Limpeza de Equipamentos",  2, "Bico dosador limpo e sem resíduos do produto anterior"),
        _make_item("1. Limpeza de Equipamentos",  3, "Tampadora limpa e regulada"),
        _make_item("1. Limpeza de Equipamentos",  4, "Rotuladora limpa e sem resíduos de cola/rótulos anteriores"),
        _make_item("2. Calibração e Ferramentas", 5, "Dosadora calibrada e zerada para o produto"),
        _make_item("2. Calibração e Ferramentas", 6, "Torquímetro disponível e com calibração vigente"),
        _make_item("3. Aprovação CQ",             7, "CQ aprova as condições de higiene e setup para iniciar o envase?", somente_cq=True),
    ]


def _itens_ck5() -> List[dict]:
    return [
        _make_item("1. Setup",                1,  "OP afixada na linha e conferida pelo operador"),
        _make_item("1. Setup",                2,  "Produto e número de lote corretos conforme OP"),
        _make_item("1. Setup",                3,  "Frasco correto conforme OP e especificação"),
        _make_item("1. Setup",                4,  "Tampa correta conforme OP e especificação"),
        _make_item("1. Setup",                5,  "Rótulo correto conforme OP e arte aprovada"),
        _make_item("1. Setup",                6,  "Quantidade de insumos separados confere com a OP"),
        _make_item("2. Medições — Amostra 1", 7,  "Amostra 1 — Peso (g)", "numerico"),
        _make_item("2. Medições — Amostra 1", 8,  "Amostra 1 — Volume (mL)", "numerico"),
        _make_item("2. Medições — Amostra 1", 9,  "Amostra 1 — Torque (N.m)", "numerico"),
        _make_item("3. Medições — Amostra 2", 10, "Amostra 2 — Peso (g)", "numerico"),
        _make_item("3. Medições — Amostra 2", 11, "Amostra 2 — Volume (mL)", "numerico"),
        _make_item("3. Medições — Amostra 2", 12, "Amostra 2 — Torque (N.m)", "numerico"),
        _make_item("4. Medições — Amostra 3", 13, "Amostra 3 — Peso (g)", "numerico"),
        _make_item("4. Medições — Amostra 3", 14, "Amostra 3 — Volume (mL)", "numerico"),
        _make_item("4. Medições — Amostra 3", 15, "Amostra 3 — Torque (N.m)", "numerico"),
        _make_item("5. Aprovação CQ",         16, "CQ aprova o First Article e libera a linha para produção?", somente_cq=True),
    ]


def _itens_ck6() -> List[dict]:
    return [
        _make_item("1. Identificação",       1,  "Linha identificada conforme OP (produto e lote visíveis)"),
        _make_item("1. Identificação",       2,  "Horário da ronda registrado conforme cronograma"),
        _make_item("2. Operadores / EPI",    3,  "Operadores com EPIs completos (touca, jaleco, luvas)"),
        _make_item("2. Operadores / EPI",    4,  "Não há operadores não autorizados na linha"),
        _make_item("3. Área",                5,  "Área limpa e organizada"),
        _make_item("3. Área",                6,  "Sem resíduos de produto ou material no chão"),
        _make_item("3. Área",                7,  "Corredores desobstruídos e acesso à emergência livre"),
        _make_item("4. Documentos",          8,  "OP visível, atualizada e preenchida corretamente"),
        _make_item("4. Documentos",          9,  "CK-5 (First Article) aprovado e afixado na linha"),
        _make_item("5. Insumos",             10, "Insumos identificados com número de lote correto"),
        _make_item("5. Insumos",             11, "Sem insumos com prazo vencido na linha"),
        _make_item("5. Insumos",             12, "Sem mistura de lotes sem autorização"),
        _make_item("6. Produto em Processo", 13, "Peso do produto (g)", "numerico"),
        _make_item("6. Produto em Processo", 14, "Volume do produto (mL)", "numerico"),
        _make_item("6. Produto em Processo", 15, "Torque de fechamento (N.m)", "numerico"),
        _make_item("6. Produto em Processo", 16, "Aspecto visual conforme padrão aprovado"),
        _make_item("7. Equipamentos",        17, "Dosadora operando sem falhas ou alarmes"),
        _make_item("7. Equipamentos",        18, "Tampadora operando corretamente"),
        _make_item("7. Equipamentos",        19, "Rotuladora operando corretamente"),
        _make_item("8. NCs Observadas",      20, "Há não conformidades identificadas nesta ronda?"),
    ]


def _itens_ck7() -> List[dict]:
    return [
        _make_item("1. Documentação",               1, "RA de produto acabado aprovado para este lote", somente_cq=True),
        _make_item("1. Documentação",               2, "Palete corretamente identificado (produto, lote, quantidade)"),
        _make_item("1. Documentação",               3, "Etiqueta 'APROVADO CQ' afixada visivelmente no palete"),
        _make_item("2. Integridade das Embalagens", 4, "Embalagens sem amassados, rasgos ou danos visíveis"),
        _make_item("2. Integridade das Embalagens", 5, "Rótulos aplicados corretamente e sem defeitos"),
        _make_item("2. Integridade das Embalagens", 6, "Caixas master fechadas e identificadas"),
        _make_item("3. Conformidade da Unitização", 7, "Quantidade de unidades confere com a OP"),
        _make_item("3. Conformidade da Unitização", 8, "Palete filmado corretamente para transporte"),
        _make_item("3. Conformidade da Unitização", 9, "Separação conforme pedido de expedição"),
    ]


def _itens_ck8() -> List[dict]:
    return [
        _make_item("1. Higiene das Instalações",     1,  "Instalações sanitárias limpas e abastecidas"),
        _make_item("1. Higiene das Instalações",     2,  "Vestiários organizados e limpos"),
        _make_item("1. Higiene das Instalações",     3,  "Almoxarifado organizado — sem materiais fora do lugar"),
        _make_item("2. Condições Ambientais",        4,  "Temperatura sala de envase (°C)", "numerico"),
        _make_item("2. Condições Ambientais",        5,  "Umidade relativa sala de envase (%)", "numerico"),
        _make_item("2. Condições Ambientais",        6,  "Temperatura sala de fragrâncias (°C)", "numerico"),
        _make_item("3. Controle de Pragas",          7,  "Sem evidências de pragas (insetos, roedores)"),
        _make_item("3. Controle de Pragas",          8,  "Iscas e armadilhas presentes e íntegras"),
        _make_item("4. Verificação de Instrumentos", 9,  "Balança verificada com peso padrão — dentro da tolerância"),
        _make_item("4. Verificação de Instrumentos", 10, "pHmetro calibrado (buffers 4,00 e 7,00)"),
        _make_item("4. Verificação de Instrumentos", 11, "Termohigrômetro calibrado e funcionando"),
    ]


def _build_itens_para_checklist(tipo: str, subtipo_insumo: Optional[str] = None) -> List[dict]:
    builders = {
        "CK-2": _itens_ck2, "CK-3": _itens_ck3, "CK-4": _itens_ck4,
        "CK-5": _itens_ck5, "CK-6": _itens_ck6, "CK-7": _itens_ck7, "CK-8": _itens_ck8,
    }
    if tipo == "CK-1":
        return _itens_ck1(subtipo_insumo or "frasco")
    fn = builders.get(tipo)
    return fn() if fn else []


def _calc_ck5_averages(itens: List[dict]) -> dict:
    pesos, volumes, torques = [], [], []
    for item in itens:
        if item.get("tipo_resposta") != "numerico" or item.get("resposta") is None:
            continue
        try:
            val = float(item["resposta"])
        except (TypeError, ValueError):
            continue
        lower = (item.get("descricao") or "").lower()
        if "peso" in lower:
            pesos.append(val)
        elif "volume" in lower:
            volumes.append(val)
        elif "torque" in lower:
            torques.append(val)
    result: dict = {}
    if pesos:
        result["media_peso_g"] = round(sum(pesos) / len(pesos), 3)
    if volumes:
        result["media_volume_ml"] = round(sum(volumes) / len(volumes), 3)
    if torques:
        result["media_torque_nm"] = round(sum(torques) / len(torques), 3)
    return result


TIPOS_CK_VALIDOS = {"CK-1", "CK-2", "CK-3", "CK-4", "CK-5", "CK-6", "CK-7", "CK-8"}
TIPOS_CK_REQUEREM_OP = {"CK-3", "CK-4", "CK-5", "CK-6", "CK-7", "CK-8"}
SUBTIPOS_CK1_VALIDOS = {"frasco", "tampa", "valvula", "rotulo", "cartucho", "caixa"}


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 1 — REGISTRO DE ANÁLISE (RA)
# ══════════════════════════════════════════════════════════════════════════════

@cq_router.post("/registros-analise", status_code=201)
async def criar_ra(data: RACreate, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_ANALISTA)
    tenant_id = user["tenant_id"]

    if not data.lote_id:
        raise HTTPException(status_code=400, detail="lote_id é obrigatório")

    TIPOS_VALIDOS = {"recepcao_mp", "recepcao_embalagem", "bulk_piloto", "produto_acabado"}
    if data.tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"tipo inválido. Valores aceitos: {sorted(TIPOS_VALIDOS)}")

    if data.parametros is not None:
        parametros = [
            {"id": p.id or new_id(), "nome": p.nome, "unidade": p.unidade,
             "metodo": p.metodo, "especificacao_min": p.especificacao_min,
             "especificacao_max": p.especificacao_max, "resultado": p.resultado,
             "conforme": p.conforme, "observacao": p.observacao}
            for p in data.parametros
        ]
    else:
        parametros = await _buscar_parametros_ft(tenant_id, data.item_id)

    ra_id = new_id()
    numero_ra = await _next_ra_number(tenant_id)

    await pg_db.execute(
        """
        INSERT INTO cq_registros_analise(
          id, tenant_id, numero_ra, tipo, status,
          lote_id, lote_numero, item_id, item_nome, item_tipo,
          fornecedor_id, fornecedor_nome, nf_numero, nf_data,
          quantidade_recebida, unidade, numero_lote_fornecedor,
          data_fabricacao_fornecedor, data_validade_fornecedor,
          parametros, resultado_geral, analista_id, analista_nome,
          fotos_file_ids, coa_gerado, coa_enviado_cliente,
          log_auditoria, created_at, updated_at
        ) VALUES(
          $1,$2,$3,$4,'rascunho',$5,$6,$7,$8,$9,$10,$11,$12,$13,
          $14,$15,$16,$17,$18,$19,NULL,$20,$21,'[]',FALSE,FALSE,'[]',NOW(),NOW()
        )
        """,
        ra_id, tenant_id, numero_ra, data.tipo,
        data.lote_id, data.lote_numero, data.item_id, data.item_nome, data.item_tipo,
        data.fornecedor_id, data.fornecedor_nome, data.nf_numero, data.nf_data,
        data.quantidade_recebida, data.unidade, data.numero_lote_fornecedor,
        data.data_fabricacao_fornecedor, data.data_validade_fornecedor,
        parametros, user["id"], user.get("name", ""),
    )

    await _registrar_status_lote(
        tenant_id=tenant_id, lote_id=data.lote_id, lote_numero=data.lote_numero,
        status_anterior=None, status_novo="em_analise",
        motivo=f"RA {numero_ra} criado", user=user, ra_id=ra_id,
    )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="create", entity_type="cq_ra", entity_id=ra_id)

    if _broadcast_event:
        await _broadcast_event(tenant_id, "cq_ra_created", {"ra_id": ra_id, "numero_ra": numero_ra})

    _RECEPCAO_TO_CQ = {
        "recepcao_mp": ("CQ-01", "Analisar recebimento MP/Fragrância"),
        "recepcao_embalagem": ("CQ-02", "Inspecionar recebimento de Embalagem"),
    }
    if data.tipo in _RECEPCAO_TO_CQ:
        cq_code, cq_titulo = _RECEPCAO_TO_CQ[data.tipo]
        await create_workflow_task(
            tenant_id=tenant_id, entity_type="cq_ra", entity_id=ra_id,
            title=f"{cq_code} {cq_titulo} — {numero_ra}",
            description=f"RA {numero_ra} criado. Item: {data.item_nome or '—'}. Fornecedor: {data.fornecedor_nome or '—'}.",
            category="qa", blocking=False, due_in_days=1, created_by=user,
        )

    row = await pg_db.fetch_one("SELECT * FROM cq_registros_analise WHERE id=$1", ra_id)
    return _row(row)


@cq_router.get("/registros-analise")
async def listar_ras(
    request: Request,
    status: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    lote_id: Optional[str] = Query(None),
    fornecedor_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    tenant_id = user["tenant_id"]

    conds = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    for val, col in [(status, "status"), (tipo, "tipo"), (lote_id, "lote_id"), (fornecedor_id, "fornecedor_id")]:
        if val:
            conds.append(f"{col}=${idx}"); params.append(val); idx += 1

    where = " AND ".join(conds)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM cq_registros_analise WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM cq_registros_analise WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"items": _rows(rows), "total": total, "limit": limit, "offset": offset}


@cq_router.get("/registros-analise/{ra_id}")
async def detalhe_ra(ra_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    row = await pg_db.fetch_one(
        "SELECT * FROM cq_registros_analise WHERE id=$1 AND tenant_id=$2",
        ra_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Registro de Análise não encontrado")
    return _row(row)


@cq_router.put("/registros-analise/{ra_id}/parametros")
async def salvar_parametros(ra_id: str, data: RAParametrosUpdate, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_ANALISTA)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_registros_analise WHERE id=$1 AND tenant_id=$2", ra_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Registro de Análise não encontrado")
    ra = _row(row)
    if ra["status"] in ("aprovado", "reprovado", "concessao"):
        raise HTTPException(status_code=409, detail=f"RA já encerrado com status '{ra['status']}'")

    resultado_map = {p.id: p for p in data.parametros}
    updated_params = []
    for p in ra.get("parametros", []):
        upd = resultado_map.get(p["id"])
        if upd is None:
            updated_params.append(p); continue
        resultado = upd.resultado
        conforme: Optional[bool] = None
        if resultado is not None:
            try:
                resultado_num = float(resultado)
                mn = p.get("especificacao_min")
                mx = p.get("especificacao_max")
                if mn is not None and mx is not None:
                    conforme = mn <= resultado_num <= mx
                elif mn is not None:
                    conforme = resultado_num >= mn
                elif mx is not None:
                    conforme = resultado_num <= mx
            except (TypeError, ValueError):
                pass
        updated_params.append({**p, "resultado": resultado, "conforme": conforme,
                                "observacao": upd.observacao if upd.observacao is not None else p.get("observacao")})

    checked = [p for p in updated_params if p.get("conforme") is not None]
    resultado_geral: Optional[str] = ("conforme" if all(p["conforme"] for p in checked) else "nao_conforme") if checked else None

    await pg_db.execute(
        """UPDATE cq_registros_analise SET parametros=$1, resultado_geral=$2,
           status='em_analise', data_analise=$3, updated_at=NOW()
           WHERE id=$4 AND tenant_id=$5""",
        updated_params, resultado_geral, now_iso()[:10], ra_id, tenant_id,
    )
    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="update_parametros", entity_type="cq_ra", entity_id=ra_id,
                    before={"resultado_geral": ra.get("resultado_geral")},
                    after={"resultado_geral": resultado_geral})

    return _row(await pg_db.fetch_one("SELECT * FROM cq_registros_analise WHERE id=$1", ra_id))


@cq_router.post("/registros-analise/{ra_id}/aprovar")
async def aprovar_ra(ra_id: str, data: AprovarInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_registros_analise WHERE id=$1 AND tenant_id=$2", ra_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Registro de Análise não encontrado")
    ra = _row(row)
    if ra["status"] in ("aprovado", "reprovado", "concessao"):
        raise HTTPException(status_code=409, detail=f"RA já encerrado com status '{ra['status']}'")

    DECISOES_VALIDAS = {"aprovado", "reprovado", "concessao"}
    if data.decisao not in DECISOES_VALIDAS:
        raise HTTPException(status_code=422, detail=f"decisao inválida. Valores aceitos: {sorted(DECISOES_VALIDAS)}")
    if data.decisao == "concessao" and not data.justificativa_concessao:
        raise HTTPException(status_code=422, detail="justificativa_concessao é obrigatória quando decisao='concessao'")
    if data.decisao == "reprovado":
        if not data.disposicao_imediata:
            raise HTTPException(status_code=422, detail="disposicao_imediata é obrigatória quando decisao='reprovado'")
        if data.disposicao_imediata not in {"devolucao", "descarte", "reprocesso", "concessao"}:
            raise HTTPException(status_code=422, detail="disposicao_imediata inválida")

    now = now_iso()
    log_entry: Dict[str, Any] = {
        "campo": "status", "de": ra["status"], "para": data.decisao,
        "usuario_id": user["id"], "usuario_nome": user.get("name", ""), "datetime": now,
    }
    if data.observacoes:
        log_entry["observacoes"] = data.observacoes
    if data.justificativa_concessao:
        log_entry["justificativa_concessao"] = data.justificativa_concessao

    await pg_db.execute(
        "UPDATE cq_registros_analise SET status=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        data.decisao, ra_id, tenant_id,
    )
    await pg_db.execute(
        "UPDATE cq_registros_analise SET log_auditoria = log_auditoria || $1::jsonb WHERE id=$2",
        [log_entry], ra_id,
    )

    lote_status_map = {"aprovado": "aprovado", "reprovado": "reprovado", "concessao": "concessao"}
    await _registrar_status_lote(
        tenant_id=tenant_id, lote_id=ra["lote_id"], lote_numero=ra.get("lote_numero", ""),
        status_anterior="em_analise", status_novo=lote_status_map[data.decisao],
        motivo=data.observacoes or f"Decisão CQ: {data.decisao}", user=user, ra_id=ra_id,
    )

    ret_id: Optional[str] = None
    rnc_id: Optional[str] = None

    if data.decisao in ("aprovado", "concessao"):
        ret = await _criar_ret_auto(tenant_id, ra, user)
        ret_id = ret["id"]
        await pg_db.execute(
            "UPDATE cq_registros_analise SET amostra_retencao_id=$1 WHERE id=$2", ret_id, ra_id,
        )
        coa_client = await db.crm_clients.find_one(
            {"tenant_id": tenant_id, "requer_coa": True}, {"_id": 0, "id": 1, "nome_empresa": 1},
        )
        if coa_client:
            await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_ra", entity_id=ra_id,
                title=f"CQ-12 Enviar CoA — {ra.get('numero_ra')}",
                description=f"CoA do RA {ra.get('numero_ra')} deve ser enviado ao cliente {coa_client.get('nome_empresa','')}.",
                category="qa", blocking=False, due_in_days=2, created_by=user,
            )
    elif data.decisao == "reprovado":
        rnc = await _criar_rnc_auto(tenant_id, ra, data.disposicao_imediata, user)
        rnc_id = rnc["id"]
        await pg_db.execute(
            "UPDATE cq_registros_analise SET rnc_id=$1 WHERE id=$2", rnc_id, ra_id,
        )
        await create_workflow_task(
            tenant_id=tenant_id, entity_type="cq_ra", entity_id=ra_id,
            title=f"CQ-11 Tratar RNC — {rnc['numero_rnc']}",
            description=f"RA {ra.get('numero_ra')} reprovado. RNC {rnc['numero_rnc']} aberta. Disposição: {data.disposicao_imediata}.",
            category="qa", blocking=True, due_in_days=3, created_by=user,
        )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="aprovar", entity_type="cq_ra", entity_id=ra_id,
                    before={"status": ra["status"]},
                    after={"status": data.decisao, "ret_id": ret_id, "rnc_id": rnc_id})
    if _broadcast_event:
        await _broadcast_event(tenant_id, "cq_ra_aprovado",
                               {"ra_id": ra_id, "status": data.decisao, "rnc_id": rnc_id, "ret_id": ret_id})

    return _row(await pg_db.fetch_one("SELECT * FROM cq_registros_analise WHERE id=$1", ra_id))


@cq_router.get("/registros-analise/{ra_id}/coa")
async def gerar_coa(ra_id: str, request: Request, tipo_coa: str = Query("interno")):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_registros_analise WHERE id=$1 AND tenant_id=$2", ra_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Registro de Análise não encontrado")
    ra = _row(row)
    if ra["status"] not in ("aprovado", "concessao"):
        raise HTTPException(status_code=400, detail=f"CoA só pode ser gerado para RA aprovado ou concessao (status atual: '{ra['status']}')")
    if tipo_coa not in ("interno", "comercial"):
        raise HTTPException(status_code=400, detail="tipo_coa deve ser 'interno' ou 'comercial'")

    tenant_row = await pg_db.fetch_one("SELECT nome, name FROM tenants WHERE id=$1", tenant_id)
    empresa = ""
    if tenant_row:
        d = dict(tenant_row)
        empresa = d.get("nome") or d.get("name") or ""
    if not empresa:
        empresa = "Laboratório CQ"

    html_content = _build_coa_html(ra, tipo_coa, empresa)
    await pg_db.execute(
        "UPDATE cq_registros_analise SET coa_gerado=TRUE, updated_at=NOW() WHERE id=$1", ra_id,
    )
    pdf_bytes = _html_to_pdf(html_content)
    if pdf_bytes:
        filename = f"CoA-{ra['numero_ra']}-{tipo_coa}.pdf"
        return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    return HTMLResponse(content=html_content, status_code=200)


@cq_router.post("/registros-analise/{ra_id}/registrar-envio-coa")
async def registrar_envio_coa(ra_id: str, data: RegistrarEnvioCoAInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_ANALISTA)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_registros_analise WHERE id=$1 AND tenant_id=$2", ra_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Registro de Análise não encontrado")
    ra = _row(row)
    if ra["status"] not in ("aprovado", "concessao"):
        raise HTTPException(status_code=400, detail="CoA só pode ser registrado para RA aprovado ou concessao")

    now = now_iso()
    log_entry = {
        "campo": "coa_enviado_cliente", "de": ra.get("coa_enviado_cliente", False), "para": True,
        "usuario_id": user["id"], "usuario_nome": user.get("name", ""), "datetime": now,
        "cliente_id": data.cliente_id, "cliente_nome": data.cliente_nome,
        "canal": data.canal, "observacoes": data.observacoes,
    }
    await pg_db.execute(
        """UPDATE cq_registros_analise SET coa_enviado_cliente=TRUE, coa_enviado_em=$1,
           log_auditoria = log_auditoria || $2::jsonb, updated_at=NOW()
           WHERE id=$3 AND tenant_id=$4""",
        now, [log_entry], ra_id, tenant_id,
    )
    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="registrar_envio_coa", entity_type="cq_ra", entity_id=ra_id,
                    after={"coa_enviado_cliente": True, "coa_enviado_em": now})
    return _row(await pg_db.fetch_one("SELECT * FROM cq_registros_analise WHERE id=$1", ra_id))


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 2 — CHECKLISTS
# ══════════════════════════════════════════════════════════════════════════════

@cq_router.post("/checklists", status_code=201)
async def criar_checklist(data: ChecklistCreate, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_ANALISTA)
    tenant_id = user["tenant_id"]

    tipo_upper = (data.tipo or "").upper()
    if tipo_upper not in TIPOS_CK_VALIDOS:
        raise HTTPException(status_code=422, detail=f"tipo inválido. Valores aceitos: {sorted(TIPOS_CK_VALIDOS)}")
    if tipo_upper in TIPOS_CK_REQUEREM_OP and not data.op_id:
        raise HTTPException(status_code=400, detail=f"{tipo_upper} exige op_id")
    if tipo_upper == "CK-1":
        if not data.subtipo_insumo:
            raise HTTPException(status_code=400, detail="CK-1 exige subtipo_insumo")
        if data.subtipo_insumo not in SUBTIPOS_CK1_VALIDOS:
            raise HTTPException(status_code=422, detail=f"subtipo_insumo inválido. Valores aceitos: {sorted(SUBTIPOS_CK1_VALIDOS)}")

    if tipo_upper == "CK-7":
        if not data.lote_id:
            raise HTTPException(status_code=400, detail="CK-7 exige lote_id")
        ra_pa = await pg_db.fetch_one(
            "SELECT id FROM cq_registros_analise WHERE tenant_id=$1 AND tipo='produto_acabado' AND status IN ('aprovado','concessao') AND lote_id=$2",
            tenant_id, data.lote_id,
        )
        if not ra_pa:
            raise HTTPException(status_code=400, detail={
                "error": "prerequisito_nao_atendido",
                "message": "RA de Produto Acabado aprovado é pré-requisito para CK-7",
            })

    ck_id = new_id()
    numero_ck = await _next_ck_number(tenant_id, tipo_upper)
    itens = _build_itens_para_checklist(tipo_upper, data.subtipo_insumo)

    await pg_db.execute(
        """
        INSERT INTO cq_checklists(
          id, tenant_id, numero_ck, tipo, nome, status,
          op_id, op_numero, lote_id, linha, turno,
          subtipo_insumo, horario_previsto_ronda, ra_id,
          itens, ncs_identificadas, rncs_geradas,
          preenchido_por_id, preenchido_por_nome,
          aprovado_por_id, aprovado_por_nome, aprovado_em,
          ck5_medias, log_auditoria, created_at, updated_at
        ) VALUES(
          $1,$2,$3,$4,$5,'em_preenchimento',$6,$7,$8,$9,$10,
          $11,$12,$13,$14,0,'[]',$15,$16,NULL,NULL,NULL,'{}','[]',NOW(),NOW()
        )
        """,
        ck_id, tenant_id, numero_ck, tipo_upper, data.nome,
        data.op_id, data.op_numero, data.lote_id, data.linha, data.turno,
        data.subtipo_insumo, data.horario_previsto_ronda, data.ra_id,
        itens, user["id"], user.get("name", ""),
    )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="create", entity_type="cq_checklist", entity_id=ck_id)
    if _broadcast_event:
        await _broadcast_event(tenant_id, "cq_checklist_created", {"ck_id": ck_id, "numero_ck": numero_ck})

    return _row(await pg_db.fetch_one("SELECT * FROM cq_checklists WHERE id=$1", ck_id))


@cq_router.get("/checklists")
async def listar_checklists(
    request: Request,
    tipo: Optional[str] = Query(None),
    op_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    lote_id: Optional[str] = Query(None),
    ra_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    tenant_id = user["tenant_id"]

    conds = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    for val, col in [(tipo, "tipo"), (op_id, "op_id"), (status, "status"),
                     (lote_id, "lote_id"), (ra_id, "ra_id")]:
        if val:
            v = val.upper() if col == "tipo" else val
            conds.append(f"{col}=${idx}"); params.append(v); idx += 1

    where = " AND ".join(conds)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM cq_checklists WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM cq_checklists WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"items": _rows(rows), "total": total, "limit": limit, "offset": offset}


@cq_router.get("/checklists/{ck_id}")
async def detalhe_checklist(ck_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    row = await pg_db.fetch_one(
        "SELECT * FROM cq_checklists WHERE id=$1 AND tenant_id=$2", ck_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Checklist não encontrado")
    return _row(row)


@cq_router.put("/checklists/{ck_id}/itens/{item_id}")
async def preencher_item(ck_id: str, item_id: str, data: ChecklistItemUpdate, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_ANALISTA)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_checklists WHERE id=$1 AND tenant_id=$2", ck_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Checklist não encontrado")
    ck = _row(row)
    if ck["status"] in ("aprovado", "reprovado"):
        raise HTTPException(status_code=409, detail=f"Checklist já encerrado com status '{ck['status']}'")

    item_atual = next((i for i in ck.get("itens", []) if i["id"] == item_id), None)
    if not item_atual:
        raise HTTPException(status_code=404, detail="Item não encontrado neste checklist")
    if item_atual.get("somente_cq") and not has_role(user, CQ_FULL):
        raise HTTPException(status_code=403, detail="Este item é de preenchimento exclusivo do CQ")

    resposta = data.resposta
    conforme = data.conforme
    if item_atual.get("tipo_resposta") == "snna" and resposta is not None:
        conforme = resposta in ("S", "NA")

    # Fetch-modify-write para atualizar item no array JSONB
    itens = list(ck["itens"])
    for i, item in enumerate(itens):
        if item["id"] == item_id:
            updated = dict(item)
            if data.resposta is not None:
                updated["resposta"] = resposta
                updated["conforme"] = conforme
            if data.observacao is not None:
                updated["observacao"] = data.observacao
            if data.nc_classificacao is not None:
                updated["nc_classificacao"] = data.nc_classificacao
            if data.acao_imediata is not None:
                updated["acao_imediata"] = data.acao_imediata
            if data.foto_file_ids is not None:
                updated["foto_file_ids"] = data.foto_file_ids
            itens[i] = updated
            break

    await pg_db.execute(
        "UPDATE cq_checklists SET itens=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
        itens, ck_id, tenant_id,
    )

    # CK-5: recalcular médias após item numérico
    if ck["tipo"] == "CK-5" and item_atual.get("tipo_resposta") == "numerico":
        avgs = _calc_ck5_averages(itens)
        if avgs:
            await pg_db.execute(
                "UPDATE cq_checklists SET ck5_medias=$1 WHERE id=$2 AND tenant_id=$3",
                avgs, ck_id, tenant_id,
            )

    # Auto-criar RNC quando resposta=N e nc_classificacao=critica
    if resposta == "N" and data.nc_classificacao == "critica":
        numero_rnc = await _next_rnc_number(tenant_id)
        rnc_id_auto = new_id()
        descricao_rnc = (
            f"NC crítica identificada no {ck['numero_ck']} — "
            f"seção '{item_atual.get('secao','—')}': \"{item_atual['descricao']}\"."
        )
        await pg_db.execute(
            """INSERT INTO cq_rncs(
               id, tenant_id, numero_rnc, classificacao, origem, descricao, status,
               ck_id, lote_id, fotos_file_ids, disposicao_imediata,
               responsavel_id, responsavel_nome,
               comunicado_fornecedor_enviado, log_auditoria, created_at, updated_at
            ) VALUES($1,$2,$3,'critica',$4,$5,'aberta',$6,$7,$8,'descarte',$9,$10,FALSE,'[]',NOW(),NOW())""",
            rnc_id_auto, tenant_id, numero_rnc, _ck_tipo_to_origem(ck["tipo"]),
            descricao_rnc, ck_id, ck.get("lote_id"),
            data.foto_file_ids or [],
            user["id"], user.get("name", ""),
        )
        await pg_db.execute(
            """UPDATE cq_checklists SET
               ncs_identificadas = ncs_identificadas + 1,
               rncs_geradas = rncs_geradas || $1::jsonb
               WHERE id=$2 AND tenant_id=$3""",
            [rnc_id_auto], ck_id, tenant_id,
        )

        # CK-6: alerta se mesma seção teve NC crítica na ronda anterior
        if ck["tipo"] == "CK-6" and ck.get("op_id"):
            secao_atual = item_atual.get("secao", "")
            prev_rows = await pg_db.fetch_all(
                """SELECT itens FROM cq_checklists
                   WHERE tenant_id=$1 AND tipo='CK-6' AND op_id=$2 AND id!=$3
                   ORDER BY created_at DESC LIMIT 1""",
                tenant_id, ck["op_id"], ck_id,
            )
            if prev_rows:
                prev_itens = prev_rows[0]["itens"] or []
                prev_nc = any(
                    i.get("resposta") == "N" and i.get("nc_classificacao") == "critica"
                    and i.get("secao") == secao_atual
                    for i in prev_itens
                )
                if prev_nc:
                    await create_workflow_task(
                        tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_id,
                        title=f"CQ-13 ALERTA PARADA DE LINHA — {ck['numero_ck']}",
                        description=f"NC crítica repetida na seção '{secao_atual}' em duas rondas consecutivas (OP {ck.get('op_numero') or ck.get('op_id') or '—'}).",
                        category="qa", blocking=True, due_in_days=0, created_by=user,
                    )

    # Instrument calibration alert
    if data.instrumento_id:
        instr_row = await pg_db.fetch_one(
            "SELECT * FROM cq_instrumentos WHERE id=$1 AND tenant_id=$2",
            data.instrumento_id, tenant_id,
        )
        if instr_row:
            instr_check = _row(instr_row)
            if _calc_instrumento_status(instr_check) in ("vencido", "bloqueado"):
                alerta = "[ALERTA: instrumento com calibração vencida]"
                new_obs = f"{alerta} {data.observacao or ''}".strip()
                # Update observacao on the specific item
                itens_upd = list((await pg_db.fetch_one("SELECT itens FROM cq_checklists WHERE id=$1", ck_id))["itens"] or [])
                for i, item in enumerate(itens_upd):
                    if item["id"] == item_id:
                        itens_upd[i] = {**item, "observacao": new_obs}
                        break
                log_alerta = {
                    "tipo": "instrumento_alerta", "instrumento_id": data.instrumento_id,
                    "instrumento_nome": instr_check.get("nome"), "alerta": alerta,
                    "usuario_id": user["id"], "usuario_nome": user.get("name", ""),
                    "datetime": now_iso(),
                }
                await pg_db.execute(
                    "UPDATE cq_checklists SET itens=$1, log_auditoria = log_auditoria || $2::jsonb WHERE id=$3",
                    itens_upd, [log_alerta], ck_id,
                )

    # CQ-03/04: notificar CQ quando todos os itens de operador estiverem preenchidos
    if ck["tipo"] in ("CK-3", "CK-4"):
        ck_fresh_row = await pg_db.fetch_one("SELECT itens FROM cq_checklists WHERE id=$1", ck_id)
        itens_fresh = ck_fresh_row["itens"] or []
        itens_op = [i for i in itens_fresh if not i.get("somente_cq")]
        if itens_op and all(i.get("resposta") is not None for i in itens_op):
            cq_code = "CQ-03" if ck["tipo"] == "CK-3" else "CQ-04"
            cq_titulo = "Liberar assépsia de manipulação" if ck["tipo"] == "CK-3" else "Liberar assépsia de linha"
            exists_task = await db.workflow_tasks.find_one(
                {"tenant_id": tenant_id, "entity_id": ck_id,
                 "title": {"$regex": f"^{cq_code}"}, "status": "pendente"},
                {"_id": 0, "id": 1},
            )
            if not exists_task:
                await create_workflow_task(
                    tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_id,
                    title=f"{cq_code} {cq_titulo} — {ck['numero_ck']}",
                    description=f"Todos os itens do operador no {ck['numero_ck']} foram preenchidos. CQ deve verificar e aprovar.",
                    category="qa", blocking=True, due_in_days=0, created_by=user,
                )

    return _row(await pg_db.fetch_one("SELECT * FROM cq_checklists WHERE id=$1", ck_id))


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 3 — APROVAR CHECKLIST
# ══════════════════════════════════════════════════════════════════════════════

@cq_router.post("/checklists/{ck_id}/aprovar")
async def aprovar_checklist(ck_id: str, data: AprovarChecklistInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_checklists WHERE id=$1 AND tenant_id=$2", ck_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Checklist não encontrado")
    ck = _row(row)
    if ck["status"] in ("aprovado", "reprovado"):
        raise HTTPException(status_code=409, detail=f"Checklist já encerrado com status '{ck['status']}'")
    if data.decisao not in ("aprovado", "reprovado"):
        raise HTTPException(status_code=422, detail="decisao deve ser 'aprovado' ou 'reprovado'")

    now = now_iso()
    log_entry = {
        "campo": "status", "de": ck["status"], "para": data.decisao,
        "usuario_id": user["id"], "usuario_nome": user.get("name", ""),
        "datetime": now, "observacoes": data.observacoes,
    }
    await pg_db.execute(
        """UPDATE cq_checklists SET status=$1,
           aprovado_por_id=$2, aprovado_por_nome=$3, aprovado_em=$4,
           log_auditoria = log_auditoria || $5::jsonb, updated_at=NOW()
           WHERE id=$6 AND tenant_id=$7""",
        data.decisao, user["id"], user.get("name", ""), now,
        [log_entry], ck_id, tenant_id,
    )

    tipo = ck["tipo"]
    op_ref = ck.get("op_numero") or ck.get("op_id") or "—"

    if data.decisao == "aprovado":
        if tipo == "CK-3":
            await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_id,
                title=f"CK-3 Aprovado — Iniciar Manipulação (OP {op_ref})",
                description=f"Assépsia de manipulação {ck['numero_ck']} aprovada pelo CQ. Linha liberada.",
                category="operacional", blocking=False, due_in_days=0, created_by=user,
            )
        elif tipo == "CK-4":
            await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_id,
                title=f"CK-4 Aprovado — Iniciar Envase (OP {op_ref})",
                description=f"Assépsia de envase {ck['numero_ck']} aprovada pelo CQ. Linha liberada.",
                category="operacional", blocking=False, due_in_days=0, created_by=user,
            )
            await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_id,
                title=f"CQ-05 Realizar setup / First Article — OP {op_ref}",
                description=f"Linha liberada ({ck['numero_ck']}). Realizar CK-5 antes de iniciar produção em série.",
                category="qa", blocking=True, due_in_days=0, created_by=user,
            )
        elif tipo == "CK-5":
            prazo_ronda = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
            await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_id,
                title=f"CQ-06 Primeira Ronda de Linha — OP {op_ref}",
                description=f"First Article {ck['numero_ck']} aprovado. Realizar primeira ronda CK-6 até {prazo_ronda[:16].replace('T',' ')} UTC.",
                category="qa", blocking=False, due_in_days=0, created_by=user,
                metadata={"prazo_primeira_ronda_iso": prazo_ronda},
            )
        elif tipo == "CK-7":
            await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_id,
                title=f"CK-7 Aprovado — Liberar Palete para Expedição (OP {op_ref})",
                description=f"Palete inspecionado e aprovado pelo CQ ({ck['numero_ck']}). Expedição autorizada.",
                category="operacional", blocking=False, due_in_days=0, created_by=user,
            )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="aprovar", entity_type="cq_checklist", entity_id=ck_id,
                    before={"status": ck["status"]}, after={"status": data.decisao})
    if _broadcast_event:
        await _broadcast_event(tenant_id, "cq_checklist_aprovado", {"ck_id": ck_id, "status": data.decisao})

    return _row(await pg_db.fetch_one("SELECT * FROM cq_checklists WHERE id=$1", ck_id))


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 4 — RNCs
# ══════════════════════════════════════════════════════════════════════════════

@cq_router.get("/rncs")
async def listar_rncs(
    request: Request,
    status: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    fornecedor_id: Optional[str] = Query(None),
    classificacao: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    tenant_id = user["tenant_id"]

    conds = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    for val, col in [(status, "status"), (origem, "origem"),
                     (fornecedor_id, "fornecedor_id"), (classificacao, "classificacao")]:
        if val:
            conds.append(f"{col}=${idx}"); params.append(val); idx += 1

    where = " AND ".join(conds)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM cq_rncs WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM cq_rncs WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"items": _rows(rows), "total": total, "limit": limit, "offset": offset}


@cq_router.get("/rncs/{rnc_id}")
async def detalhe_rnc(rnc_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    row = await pg_db.fetch_one(
        "SELECT * FROM cq_rncs WHERE id=$1 AND tenant_id=$2", rnc_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="RNC não encontrada")
    return _row(row)


@cq_router.put("/rncs/{rnc_id}")
async def atualizar_rnc(rnc_id: str, data: RNCUpdate, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_ANALISTA)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_rncs WHERE id=$1 AND tenant_id=$2", rnc_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="RNC não encontrada")
    rnc = _row(row)
    if rnc["status"] in ("encerrada", "encerrada_concessao"):
        raise HTTPException(status_code=400, detail=f"RNC encerrada com status '{rnc['status']}' — não pode ser editada")

    payload = data.model_dump(exclude_none=True)
    sets = ["updated_at=NOW()"]
    params: list = []
    idx = 1
    for field in ("classificacao", "descricao", "responsavel_id", "responsavel_nome",
                  "prazo_resolucao", "capa_descricao"):
        if field in payload:
            sets.append(f"{field}=${idx}"); params.append(payload[field]); idx += 1

    # Auto-transição para em_investigacao
    responsavel_id_final = payload.get("responsavel_id") or rnc.get("responsavel_id")
    prazo_final = payload.get("prazo_resolucao") or rnc.get("prazo_resolucao")
    if responsavel_id_final and prazo_final and rnc["status"] == "aberta":
        sets.append(f"status=${idx}"); params.append("em_investigacao"); idx += 1

    params += [tenant_id, rnc_id]
    await pg_db.execute(
        f"UPDATE cq_rncs SET {', '.join(sets)} WHERE tenant_id=${idx} AND id=${idx+1}",
        *params,
    )

    if data.observacao:
        log_entry = {
            "campo": "observacao", "de": None, "para": data.observacao,
            "usuario_id": user["id"], "usuario_nome": user.get("name", ""), "datetime": now_iso(),
        }
        await pg_db.execute(
            "UPDATE cq_rncs SET log_auditoria = log_auditoria || $1::jsonb WHERE id=$2 AND tenant_id=$3",
            [log_entry], rnc_id, tenant_id,
        )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="update", entity_type="cq_rnc", entity_id=rnc_id,
                    before={k: rnc.get(k) for k in payload if k != "observacao"},
                    after=payload)
    return _row(await pg_db.fetch_one("SELECT * FROM cq_rncs WHERE id=$1", rnc_id))


@cq_router.post("/rncs/{rnc_id}/encerrar")
async def encerrar_rnc(rnc_id: str, data: RNCEncerrarPayload, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_rncs WHERE id=$1 AND tenant_id=$2", rnc_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="RNC não encontrada")
    rnc = _row(row)
    if rnc["status"] in ("encerrada", "encerrada_concessao"):
        raise HTTPException(status_code=409, detail=f"RNC já encerrada com status '{rnc['status']}'")
    if not data.evidencia_resolucao or not data.evidencia_resolucao.strip():
        raise HTTPException(status_code=422, detail="evidencia_resolucao é obrigatória")
    if data.com_concessao and not data.autorizacao_concessao:
        raise HTTPException(status_code=422, detail="autorizacao_concessao é obrigatória quando com_concessao=true")

    status_final = "encerrada_concessao" if data.com_concessao else "encerrada"
    now = now_iso()
    log_entry: Dict[str, Any] = {
        "campo": "status", "de": rnc["status"], "para": status_final,
        "usuario_id": user["id"], "usuario_nome": user.get("name", ""),
        "datetime": now, "observacoes": data.observacoes,
    }

    extra_set = ", autorizacao_concessao=$6" if data.autorizacao_concessao else ""
    extra_params = [data.autorizacao_concessao] if data.autorizacao_concessao else []
    await pg_db.execute(
        f"""UPDATE cq_rncs SET
            status=$1, evidencia_resolucao=$2, encerrado_por_id=$3, encerrado_em=$4,
            log_auditoria = log_auditoria || $5::jsonb{extra_set}, updated_at=NOW()
            WHERE id=${6 + len(extra_params)} AND tenant_id=${7 + len(extra_params)}""",
        status_final, data.evidencia_resolucao, user["id"], now,
        [log_entry], *extra_params, rnc_id, tenant_id,
    )

    # Threshold: ≥3 RNCs do mesmo fornecedor em 90 dias
    if rnc.get("fornecedor_id"):
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        count_90d = await pg_db.fetch_val(
            "SELECT COUNT(*) FROM cq_rncs WHERE tenant_id=$1 AND fornecedor_id=$2 AND created_at >= $3",
            tenant_id, rnc["fornecedor_id"], ninety_days_ago,
        )
        if (count_90d or 0) >= 3:
            await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_rnc", entity_id=rnc_id,
                title=f"ALERTA — Fornecedor com {count_90d} RNCs em 90 dias",
                description=f"Fornecedor '{rnc.get('fornecedor_nome') or rnc.get('fornecedor_id')}' acumula {count_90d} RNCs nos últimos 90 dias. Revisar homologação.",
                category="compras", blocking=False, due_in_days=5, created_by=user,
            )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="encerrar", entity_type="cq_rnc", entity_id=rnc_id,
                    before={"status": rnc["status"]}, after={"status": status_final})
    if _broadcast_event:
        await _broadcast_event(tenant_id, "cq_rnc_encerrada", {"rnc_id": rnc_id, "status": status_final})
    return _row(await pg_db.fetch_one("SELECT * FROM cq_rncs WHERE id=$1", rnc_id))


@cq_router.post("/rncs/{rnc_id}/comunicar-fornecedor")
async def comunicar_fornecedor(rnc_id: str, data: ComunicarFornecedorInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_rncs WHERE id=$1 AND tenant_id=$2", rnc_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="RNC não encontrada")
    rnc = _row(row)
    if rnc["status"] in ("encerrada", "encerrada_concessao"):
        raise HTTPException(status_code=400, detail="Não é possível comunicar fornecedor em RNC encerrada")
    if rnc.get("origem") not in {"recepcao_mp", "recepcao_embalagem"}:
        raise HTTPException(status_code=400, detail="Comunicado ao fornecedor só é aplicável para RNCs de recepcao_mp ou recepcao_embalagem")

    tenant_row = await pg_db.fetch_one("SELECT nome, name FROM tenants WHERE id=$1", tenant_id)
    empresa = ""
    if tenant_row:
        d = dict(tenant_row)
        empresa = d.get("nome") or d.get("name") or ""
    if not empresa:
        empresa = "Laboratório CQ"

    now = now_iso()
    log_entry = {
        "campo": "comunicado_fornecedor_enviado", "de": False, "para": True,
        "usuario_id": user["id"], "usuario_nome": user.get("name", ""),
        "datetime": now, "email_destinatario": data.email_destinatario,
        "observacoes": data.observacoes,
    }
    await pg_db.execute(
        """UPDATE cq_rncs SET
           comunicado_fornecedor_enviado=TRUE, comunicado_enviado_em=$1,
           status='aguardando_fornecedor',
           log_auditoria = log_auditoria || $2::jsonb, updated_at=NOW()
           WHERE id=$3 AND tenant_id=$4""",
        now, [log_entry], rnc_id, tenant_id,
    )
    rnc_updated = _row(await pg_db.fetch_one("SELECT * FROM cq_rncs WHERE id=$1", rnc_id))
    html_content = _build_comunicado_fornecedor_html(rnc_updated, empresa)

    prazo_cq14 = _add_business_days(datetime.now(timezone.utc), 3)
    await create_workflow_task(
        tenant_id=tenant_id, entity_type="cq_rnc", entity_id=rnc_id,
        title=f"CQ-14 Acompanhar resposta do fornecedor — {rnc_updated.get('numero_rnc')}",
        description=f"Comunicado enviado ao fornecedor '{rnc.get('fornecedor_nome') or '—'}'. Aguardar resposta CAPA até {prazo_cq14}.",
        category="qa", blocking=False, due_in_days=5, created_by=user,
        metadata={"prazo_capa_iso": prazo_cq14, "email_destinatario": data.email_destinatario},
    )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="comunicar_fornecedor", entity_type="cq_rnc", entity_id=rnc_id,
                    after={"status": "aguardando_fornecedor", "comunicado_enviado_em": now})

    pdf_bytes = _html_to_pdf(html_content)
    if pdf_bytes:
        filename = f"Comunicado-NC-{rnc_updated.get('numero_rnc', rnc_id)}.pdf"
        return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    return HTMLResponse(content=html_content, status_code=200)


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 5 — RETENÇÕES
# ══════════════════════════════════════════════════════════════════════════════

@cq_router.get("/retencoes")
async def listar_retencoes(
    request: Request,
    status: Optional[str] = Query(None),
    ra_id: Optional[str] = Query(None),
    lote_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    tenant_id = user["tenant_id"]

    conds = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    for val, col in [(status, "status"), (ra_id, "ra_id"), (lote_id, "lote_id")]:
        if val:
            conds.append(f"{col}=${idx}"); params.append(val); idx += 1

    where = " AND ".join(conds)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM cq_retencoes WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM cq_retencoes WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    return {"items": _rows(rows), "total": total, "limit": limit, "offset": offset}


@cq_router.get("/retencoes/{ret_id}")
async def detalhe_retencao(ret_id: str, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    row = await pg_db.fetch_one(
        "SELECT * FROM cq_retencoes WHERE id=$1 AND tenant_id=$2", ret_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Amostra de retenção não encontrada")
    return _row(row)


# ══════════════════════════════════════════════════════════════════════════════
#   405 GUARDS — imutabilidade das coleções CQ
# ══════════════════════════════════════════════════════════════════════════════

_IMUTAVEL_MSG = "Documentos CQ são imutáveis. Exclusão não é permitida em nenhuma coleção CQ."


@cq_router.delete("/registros-analise/{ra_id}", status_code=405)
async def delete_ra_blocked(ra_id: str):
    raise HTTPException(status_code=405, detail=_IMUTAVEL_MSG)


@cq_router.delete("/checklists/{ck_id}", status_code=405)
async def delete_ck_blocked(ck_id: str):
    raise HTTPException(status_code=405, detail=_IMUTAVEL_MSG)


@cq_router.delete("/rncs/{rnc_id}", status_code=405)
async def delete_rnc_blocked(rnc_id: str):
    raise HTTPException(status_code=405, detail=_IMUTAVEL_MSG)


@cq_router.delete("/retencoes/{ret_id}", status_code=405)
async def delete_ret_blocked(ret_id: str):
    raise HTTPException(status_code=405, detail=_IMUTAVEL_MSG)


@cq_router.delete("/instrumentos/{instr_id}", status_code=405)
async def delete_instr_blocked(instr_id: str):
    raise HTTPException(status_code=405, detail=_IMUTAVEL_MSG)


@cq_router.delete("/status-lote/{entry_id}", status_code=405)
async def delete_status_lote_blocked(entry_id: str):
    raise HTTPException(status_code=405, detail=_IMUTAVEL_MSG)


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 6 — SCHEDULER TICK
# ══════════════════════════════════════════════════════════════════════════════

@cq_router.get("/scheduler/tick")
async def scheduler_tick(request: Request):
    """Trigger manual para verificações CQ baseadas em tempo (CQ-09/10/13/14)."""
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.date().isoformat()
    created: List[dict] = []

    # CQ-09: CK-8 de higiene/ambiente ainda não criado hoje
    ck8_hoje = await pg_db.fetch_one(
        "SELECT id FROM cq_checklists WHERE tenant_id=$1 AND tipo='CK-8' AND created_at >= $2::timestamptz",
        tenant_id, today_str,
    )
    if not ck8_hoje:
        exists_cq09 = await db.workflow_tasks.find_one(
            {"tenant_id": tenant_id, "title": {"$regex": "^CQ-09"},
             "created_at": {"$gte": today_str}},
            {"_id": 0, "id": 1},
        )
        if not exists_cq09:
            t = await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_turno",
                entity_id=f"ck8_{today_str}",
                title=f"CQ-09 CK-8 Higiene/Ambiente/Calibração — {today_str}",
                description=f"CK-8 ainda não realizado hoje ({today_str}). Executar antes de qualquer CK-5 ou CK-6 do turno.",
                category="qa", blocking=True, due_in_days=0, created_by=user,
            )
            created.append({"tipo": "CQ-09", "date": today_str, "task_id": t.get("id")})

    # CQ-10: retenções vencendo em ≤30 dias
    window_30d = (now_dt + timedelta(days=30)).date().isoformat()
    ret_rows = await pg_db.fetch_all(
        "SELECT * FROM cq_retencoes WHERE tenant_id=$1 AND status='em_guarda' AND data_limite_guarda <= $2",
        tenant_id, window_30d,
    )
    for ret_row in ret_rows:
        ret = _row(ret_row)
        existing = await db.workflow_tasks.find_one(
            {"tenant_id": tenant_id, "entity_id": ret["id"], "title": {"$regex": "^CQ-10"}},
            {"_id": 0, "id": 1},
        )
        if not existing:
            t = await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_retencao", entity_id=ret["id"],
                title=f"CQ-10 Amostra de retenção vencendo — {ret.get('numero_ret')}",
                description=f"Amostra {ret.get('numero_ret')} vence em {ret.get('data_limite_guarda')}. Item: {ret.get('item_nome') or '—'}.",
                category="qa", blocking=False, due_in_days=30, created_by=user,
            )
            created.append({"tipo": "CQ-10", "ret_id": ret["id"], "task_id": t.get("id")})

    # CQ-13: tarefa CQ-06 vencida há >30 min e ainda pendente (workflow_tasks = MongoDB)
    thirty_min_ago = (now_dt - timedelta(minutes=30)).isoformat()
    async for ck6_task in db.workflow_tasks.find(
        {"tenant_id": tenant_id, "title": {"$regex": "^CQ-06"},
         "status": "pendente", "due_date": {"$lt": thirty_min_ago}},
        {"_id": 0},
    ):
        ck_eid = ck6_task.get("entity_id", "")
        exists_cq13 = await db.workflow_tasks.find_one(
            {"tenant_id": tenant_id, "entity_id": ck_eid, "title": {"$regex": "^CQ-13"}},
            {"_id": 0, "id": 1},
        )
        if not exists_cq13:
            t = await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_checklist", entity_id=ck_eid,
                title="CQ-13 Ronda atrasada >30min — escalonamento supervisor",
                description=f"Tarefa '{ck6_task.get('title')}' está pendente há mais de 30 minutos. Supervisor deve verificar a linha.",
                category="qa", blocking=True, due_in_days=0, created_by=user,
                metadata={"cq06_task_id": ck6_task.get("id")},
            )
            created.append({"tipo": "CQ-13", "entity_id": ck_eid, "task_id": t.get("id")})

    # CQ-14: RNC aguardando resposta do fornecedor há >3 dias
    three_days_ago = (now_dt - timedelta(days=3)).isoformat()
    rnc_rows = await pg_db.fetch_all(
        "SELECT * FROM cq_rncs WHERE tenant_id=$1 AND status='aguardando_fornecedor' AND comunicado_enviado_em < $2",
        tenant_id, three_days_ago,
    )
    for rnc_row in rnc_rows:
        rnc = _row(rnc_row)
        exists_cq14 = await db.workflow_tasks.find_one(
            {"tenant_id": tenant_id, "entity_id": rnc["id"],
             "title": {"$regex": "^CQ-14"}, "status": "pendente"},
            {"_id": 0, "id": 1},
        )
        if not exists_cq14:
            t = await create_workflow_task(
                tenant_id=tenant_id, entity_type="cq_rnc", entity_id=rnc["id"],
                title=f"CQ-14 Fornecedor sem resposta à RNC — {rnc.get('numero_rnc')}",
                description=f"RNC {rnc.get('numero_rnc')} aguarda resposta de '{rnc.get('fornecedor_nome') or '—'}' há >3 dias.",
                category="qa", blocking=False, due_in_days=3, created_by=user,
            )
            created.append({"tipo": "CQ-14", "rnc_id": rnc["id"], "task_id": t.get("id")})

    return {"tick_at": now_dt.isoformat(), "tarefas_criadas": len(created), "detalhe": created}


# ══════════════════════════════════════════════════════════════════════════════
#   PASSO 7 — INSTRUMENTOS DE CALIBRAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

@cq_router.get("/instrumentos")
async def listar_instrumentos(
    request: Request,
    tipo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    user = await get_current_user(request)
    require_roles(user, CQ_READ)
    tenant_id = user["tenant_id"]

    conds = ["tenant_id=$1"]
    params: list = [tenant_id]
    idx = 2
    if tipo:
        conds.append(f"tipo=${idx}"); params.append(tipo); idx += 1

    where = " AND ".join(conds)
    total = await pg_db.fetch_val(f"SELECT COUNT(*) FROM cq_instrumentos WHERE {where}", *params)
    rows = await pg_db.fetch_all(
        f"SELECT * FROM cq_instrumentos WHERE {where} ORDER BY nome LIMIT ${idx} OFFSET ${idx+1}",
        *params, limit, offset,
    )
    items = _rows(rows)

    # Recalcular status real-time e sincronizar se estiver desatualizado
    for instr in items:
        status_real = _calc_instrumento_status(instr)
        if status_real != instr.get("status"):
            instr["status"] = status_real
            await pg_db.execute(
                "UPDATE cq_instrumentos SET status=$1, updated_at=NOW() WHERE id=$2 AND tenant_id=$3",
                status_real, instr["id"], tenant_id,
            )

    if status:
        items = [i for i in items if i.get("status") == status]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@cq_router.post("/instrumentos", status_code=201)
async def criar_instrumento(data: InstrumentoCreate, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    dup = await pg_db.fetch_one(
        "SELECT id FROM cq_instrumentos WHERE tenant_id=$1 AND codigo_interno=$2",
        tenant_id, data.codigo_interno,
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"Código interno '{data.codigo_interno}' já está em uso")

    TIPOS_VALIDOS_INSTR = {"phmetro", "balanca", "torquimetro", "densimetro", "termohigrometro"}
    if data.tipo not in TIPOS_VALIDOS_INSTR:
        raise HTTPException(status_code=422, detail=f"tipo inválido. Valores aceitos: {sorted(TIPOS_VALIDOS_INSTR)}")

    proxima_calibracao = None
    if data.ultima_calibracao:
        proxima_calibracao = _add_days_iso(data.ultima_calibracao, data.frequencia_calibracao_dias + 1)

    status_inicial = "calibrado"
    if proxima_calibracao:
        today = datetime.now(timezone.utc).date().isoformat()
        if proxima_calibracao < today:
            status_inicial = "vencido"

    instr_id = new_id()
    await pg_db.execute(
        """INSERT INTO cq_instrumentos(
           id, tenant_id, nome, codigo_interno, tipo, localizacao,
           frequencia_calibracao_dias, ultima_calibracao, proxima_calibracao,
           status, certificado_file_id, historico_calibracoes, created_at, updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'[]',NOW(),NOW())""",
        instr_id, tenant_id, data.nome, data.codigo_interno, data.tipo,
        data.localizacao, data.frequencia_calibracao_dias,
        data.ultima_calibracao, proxima_calibracao,
        status_inicial, data.certificado_file_id,
    )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="create", entity_type="cq_instrumento", entity_id=instr_id)
    return _row(await pg_db.fetch_one("SELECT * FROM cq_instrumentos WHERE id=$1", instr_id))


@cq_router.put("/instrumentos/{instr_id}")
async def atualizar_instrumento(instr_id: str, data: InstrumentoUpdate, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_instrumentos WHERE id=$1 AND tenant_id=$2", instr_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Instrumento não encontrado")

    sets = ["updated_at=NOW()"]
    params: list = []
    idx = 1
    for field in ("nome", "localizacao", "frequencia_calibracao_dias", "status", "certificado_file_id"):
        val = getattr(data, field, None)
        if val is not None:
            sets.append(f"{field}=${idx}"); params.append(val); idx += 1

    params += [tenant_id, instr_id]
    await pg_db.execute(
        f"UPDATE cq_instrumentos SET {', '.join(sets)} WHERE tenant_id=${idx} AND id=${idx+1}",
        *params,
    )

    instr_before = _row(row)
    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="update", entity_type="cq_instrumento", entity_id=instr_id,
                    before={f: instr_before.get(f) for f in ("nome", "localizacao", "status")},
                    after=data.model_dump(exclude_none=True))
    return _row(await pg_db.fetch_one("SELECT * FROM cq_instrumentos WHERE id=$1", instr_id))


@cq_router.post("/instrumentos/{instr_id}/registrar-calibracao")
async def registrar_calibracao(instr_id: str, data: RegistrarCalibracaoInput, request: Request):
    user = await get_current_user(request)
    require_roles(user, CQ_FULL)
    tenant_id = user["tenant_id"]

    row = await pg_db.fetch_one(
        "SELECT * FROM cq_instrumentos WHERE id=$1 AND tenant_id=$2", instr_id, tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Instrumento não encontrado")
    instr = _row(row)

    if data.resultado not in ("aprovado", "reprovado"):
        raise HTTPException(status_code=422, detail="resultado deve ser 'aprovado' ou 'reprovado'")

    proxima_calibracao = _add_days_iso(data.data_calibracao, instr["frequencia_calibracao_dias"] + 1)
    novo_status = "calibrado" if data.resultado == "aprovado" else "bloqueado"

    historico_entry = {
        "data": data.data_calibracao, "laboratorio": data.laboratorio,
        "certificado_numero": data.certificado_numero, "resultado": data.resultado,
        "certificado_file_id": data.certificado_file_id,
        "registrado_por_id": user["id"], "registrado_por_nome": user.get("name", ""),
        "created_at": now_iso(),
    }

    cert_set = ", certificado_file_id=$6" if data.certificado_file_id else ""
    cert_params = [data.certificado_file_id] if data.certificado_file_id else []
    await pg_db.execute(
        f"""UPDATE cq_instrumentos SET
            ultima_calibracao=$1, proxima_calibracao=$2, status=$3,
            historico_calibracoes = historico_calibracoes || $4::jsonb{cert_set},
            updated_at=NOW()
            WHERE id=${5 + len(cert_params)} AND tenant_id=${6 + len(cert_params)}""",
        data.data_calibracao, proxima_calibracao, novo_status,
        [historico_entry], *cert_params, instr_id, tenant_id,
    )

    await audit_log(tenant_id=tenant_id, user_id=user["id"], user_name=user.get("name", ""),
                    action="registrar_calibracao", entity_type="cq_instrumento", entity_id=instr_id,
                    before={"status": instr.get("status"), "ultima_calibracao": instr.get("ultima_calibracao")},
                    after={"status": novo_status, "proxima_calibracao": proxima_calibracao})

    if _broadcast_event:
        await _broadcast_event(tenant_id, "cq_instrumento_calibrado",
                               {"instrumento_id": instr_id, "status": novo_status,
                                "proxima_calibracao": proxima_calibracao})

    return _row(await pg_db.fetch_one("SELECT * FROM cq_instrumentos WHERE id=$1", instr_id))

