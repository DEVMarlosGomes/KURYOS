"""
propostas_routes.py — R14: Proposta Comercial & Pedido de Fabricação

Coleção: db.propostas_comerciais  (uma por projeto, upsert)
Endpoints:
  GET    /crm/projects/{id}/proposta
  POST   /crm/projects/{id}/proposta          (criar / atualizar inteiro)
  PATCH  /crm/projects/{id}/proposta          (atualizar parcialmente)
  GET    /crm/projects/{id}/amostras-status   (R18: validação antes de confirmar pedido)
"""

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import os

propostas_router = APIRouter(prefix="/crm/projects", tags=["propostas"])

db = None
_get_current_user = None
_new_id = None
_now_iso = None


def init_propostas(database, get_current_user_fn, new_id_fn, now_iso_fn):
    global db, _get_current_user, _new_id, _now_iso
    db = database
    _get_current_user = get_current_user_fn
    _new_id = new_id_fn
    _now_iso = now_iso_fn


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
    valor_total: Optional[float] = None  # calculado no frontend, salvo aqui

class PropostaPayload(BaseModel):
    # Bloco A — Proposta Comercial
    tipo_produto: str = ""
    variacao_produto: str = ""
    preco_unitario: Optional[float] = None
    insumos_inclusos: List[str] = []
    observacoes_proposta: str = ""
    # Bloco B — Pedido de Fabricação
    items_pedido: List[PedidoItem] = []
    condicoes_pagamento: str = ""
    insumos_fabricacao: List[InsumoItem] = []
    rodape_observacoes: str = ""
    # Controle
    status: str = "rascunho"  # rascunho | confirmado | cancelado

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
    proj = await db.crm_projects.find_one(
        {"id": projeto_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return proj


# ── Endpoints ─────────────────────────────────────────────────────────────────

@propostas_router.get("/{projeto_id}/proposta")
async def get_proposta(projeto_id: str, request: Request):
    user = await _get_current_user(request)
    await _get_project(projeto_id, user["tenant_id"])
    doc = await db.propostas_comerciais.find_one(
        {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    )
    if not doc:
        return {}
    return doc


@propostas_router.post("/{projeto_id}/proposta")
async def upsert_proposta(projeto_id: str, payload: PropostaPayload, request: Request):
    """Cria ou substitui completamente a proposta do projeto."""
    user = await _get_current_user(request)
    project = await _get_project(projeto_id, user["tenant_id"])

    now = _now_iso()
    existing = await db.propostas_comerciais.find_one(
        {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]}
    )

    items_dict = [item.dict() for item in payload.items_pedido]
    insumos_dict = [i.dict() for i in payload.insumos_fabricacao]

    if existing:
        doc_id = existing.get("id", _new_id())
        await db.propostas_comerciais.update_one(
            {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]},
            {"$set": {
                **payload.dict(exclude={"items_pedido", "insumos_fabricacao"}),
                "items_pedido": items_dict,
                "insumos_fabricacao": insumos_dict,
                "updated_at": now,
                "updated_by": user["id"],
                "updated_by_name": user.get("name", ""),
            }},
        )
    else:
        doc_id = _new_id()
        doc = {
            "id": doc_id,
            "tenant_id": user["tenant_id"],
            "projeto_id": projeto_id,
            "projeto_nome": project.get("nome_projeto", ""),
            "cliente_id": project.get("cliente_id"),
            "cliente_nome": project.get("cliente_nome", ""),
            **payload.dict(exclude={"items_pedido", "insumos_fabricacao"}),
            "items_pedido": items_dict,
            "insumos_fabricacao": insumos_dict,
            "arquivos": [],
            "created_at": now,
            "created_by": user["id"],
            "created_by_name": user.get("name", ""),
            "updated_at": now,
            "updated_by": user["id"],
            "updated_by_name": user.get("name", ""),
        }
        await db.propostas_comerciais.insert_one(doc)

    updated = await db.propostas_comerciais.find_one(
        {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    )
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

    result = await db.propostas_comerciais.update_one(
        {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]},
        {"$set": patch},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Proposta não encontrada — crie com POST primeiro")

    updated = await db.propostas_comerciais.find_one(
        {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]}, {"_id": 0}
    )
    return updated


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

    samples = await db.crm_samples.find(
        {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]},
        {"_id": 0, "id": 1, "numero_amostra": 1, "nome_produto": 1, "variacoes": 1},
    ).to_list(500)

    resumo = []
    total_aprovadas = 0

    for s in samples:
        for v in s.get("variacoes", []):
            aprovada = bool(v.get("aprovacao_externa"))
            status_raw = v.get("status", "solicitada")
            if aprovada:
                label = "aprovada"
                total_aprovadas += 1
            elif status_raw in ("reprovada", "cancelada"):
                label = "reprovada"
            elif status_raw in ("plano_futuro",):
                label = "plano_futuro"
            else:
                label = "em_andamento"

            resumo.append({
                "amostra_id": s["id"],
                "numero_amostra": s.get("numero_amostra", ""),
                "nome_produto": s.get("nome_produto", ""),
                "variacao_id": v["id"],
                "codigo": v.get("codigo", ""),
                "descricao": v.get("descricao_aplicacao", ""),
                "status": label,
                "aprovada": aprovada,
            })

    return {
        "total": len(resumo),
        "total_aprovadas": total_aprovadas,
        "pode_confirmar": total_aprovadas > 0,
        "variacoes": resumo,
    }


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

    await db.propostas_comerciais.update_one(
        {"projeto_id": projeto_id, "tenant_id": user["tenant_id"]},
        {"$push": {"arquivos": ref}},
    )

    return ref
