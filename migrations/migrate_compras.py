"""
migrate_compras.py — Backfill das 6 coleções Compras do MongoDB para PostgreSQL.

Uso:
    cd backend
    python ../migrations/migrate_compras.py
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import motor.motor_asyncio
import asyncpg
from urllib.parse import urlparse, quote
import json


def _safe_dsn(url: str) -> str:
    p = urlparse(url)
    if not p.password:
        return url
    encoded = quote(p.password, safe="")
    return url.replace(f":{p.password}@", f":{encoded}@", 1)


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


COMPRAS_COUNTER_KEYS = [
    "compras_fornecedores",
    "compras_mrp_2026",
    "compras_po_2026",
    "ordem_compra",
]


def _parse_dt(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


async def main():
    from dotenv import load_dotenv
    from pathlib import Path
    repo_root = Path(__file__).parent.parent
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / "backend" / ".env", override=False)

    mongo_url = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
    pg_url = os.environ["DATABASE_URL"]

    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
    db_name = urlparse(mongo_url).path.lstrip("/") or "kuryos"
    mdb = mongo_client[db_name]

    pg = await asyncpg.connect(_safe_dsn(pg_url), ssl="require", statement_cache_size=0)
    await _init_conn(pg)
    print("Conectado ao PostgreSQL")

    # ─── Seed counters ────────────────────────────────────────────────────────
    print("\n-- Sincronizando contadores Compras --")
    tenant_ids = []
    async for t in mdb.tenants.find({}, {"_id": 0, "id": 1}):
        if t.get("id"):
            tenant_ids.append(t["id"])
    pg_tenants = await pg.fetch("SELECT id FROM tenants")
    for row in pg_tenants:
        if row["id"] not in tenant_ids:
            tenant_ids.append(row["id"])

    year = datetime.utcnow().year
    for tenant_id in tenant_ids:
        for key in COMPRAS_COUNTER_KEYS:
            mongo_key = key if "_" in key else key
            counter_doc = await mdb.counters.find_one({"_id": f"{mongo_key}:{tenant_id}"})
            mongo_seq = int(counter_doc.get("seq", 0)) if counter_doc else 0

            pg_key = f"{mongo_key}:{tenant_id}"
            existing = await pg.fetchval("SELECT seq FROM counters WHERE id=$1", pg_key)
            if existing is None:
                await pg.execute(
                    "INSERT INTO counters(id, tenant_id, seq, updated_at) VALUES($1,$2,$3,NOW()) ON CONFLICT DO NOTHING",
                    pg_key, tenant_id, mongo_seq,
                )
                print(f"  [seed] {pg_key} = {mongo_seq}")
            elif mongo_seq > existing:
                await pg.execute("UPDATE counters SET seq=$1, updated_at=NOW() WHERE id=$2", mongo_seq, pg_key)
                print(f"  [sync] {pg_key}: {existing} -> {mongo_seq}")

    # ─── compras_fornecedores ─────────────────────────────────────────────────
    print("\n-- Migrando compras_fornecedores --")
    count = 0
    async for doc in mdb.compras_fornecedores.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO compras_fornecedores(
                  id, tenant_id, codigo_interno, razao_social, nome_fantasia,
                  cnpj, cnpj_normalizado, ie, im,
                  endereco, contatos, categorias, homologacao,
                  status_cadastro, log_auditoria, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("codigo_interno"), doc.get("razao_social", ""), doc.get("nome_fantasia", ""),
                doc.get("cnpj", ""), doc.get("cnpj_normalizado"),
                doc.get("ie", ""), doc.get("im", ""),
                doc.get("endereco") or {}, doc.get("contatos") or [], doc.get("categorias") or [],
                doc.get("homologacao") or {},
                doc.get("status_cadastro", "ativo"),
                doc.get("log_auditoria") or [],
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO FORN {doc.get('id')}: {e}")
    print(f"  {count} fornecedores migrados")

    # ─── compras_itens ────────────────────────────────────────────────────────
    print("\n-- Migrando compras_itens --")
    count = 0
    async for doc in mdb.compras_itens.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO compras_itens(
                  id, tenant_id, codigo_interno, descricao, categoria,
                  sub_categoria, unidade_compra, fator_conversao_producao,
                  estoque_minimo, estoque_seguranca, lead_time_dias,
                  requer_homologacao_cq, fornecedores_homologados, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("codigo_interno", ""), doc.get("descricao", ""), doc.get("categoria", ""),
                doc.get("sub_categoria", ""), doc.get("unidade_compra", ""),
                doc.get("fator_conversao_producao", 1.0),
                doc.get("estoque_minimo"), doc.get("estoque_seguranca", 0.0),
                doc.get("lead_time_dias", 0),
                doc.get("requer_homologacao_cq", True),
                doc.get("fornecedores_homologados") or [],
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO ITEM {doc.get('id')}: {e}")
    print(f"  {count} itens migrados")

    # ─── compras_condicoes_comerciais ─────────────────────────────────────────
    print("\n-- Migrando compras_condicoes_comerciais --")
    count = 0
    async for doc in mdb.compras_condicoes_comerciais.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO compras_condicoes_comerciais(
                  id, tenant_id, fornecedor_id, fornecedor_nome,
                  item_id, item_descricao,
                  preco_unitario, preco_unitario_currency,
                  prazo_pagamento_texto, prazo_pagamento_dias,
                  prazo_entrega_dias_uteis, moq,
                  frete_tipo, frete_valor, valido_ate, origem,
                  cotado_por_id, cotado_por_nome, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("fornecedor_id"), doc.get("fornecedor_nome", ""),
                doc.get("item_id"), doc.get("item_descricao", ""),
                doc.get("preco_unitario", 0), doc.get("preco_unitario_currency", "BRL"),
                doc.get("prazo_pagamento_texto", ""), doc.get("prazo_pagamento_dias", 0),
                doc.get("prazo_entrega_dias_uteis", 0), doc.get("moq", 1.0),
                doc.get("frete_tipo", "cif"), doc.get("frete_valor", 0.0),
                doc.get("valido_ate"), doc.get("origem", "manual"),
                doc.get("cotado_por_id"), doc.get("cotado_por_nome", ""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO COND {doc.get('id')}: {e}")
    print(f"  {count} condições comerciais migradas")

    # ─── compras_pos ──────────────────────────────────────────────────────────
    print("\n-- Migrando compras_pos --")
    count = 0
    async for doc in mdb.compras_pos.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO compras_pos(
                  id, tenant_id, numero_po,
                  fornecedor_id, fornecedor_nome, fornecedor_cnpj,
                  status, origem, ops_vinculadas,
                  data_emissao, data_entrega_solicitada, data_entrega_confirmada,
                  prazo_pagamento_texto, prazo_pagamento_dias,
                  fornecedor_homologado, itens, valor_total_po,
                  compartilhamento, nfs_vinculadas,
                  gatilho_financeiro_acionado, data_vencimento_pagamento,
                  cancelado_motivo, cancelado_por, cancelado_em,
                  requer_aprovacao, aprovado_por, aprovado_em,
                  created_at, updated_at, created_by_id, created_by_nome, log_auditoria
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                  $18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32
                ) ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""), doc.get("numero_po"),
                doc.get("fornecedor_id"), doc.get("fornecedor_nome", ""), doc.get("fornecedor_cnpj", ""),
                doc.get("status", "rascunho"), doc.get("origem", "manual"),
                doc.get("ops_vinculadas") or [],
                doc.get("data_emissao"), doc.get("data_entrega_solicitada"), doc.get("data_entrega_confirmada"),
                doc.get("prazo_pagamento_texto", ""), doc.get("prazo_pagamento_dias", 0),
                doc.get("fornecedor_homologado", False),
                doc.get("itens") or [], doc.get("valor_total_po", 0.0),
                doc.get("compartilhamento") or {},
                doc.get("nfs_vinculadas") or [],
                doc.get("gatilho_financeiro_acionado", False),
                doc.get("data_vencimento_pagamento"),
                doc.get("cancelado_motivo"), doc.get("cancelado_por"), doc.get("cancelado_em"),
                doc.get("requer_aprovacao", False), doc.get("aprovado_por"), doc.get("aprovado_em"),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("created_by_id"), doc.get("created_by_nome", ""),
                doc.get("log_auditoria") or [],
            )
            count += 1
        except Exception as e:
            print(f"  ERRO PO {doc.get('id')}: {e}")
    print(f"  {count} POs migradas")

    # ─── compras_mrp_rodadas ──────────────────────────────────────────────────
    print("\n-- Migrando compras_mrp_rodadas --")
    count = 0
    async for doc in mdb.compras_mrp_rodadas.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO compras_mrp_rodadas(
                  id, tenant_id, numero_mrp, status,
                  ops_consideradas, snapshot_estoque, snapshot_pos_transito,
                  itens_sugeridos,
                  aprovado_por_id, aprovado_por_nome, aprovado_em,
                  disparado_por_id, disparado_por_nome, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("numero_mrp"), doc.get("status", "gerada"),
                doc.get("ops_consideradas") or [],
                doc.get("snapshot_estoque") or {},
                doc.get("snapshot_pos_transito") or {},
                doc.get("itens_sugeridos") or [],
                doc.get("aprovado_por_id"), doc.get("aprovado_por_nome", ""),
                doc.get("aprovado_em"),
                doc.get("disparado_por_id"), doc.get("disparado_por_nome", ""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO MRP {doc.get('id')}: {e}")
    print(f"  {count} rodadas MRP migradas")

    # ─── compras_demandas ─────────────────────────────────────────────────────
    print("\n-- Migrando compras_demandas --")
    count = 0
    async for doc in mdb.compras_demandas.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO compras_demandas(
                  id, tenant_id, mrp_rodada_id, mrp_numero,
                  item_id, item_descricao, quantidade,
                  data_limite_pedido, urgente, motivo,
                  fornecedor_selecionado_id, condicao_comercial_id,
                  po_id, status, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("mrp_rodada_id"), doc.get("mrp_numero", ""),
                doc.get("item_id"), doc.get("item_descricao", ""),
                doc.get("quantidade", 0.0),
                doc.get("data_limite_pedido"),
                doc.get("urgente", False), doc.get("motivo", ""),
                doc.get("fornecedor_selecionado_id"), doc.get("condicao_comercial_id"),
                doc.get("po_id"), doc.get("status", "pendente"),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO DEM {doc.get('id')}: {e}")
    print(f"  {count} demandas migradas")

    await pg.close()
    print("\nMigracao Compras concluida com sucesso.")


if __name__ == "__main__":
    asyncio.run(main())
