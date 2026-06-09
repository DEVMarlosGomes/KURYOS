"""
Recebimento de Materiais — entrada de NF vinculada à PO.
Fluxo:
  1. Recebimento criado → cada item vai para estoque em posicao_cq="quarentena"
  2. RA CQ criada automaticamente (recepcao_mp ou recepcao_embalagem)
  3. CQ aprova → WMS posicao_cq="aprovado"; CQ reprova → posicao_cq="reprovado"
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

recebimento_router = APIRouter(prefix="/api/recebimento")

db = None
get_current_user = None
new_id_func = None
now_iso_func = None


def init_recebimento(database, auth_func, id_func, iso_func):
    global db, get_current_user, new_id_func, now_iso_func
    db = database
    get_current_user = auth_func
    new_id_func = id_func
    now_iso_func = iso_func


def new_id():
    return new_id_func()


def now_iso():
    return now_iso_func()


# ===== SETOR MAPPING =====
_TIPO_MP_TO_SETOR = {
    "FORMULACAO": "MANIPULACAO",
    "ROTULO": "ROTULAGEM",
    "EMBALAGEM": "LOGISTICA",
}

_TIPO_MP_TO_RA_TIPO = {
    "FORMULACAO": "recepcao_mp",
    "ROTULO": "recepcao_embalagem",
    "EMBALAGEM": "recepcao_embalagem",
}


# ===== MODELS =====
class RecebimentoItem(BaseModel):
    nome: str
    codigo: str = ""
    tipo_mp: str = "FORMULACAO"   # FORMULACAO | ROTULO | EMBALAGEM
    quantidade: float
    unidade: str = "kg"
    lote: str = ""
    validade: Optional[str] = None
    mp_id: Optional[str] = None   # link to pd_homologacao_mps


class RecebimentoCreate(BaseModel):
    po_id: Optional[str] = None
    po_numero: Optional[str] = None
    fornecedor_id: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    numero_nf: str
    data_nf: str                  # YYYY-MM-DD
    items: List[RecebimentoItem]
    observacoes: str = ""


# ===== ROUTES =====
@recebimento_router.get("/entradas")
async def list_entradas(
    request: Request,
    status: Optional[str] = None,
    q: Optional[str] = None,
):
    user = await get_current_user(request)
    query: Dict[str, Any] = {"tenant_id": user["tenant_id"]}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"numero_nf": {"$regex": q, "$options": "i"}},
            {"fornecedor_nome": {"$regex": q, "$options": "i"}},
            {"po_numero": {"$regex": q, "$options": "i"}},
        ]
    entradas = await db.recebimentos.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return entradas


@recebimento_router.get("/entradas/{entrada_id}")
async def get_entrada(entrada_id: str, request: Request):
    user = await get_current_user(request)
    entrada = await db.recebimentos.find_one({"id": entrada_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
    if not entrada:
        raise HTTPException(status_code=404, detail="Recebimento não encontrado")
    return entrada


@recebimento_router.post("/entradas")
async def create_entrada(data: RecebimentoCreate, request: Request):
    """
    Registra entrada de NF:
    - Cria/atualiza itens no estoque com posicao_cq=quarentena
    - Cria RA no CQ para cada item
    - Cria registro do recebimento
    """
    user = await get_current_user(request)
    tid = user["tenant_id"]

    if not data.items:
        raise HTTPException(status_code=400, detail="Informe ao menos um item")

    now = now_iso()
    entrada_id = new_id()
    items_processados = []

    for item in data.items:
        setor = _TIPO_MP_TO_SETOR.get(item.tipo_mp, "MANIPULACAO")
        ra_tipo = _TIPO_MP_TO_RA_TIPO.get(item.tipo_mp, "recepcao_mp")

        # 1) Find or create estoque item
        query_estoque: Dict[str, Any] = {"tenant_id": tid, "setor": setor}
        if item.mp_id:
            query_estoque["mp_id"] = item.mp_id
        else:
            query_estoque["nome"] = item.nome
            query_estoque["mp_id"] = None

        estoque_item = await db.estoque_items.find_one(query_estoque, {"_id": 0})
        estoque_item_id = None

        if estoque_item:
            estoque_item_id = estoque_item["id"]
            # Move to quarentena if not already approved
            if estoque_item.get("posicao_cq") not in ("aprovado",):
                await db.estoque_items.update_one(
                    {"id": estoque_item_id},
                    {"$set": {"posicao_cq": "quarentena", "lote": item.lote or estoque_item.get("lote", ""), "updated_at": now}}
                )
        else:
            # Create new item in quarentena
            estoque_item_id = new_id()
            new_item = {
                "id": estoque_item_id,
                "tenant_id": tid,
                "tipo_item": "mp",
                "setor": setor,
                "nome": item.nome,
                "codigo": item.codigo,
                "mp_id": item.mp_id,
                "produto_id": None,
                "unidade": item.unidade,
                "quantidade_atual": 0,
                "estoque_minimo": 0,
                "localizacao": "",
                "lote": item.lote,
                "validade": item.validade,
                "observacoes": "",
                "posicao_cq": "quarentena",
                "created_by": user["id"],
                "created_by_name": user["name"],
                "created_at": now,
                "updated_at": now,
            }
            await db.estoque_items.insert_one(new_item)

        # 2) Create WMS entry movement
        estoque_item_full = await db.estoque_items.find_one({"id": estoque_item_id}, {"_id": 0})
        if estoque_item_full:
            qty_antes = estoque_item_full.get("quantidade_atual", 0)
            qty_depois = qty_antes + item.quantidade
            await db.estoque_items.update_one(
                {"id": estoque_item_id},
                {"$set": {"quantidade_atual": qty_depois, "updated_at": now}}
            )
            mov = {
                "id": new_id(),
                "tenant_id": tid,
                "item_id": estoque_item_id,
                "setor": setor,
                "tipo_item": "mp",
                "nome_item": item.nome,
                "codigo_item": item.codigo,
                "lote": item.lote,
                "tipo": "ENTRADA_RECEBIMENTO",
                "direcao": "entrada",
                "quantidade": item.quantidade,
                "unidade": item.unidade,
                "quantidade_antes": qty_antes,
                "quantidade_depois": qty_depois,
                "motivo": f"Recebimento NF {data.numero_nf}",
                "referencia": entrada_id,
                "documento": data.numero_nf,
                "usuario": user["name"],
                "usuario_id": user["id"],
                "created_at": now,
            }
            await db.estoque_movimentos.insert_one(mov)

        # 3) Create RA in CQ
        lote_id = new_id()
        lote_numero = item.lote or f"L{now[:10].replace('-', '')}"
        ra = {
            "id": new_id(),
            "tenant_id": tid,
            "lote_id": lote_id,
            "lote_numero": lote_numero,
            "tipo": ra_tipo,
            "status": "rascunho",
            "item_id": estoque_item_id,
            "item_nome": item.nome,
            "item_tipo": item.tipo_mp,
            "fornecedor_id": data.fornecedor_id,
            "fornecedor_nome": data.fornecedor_nome,
            "nf_numero": data.numero_nf,
            "nf_data": data.data_nf,
            "quantidade_recebida": item.quantidade,
            "unidade": item.unidade,
            "numero_lote_fornecedor": item.lote,
            "data_validade_fornecedor": item.validade,
            "parametros": [],
            "recebimento_id": entrada_id,
            "created_by": user["id"],
            "created_by_name": user["name"],
            "created_at": now,
            "updated_at": now,
        }
        await db.cq_registros_analise.insert_one(ra)

        items_processados.append({
            **item.model_dump(),
            "estoque_item_id": estoque_item_id,
            "setor": setor,
            "ra_id": ra["id"],
            "ra_status": "rascunho",
        })

    # 4) Create recebimento record
    entrada = {
        "id": entrada_id,
        "tenant_id": tid,
        "po_id": data.po_id,
        "po_numero": data.po_numero,
        "fornecedor_id": data.fornecedor_id,
        "fornecedor_nome": data.fornecedor_nome or "",
        "numero_nf": data.numero_nf,
        "data_nf": data.data_nf,
        "status": "quarentena",
        "items": items_processados,
        "observacoes": data.observacoes,
        "created_by": user["id"],
        "created_by_name": user["name"],
        "created_at": now,
        "updated_at": now,
    }
    await db.recebimentos.insert_one(entrada)
    entrada.pop("_id", None)
    logger.info(f"Recebimento {entrada_id} criado: NF={data.numero_nf} itens={len(items_processados)}")
    return entrada
