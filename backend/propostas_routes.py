"""
propostas_routes.py — R14: Proposta Comercial & Pedido de Fabricação

Coleção: propostas_comerciais  (uma por projeto, upsert)
Endpoints:
  GET    /crm/projects/{id}/proposta
  POST   /crm/projects/{id}/proposta          (criar / atualizar inteiro)
  PATCH  /crm/projects/{id}/proposta          (atualizar parcialmente)
  GET    /crm/projects/{id}/amostras-status   (R18: validação antes de confirmar pedido)
"""

import json
import math
import os
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import database as pg_db

propostas_router = APIRouter(prefix="/api/crm/projects", tags=["propostas"])

_get_current_user = None
_new_id = None
_now_iso = None


def init_propostas(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global _get_current_user, _new_id, _now_iso
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat()
    return d


# ── Schemas ──────────────────────────────────────────────────────────────────

class InsumoItem(BaseModel):
    descricao: str = ""
    qtd: Optional[float] = None
    unidade: str = ""

class PedidoItem(BaseModel):
    codigo_kuryos: str = ""
    codigo_cliente: str = ""
    item: str = ""
    prazo_entrega: str = ""
    qtd: Optional[float] = None
    valor_unitario: Optional[float] = None
    valor_total: Optional[float] = None

class PropostaPayload(BaseModel):
    tipo_produto: str = ""
    variacao_produto: str = ""
    preco_unitario: Optional[float] = None
    insumos_inclusos: List[str] = []
    observacoes_proposta: str = ""
    items_pedido: List[PedidoItem] = []
    condicoes_pagamento: str = ""
    insumos_fabricacao: List[InsumoItem] = []
    rodape_observacoes: str = ""
    status: str = "rascunho"

class PropostaPatch(BaseModel):
    tipo_produto: Optional[str] = None
    variacao_produto: Optional[str] = None
    preco_unitario: Optional[float] = None
    insumos_inclusos: Optional[List[str]] = None
    observacoes_proposta: Optional[str] = None
    items_pedido: Optional[List[PedidoItem]] = None
    condicoes_pagamento: Optional[str] = None
    insumos_fabricacao: Optional[List[InsumoItem]] = None
    rodape_observacoes: Optional[str] = None
    status: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_project(projeto_id: str, tenant_id: str) -> dict:
    proj = _row(await pg_db.fetch_one(
        "SELECT * FROM crm_projects WHERE id=$1 AND tenant_id=$2", projeto_id, tenant_id
    ))
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return proj


# ── Endpoints ─────────────────────────────────────────────────────────────────

@propostas_router.get("/{projeto_id}/proposta")
async def get_proposta(projeto_id: str, request: Request):
    user = await _get_current_user(request)
    await _get_project(projeto_id, user["tenant_id"])
    doc = _row(await pg_db.fetch_one(
        "SELECT * FROM propostas_comerciais WHERE projeto_id=$1 AND tenant_id=$2",
        projeto_id, user["tenant_id"],
    ))
    if not doc:
        return {}
    return doc


@propostas_router.post("/{projeto_id}/proposta")
async def upsert_proposta(projeto_id: str, payload: PropostaPayload, request: Request):
    """Cria ou substitui completamente a proposta do projeto."""
    user = await _get_current_user(request)
    project = await _get_project(projeto_id, user["tenant_id"])

    now = _now_iso()
    existing = _row(await pg_db.fetch_one(
        "SELECT id FROM propostas_comerciais WHERE projeto_id=$1 AND tenant_id=$2",
        projeto_id, user["tenant_id"],
    ))

    items_dict = [item.dict() for item in payload.items_pedido]
    insumos_dict = [i.dict() for i in payload.insumos_fabricacao]

    if existing:
        doc_id = existing["id"]
        await pg_db.execute(
            """UPDATE propostas_comerciais SET
                   tipo_produto=$1, variacao_produto=$2, preco_unitario=$3,
                   insumos_inclusos=$4, observacoes_proposta=$5,
                   items_pedido=$6, condicoes_pagamento=$7,
                   insumos_fabricacao=$8, rodape_observacoes=$9, status=$10,
                   updated_at=$11, updated_by=$12, updated_by_name=$13
               WHERE id=$14""",
            payload.tipo_produto, payload.variacao_produto, payload.preco_unitario,
            payload.insumos_inclusos, payload.observacoes_proposta,
            items_dict, payload.condicoes_pagamento,
            insumos_dict, payload.rodape_observacoes, payload.status,
            now, user["id"], user.get("name", ""),
            doc_id,
        )
    else:
        doc_id = _new_id()
        await pg_db.execute(
            """INSERT INTO propostas_comerciais
               (id, tenant_id, projeto_id, projeto_nome, cliente_id, cliente_nome,
                tipo_produto, variacao_produto, preco_unitario, insumos_inclusos,
                observacoes_proposta, items_pedido, condicoes_pagamento, insumos_fabricacao,
                rodape_observacoes, status, arquivos,
                created_by, created_by_name, created_at, updated_at, updated_by, updated_by_name)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)""",
            doc_id, user["tenant_id"], projeto_id,
            project.get("nome_projeto", ""), project.get("cliente_id"),
            project.get("cliente_nome", ""),
            payload.tipo_produto, payload.variacao_produto, payload.preco_unitario,
            payload.insumos_inclusos, payload.observacoes_proposta,
            items_dict, payload.condicoes_pagamento, insumos_dict,
            payload.rodape_observacoes, payload.status, [],
            user["id"], user.get("name", ""), now, now,
            user["id"], user.get("name", ""),
        )

    updated = _row(await pg_db.fetch_one(
        "SELECT * FROM propostas_comerciais WHERE projeto_id=$1 AND tenant_id=$2",
        projeto_id, user["tenant_id"],
    ))

    # R20: disparar explosão de BOM quando pedido confirmado
    if payload.status == "confirmado":
        try:
            await explode_bom_for_proposta(updated, user["tenant_id"], user)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"R20 BOM explosion failed: {exc}")

    return updated


@propostas_router.patch("/{projeto_id}/proposta")
async def patch_proposta(projeto_id: str, payload: PropostaPatch, request: Request):
    user = await _get_current_user(request)
    await _get_project(projeto_id, user["tenant_id"])

    patch = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}

    if "items_pedido" in patch:
        patch["items_pedido"] = [
            i.dict() if isinstance(i, PedidoItem) else i for i in patch["items_pedido"]
        ]
    if "insumos_fabricacao" in patch:
        patch["insumos_fabricacao"] = [
            i.dict() if isinstance(i, InsumoItem) else i for i in patch["insumos_fabricacao"]
        ]

    if not patch:
        return {"ok": True}

    patch["updated_at"] = _now_iso()
    patch["updated_by"] = user["id"]
    patch["updated_by_name"] = user.get("name", "")

    ALLOWED = {
        "tipo_produto", "variacao_produto", "preco_unitario", "insumos_inclusos",
        "observacoes_proposta", "items_pedido", "condicoes_pagamento", "insumos_fabricacao",
        "rodape_observacoes", "status", "updated_at", "updated_by", "updated_by_name",
    }
    set_parts = []
    vals: list = []
    i = 1
    for k, v in patch.items():
        if k in ALLOWED:
            set_parts.append(f"{k}=${i}")
            vals.append(v)
            i += 1

    if not set_parts:
        return {"ok": True}

    res = await pg_db.execute(
        f"UPDATE propostas_comerciais SET {', '.join(set_parts)} WHERE projeto_id=${i} AND tenant_id=${i+1}",
        *vals, projeto_id, user["tenant_id"],
    )
    if res == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Proposta não encontrada — crie com POST primeiro")

    return _row(await pg_db.fetch_one(
        "SELECT * FROM propostas_comerciais WHERE projeto_id=$1 AND tenant_id=$2",
        projeto_id, user["tenant_id"],
    ))


# ── R18: Status das amostras do projeto ──────────────────────────────────────

@propostas_router.get("/{projeto_id}/amostras-status")
async def get_amostras_status(projeto_id: str, request: Request):
    """
    R18 — Retorna situação de cada variação de amostra do projeto.
    Usado pelo frontend para bloquear confirmação de pedido quando nenhuma
    amostra está aprovada pelo cliente.
    """
    user = await _get_current_user(request)
    await _get_project(projeto_id, user["tenant_id"])

    samples = await pg_db.fetch_all(
        "SELECT id, numero_amostra, nome_produto FROM crm_samples WHERE projeto_id=$1 AND tenant_id=$2",
        projeto_id, user["tenant_id"],
    )

    variacoes_all: list = []
    if samples:
        sample_ids = [s["id"] for s in samples]
        placeholders = ",".join(f"${j+1}" for j in range(len(sample_ids)))
        variacoes_all = await pg_db.fetch_all(
            f"SELECT * FROM crm_sample_variacoes WHERE sample_id IN ({placeholders})",
            *sample_ids,
        )

    v_by_sample: dict = {}
    for v in variacoes_all:
        vd = dict(v)
        v_by_sample.setdefault(vd["sample_id"], []).append(vd)

    resumo = []
    total_aprovadas = 0
    sku_ids_needed = []

    _STATUS_PD_APROVADO = {"aprovado", "concluido", "APPROVED", "COMPLETED"}
    _STATUS_PD_REPROVADO = {"reprovado", "REJECTED"}

    for s in samples:
        sd = dict(s)
        for v in v_by_sample.get(sd["id"], []):
            status_raw = v.get("status", "solicitada")
            resultado = v.get("resultado", "")
            status_pd_raw = v.get("status_pd_raw", "")
            aprovada = (
                bool(v.get("aprovacao_externa"))
                or status_raw == "aprovada"
                or resultado == "aprovada"
                or status_pd_raw in _STATUS_PD_APROVADO
            )
            if aprovada:
                label = "aprovada"
                total_aprovadas += 1
            elif (
                status_raw in ("reprovada", "cancelada")
                or resultado == "reprovada"
                or status_pd_raw in _STATUS_PD_REPROVADO
            ):
                label = "reprovada"
            elif status_raw in ("plano_futuro",):
                label = "plano_futuro"
            else:
                label = "em_andamento"

            sku_id = v.get("sku_id")
            if sku_id:
                sku_ids_needed.append(sku_id)

            resumo.append({
                "amostra_id": sd["id"],
                "numero_amostra": sd.get("numero_amostra", ""),
                "nome_produto": sd.get("nome_produto", "") or v.get("nome_produto", ""),
                "variacao_id": v["id"],
                "codigo": v.get("codigo", ""),
                "descricao": v.get("descricao_aplicacao", ""),
                "status": label,
                "aprovada": aprovada,
                "sku_id": sku_id,
                "sku_codigo": "",
            })

    if sku_ids_needed:
        placeholders = ",".join(f"${j+1}" for j in range(len(sku_ids_needed)))
        skus = await pg_db.fetch_all(
            f"SELECT id, codigo_interno FROM skus WHERE id IN ({placeholders})",
            *sku_ids_needed,
        )
        sku_map = {s["id"]: s.get("codigo_interno", "") for s in skus}
        for item in resumo:
            if item["sku_id"]:
                item["sku_codigo"] = sku_map.get(item["sku_id"], "")

    return {
        "total": len(resumo),
        "total_aprovadas": total_aprovadas,
        "pode_confirmar": total_aprovadas > 0,
        "variacoes": resumo,
    }


# ── R20: Explosão de BOM → Necessidade de Material ───────────────────────────

async def explode_bom_for_proposta(proposta: dict, tenant_id: str, user: dict) -> dict:
    """
    R20 — Calcula necessidade de materiais por quantidade negociada.

    Composição 1 (bulk): (percentual/100) × qtd_envase_g × qtd_pedido → converte para kg
    Composição 2 (embalagem): quantidade_por_unidade × qtd_pedido → ceil(/ fator_conversao)

    Consolida por codigo_material, salva em order_material_requirements.
    """
    necessidades: dict = {}

    for pedido_item in (proposta.get("items_pedido") or []):
        codigo_kuryos = (pedido_item.get("codigo_kuryos") or "").strip()
        qtd_pedido = float(pedido_item.get("qtd") or 0)
        if not codigo_kuryos or qtd_pedido <= 0:
            continue

        sku = _row(await pg_db.fetch_one(
            "SELECT * FROM skus WHERE codigo_interno=$1 AND tenant_id=$2",
            codigo_kuryos, tenant_id,
        ))
        if not sku:
            continue

        sku_id = sku["id"]
        produto_pai_id = sku.get("produto_pai_id")
        apresentacao = sku.get("apresentacao") or {}
        if isinstance(apresentacao, str):
            try:
                apresentacao = json.loads(apresentacao)
            except Exception:
                apresentacao = {}
        qtd_envase_g = apresentacao.get("qtd_envase")

        # ── Composição 2 — Embalagem ────────────────────────────────────────
        bom_embal = await pg_db.fetch_all(
            """SELECT * FROM bom_items
               WHERE sku_id=$1 AND camada='embalagem' AND vigente=TRUE AND tenant_id=$2""",
            sku_id, tenant_id,
        )

        for item in bom_embal:
            cod = item["codigo_material"]
            qtd_raw = float(item["quantidade_por_unidade"]) * qtd_pedido
            fator = float(item.get("fator_conversao") or 1.0)
            qtd_compra = math.ceil(qtd_raw / fator)

            if cod not in necessidades:
                necessidades[cod] = {
                    "insumo_id": cod,
                    "tipo": item.get("tipo", "EP"),
                    "descricao": item.get("nome_material", cod),
                    "qtd_necessaria": 0.0,
                    "qtd_necessaria_compra": 0.0,
                    "unidade_consumo": item.get("unidade_consumo", "un"),
                    "unidade_compra": item.get("unidade_compra", "un"),
                    "fator_conversao": fator,
                    "responsavel": "compras",
                    "sku_ids": [],
                    "pendente_info": False,
                }
            necessidades[cod]["qtd_necessaria"] = round(
                necessidades[cod]["qtd_necessaria"] + qtd_raw, 4
            )
            necessidades[cod]["qtd_necessaria_compra"] = round(
                necessidades[cod]["qtd_necessaria_compra"] + qtd_compra, 4
            )
            if sku_id not in necessidades[cod]["sku_ids"]:
                necessidades[cod]["sku_ids"].append(sku_id)

        # ── Composição 1 — Bulk ─────────────────────────────────────────────
        if produto_pai_id:
            bom_bulk = await pg_db.fetch_all(
                """SELECT * FROM bom_items
                   WHERE produto_pai_id=$1 AND camada='bulk' AND vigente=TRUE AND tenant_id=$2""",
                produto_pai_id, tenant_id,
            )

            for item in bom_bulk:
                cod = item["codigo_material"]

                if not qtd_envase_g or float(qtd_envase_g) <= 0:
                    if cod not in necessidades:
                        necessidades[cod] = {
                            "insumo_id": cod,
                            "tipo": item.get("tipo", "MP"),
                            "descricao": item.get("nome_material", cod),
                            "qtd_necessaria": None,
                            "qtd_necessaria_compra": None,
                            "unidade_consumo": "g",
                            "unidade_compra": "kg",
                            "fator_conversao": 1000.0,
                            "responsavel": "compras",
                            "sku_ids": [],
                            "pendente_info": True,
                        }
                    else:
                        necessidades[cod]["pendente_info"] = True
                    if sku_id not in necessidades[cod]["sku_ids"]:
                        necessidades[cod]["sku_ids"].append(sku_id)
                    continue

                qtd_g = (float(item["percentual"]) / 100.0) * float(qtd_envase_g) * qtd_pedido
                qtd_kg = qtd_g / 1000.0

                if cod not in necessidades:
                    necessidades[cod] = {
                        "insumo_id": cod,
                        "tipo": item.get("tipo", "MP"),
                        "descricao": item.get("nome_material", cod),
                        "qtd_necessaria": 0.0,
                        "qtd_necessaria_compra": 0.0,
                        "unidade_consumo": "g",
                        "unidade_compra": "kg",
                        "fator_conversao": 1000.0,
                        "responsavel": "compras",
                        "sku_ids": [],
                        "pendente_info": False,
                    }

                necessidades[cod]["qtd_necessaria"] = round(
                    (necessidades[cod]["qtd_necessaria"] or 0) + qtd_g, 3
                )
                qtd_kg_compra = math.ceil(qtd_kg * 10) / 10
                necessidades[cod]["qtd_necessaria_compra"] = round(
                    (necessidades[cod]["qtd_necessaria_compra"] or 0) + qtd_kg_compra, 3
                )
                if sku_id not in necessidades[cod]["sku_ids"]:
                    necessidades[cod]["sku_ids"].append(sku_id)

    materiais_list = [{"id": _new_id(), **v} for v in necessidades.values()]

    now = _now_iso()
    tem_pendente = any(m.get("pendente_info") for m in materiais_list)
    doc_id = _new_id()
    await pg_db.execute(
        """INSERT INTO order_material_requirements
           (id, tenant_id, proposta_id, projeto_id, gerado_em,
            gerado_por, gerado_por_nome, status, materiais, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
           ON CONFLICT (tenant_id, proposta_id) DO UPDATE SET
               materiais    = EXCLUDED.materiais,
               status       = EXCLUDED.status,
               gerado_em    = EXCLUDED.gerado_em,
               gerado_por   = EXCLUDED.gerado_por,
               updated_at   = NOW()""",
        doc_id, tenant_id,
        proposta.get("id"), proposta.get("projeto_id"), now,
        user["id"], user.get("name", ""),
        "pendente_info" if tem_pendente else "gerado",
        materiais_list, now, now,
    )
    return _row(await pg_db.fetch_one(
        "SELECT * FROM order_material_requirements WHERE proposta_id=$1 AND tenant_id=$2",
        proposta.get("id"), tenant_id,
    )) or {}


@propostas_router.get("/{projeto_id}/material-requirements")
async def get_material_requirements(projeto_id: str, request: Request):
    """R20 — Retorna necessidades de material geradas para a proposta confirmada."""
    user = await _get_current_user(request)
    await _get_project(projeto_id, user["tenant_id"])

    proposta = _row(await pg_db.fetch_one(
        "SELECT id FROM propostas_comerciais WHERE projeto_id=$1 AND tenant_id=$2",
        projeto_id, user["tenant_id"],
    ))
    if not proposta:
        return {}

    req = _row(await pg_db.fetch_one(
        "SELECT * FROM order_material_requirements WHERE proposta_id=$1 AND tenant_id=$2",
        proposta["id"], user["tenant_id"],
    ))
    return req or {}


# ── Upload de arquivo ────────────────────────────────────────────────────────

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "propostas")


@propostas_router.post("/{projeto_id}/proposta/attachments")
async def upload_attachment(
    projeto_id: str,
    request: Request,
    file: UploadFile = File(...),
):
    """Anexa um arquivo à proposta. Salva em disco e registra referência."""
    user = await _get_current_user(request)
    await _get_project(projeto_id, user["tenant_id"])

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_id = _new_id()
    ext = os.path.splitext(file.filename or "")[1] or ""
    filename_stored = f"{file_id}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename_stored)

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    ref = {
        "id": file_id,
        "nome_original": file.filename,
        "tipo": file.content_type or "application/octet-stream",
        "tamanho_bytes": len(contents),
        "path": filename_stored,
        "url": f"/api/propostas/files/{filename_stored}",
        "uploaded_at": _now_iso(),
        "uploaded_by": user["id"],
        "uploaded_by_name": user.get("name", ""),
    }

    await pg_db.execute(
        """UPDATE propostas_comerciais
           SET arquivos = arquivos || $1::jsonb
           WHERE projeto_id=$2 AND tenant_id=$3""",
        json.dumps([ref]), projeto_id, user["tenant_id"],
    )

    return ref
