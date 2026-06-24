"""
migrate_crm.py — Backfill das 8 coleções CRM do MongoDB para PostgreSQL.

Uso:
    cd backend
    python ../migrations/migrate_crm.py
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


CRM_COUNTER_KEYS = ["cli_seq", "sku_seq"]


def _parse_dt(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _f(v, default=None):
    return v if v is not None else default


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

    # ─── Sync counters ────────────────────────────────────────────────────────
    print("\n-- Sincronizando contadores CRM --")
    tenant_ids: list[str] = []
    async for t in mdb.tenants.find({}, {"_id": 0, "id": 1}):
        if t.get("id"):
            tenant_ids.append(t["id"])
    pg_tenants = await pg.fetch("SELECT id FROM tenants")
    for row in pg_tenants:
        if row["id"] not in tenant_ids:
            tenant_ids.append(row["id"])

    for tenant_id in tenant_ids:
        for key in CRM_COUNTER_KEYS:
            pg_key = f"{key}:{tenant_id}"
            counter_doc = await mdb.counters.find_one({"_id": pg_key})
            mongo_seq = int(counter_doc.get("seq", 0)) if counter_doc else 0
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

    # ─── crm_clients ─────────────────────────────────────────────────────────
    print("\n-- Migrando crm_clients --")
    count = 0
    async for doc in mdb.crm_clients.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO crm_clients(
                  id, tenant_id, stage, nome_empresa, cnpj, cnpj_normalized,
                  cli3, cli4, cli4_congelado,
                  canal_origem, origem_lead, temperatura_lead,
                  responsavel_comercial, segmento, porte, regiao, site, instagram, observacoes,
                  tem_marca_propria, tem_anvisa, volume_estimado_mensal,
                  prazo_urgencia, valor_estimado_projeto, valor_estimado_projeto_currency,
                  moq_negociado, condicao_pagamento, motivo_perda,
                  data_pedido, valor_primeiro_pedido, valor_primeiro_pedido_currency,
                  previsao_segundo_pedido, ultima_atualizacao_temperatura, has_grau2_anvisa,
                  created_by, created_by_name, created_at, updated_at,
                  categoria_interesse, contato_principal, contatos_adicionais,
                  decisores, fornecedor_atual, anvisa_necessario,
                  concorrentes_envolvidos, skus_confirmados, amostras_aprovadas,
                  historico_movimentacoes
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                  $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36,$37,$38,
                  $39,$40,$41,$42,$43,$44,$45,$46,$47,$48
                )
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("stage"), "prospeccao"), _f(doc.get("nome_empresa"), ""),
                _f(doc.get("cnpj"), ""), doc.get("cnpj_normalized"),
                _f(doc.get("cli3"), ""), _f(doc.get("cli4"), ""),
                bool(doc.get("cli4_congelado")),
                _f(doc.get("canal_origem"), ""), _f(doc.get("origem_lead"), ""),
                _f(doc.get("temperatura_lead"), "morno"),
                _f(doc.get("responsavel_comercial"), ""), _f(doc.get("segmento"), ""),
                _f(doc.get("porte"), ""), _f(doc.get("regiao"), ""),
                _f(doc.get("site"), ""), _f(doc.get("instagram"), ""),
                _f(doc.get("observacoes"), ""),
                doc.get("tem_marca_propria"),
                _f(doc.get("tem_anvisa"), ""), _f(doc.get("volume_estimado_mensal"), ""),
                doc.get("prazo_urgencia"),
                doc.get("valor_estimado_projeto"),
                _f(doc.get("valor_estimado_projeto_currency"), "BRL"),
                _f(doc.get("moq_negociado"), ""), _f(doc.get("condicao_pagamento"), ""),
                _f(doc.get("motivo_perda"), ""),
                doc.get("data_pedido"),
                doc.get("valor_primeiro_pedido"),
                _f(doc.get("valor_primeiro_pedido_currency"), "BRL"),
                doc.get("previsao_segundo_pedido"),
                doc.get("ultima_atualizacao_temperatura"),
                bool(doc.get("has_grau2_anvisa")),
                _f(doc.get("created_by"), ""), _f(doc.get("created_by_name"), ""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("categoria_interesse") or [],
                doc.get("contato_principal") or {},
                doc.get("contatos_adicionais") or [],
                doc.get("decisores") or [],
                doc.get("fornecedor_atual") or {},
                doc.get("anvisa_necessario") or {},
                doc.get("concorrentes_envolvidos") or [],
                doc.get("skus_confirmados") or [],
                doc.get("amostras_aprovadas") or [],
                doc.get("historico_movimentacoes") or [],
            )
            count += 1
        except Exception as e:
            print(f"  ERRO crm_clients {doc.get('id')}: {e}")
    print(f"  {count} crm_clients migrados")

    # ─── crm_projects ────────────────────────────────────────────────────────
    print("\n-- Migrando crm_projects --")
    count = 0
    async for doc in mdb.crm_projects.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO crm_projects(
                  id, tenant_id, cliente_id, cliente_nome, stage, nome_projeto, categoria,
                  briefing_tecnico, responsavel_comercial, responsavel_interno,
                  ideia_conceito, referencia_mercado, publico_alvo, posicionamento,
                  faixa_preco_venda, volume_estimado_pedido, tipo_servico, sensorial_desejado,
                  claims_desejados, prazo_desejado_amostra, prazo_prometido_cliente,
                  observacoes_livres, data_inicio_desenvolvimento, data_ultima_amostra_enviada,
                  numero_amostras_solicitadas, motivo_arquivamento,
                  created_by, created_by_name, created_at, updated_at,
                  restricoes_tecnicas, historico_movimentacoes
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                  $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32
                )
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("cliente_id"), ""), _f(doc.get("cliente_nome"), ""),
                _f(doc.get("stage"), "projeto_em_discussao"),
                _f(doc.get("nome_projeto"), ""), _f(doc.get("categoria"), ""),
                _f(doc.get("briefing_tecnico"), ""),
                _f(doc.get("responsavel_comercial"), ""), _f(doc.get("responsavel_interno"), ""),
                _f(doc.get("ideia_conceito"), ""), _f(doc.get("referencia_mercado"), ""),
                _f(doc.get("publico_alvo"), ""), _f(doc.get("posicionamento"), ""),
                doc.get("faixa_preco_venda"), doc.get("volume_estimado_pedido"),
                _f(doc.get("tipo_servico"), ""), _f(doc.get("sensorial_desejado"), ""),
                _f(doc.get("claims_desejados"), ""), _f(doc.get("prazo_desejado_amostra"), ""),
                doc.get("prazo_prometido_cliente"),
                _f(doc.get("observacoes_livres"), ""),
                doc.get("data_inicio_desenvolvimento"), doc.get("data_ultima_amostra_enviada"),
                _f(doc.get("numero_amostras_solicitadas"), 0),
                _f(doc.get("motivo_arquivamento"), ""),
                _f(doc.get("created_by"), ""), _f(doc.get("created_by_name"), ""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("restricoes_tecnicas") or [],
                doc.get("historico_movimentacoes") or [],
            )
            count += 1
        except Exception as e:
            print(f"  ERRO crm_projects {doc.get('id')}: {e}")
    print(f"  {count} crm_projects migrados")

    # ─── crm_samples ─────────────────────────────────────────────────────────
    print("\n-- Migrando crm_samples --")
    count = 0
    async for doc in mdb.crm_samples.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO crm_samples(
                  id, tenant_id, projeto_id, projeto_nome, cliente_id, cliente_nome,
                  numero_amostra, nome_produto, nome_amostra, categoria, stage,
                  rework_de_amostra_id, rework_motivo, responsavel_pd, parametro_variacao,
                  tipo_amostra, referencia_formula, quantidade_por_variacao, unidade_quantidade,
                  prazo_entrega_cliente, briefing_base, briefing_especifico, feedback_cliente,
                  direcoes_retrabalho, resultado, aprovacao_interna, aprovacao_externa,
                  data_envio, enviado_comercial_em, aprovado_cliente_em, reprovacao_motivo,
                  tem_variacoes, produto, objetivo_projeto, aplicacoes_desenvolver,
                  ativos_claims, referencias, orcamento_projeto, textura_esperada,
                  aplicacao, sensorial, ph, observacao_tecnica,
                  created_by, created_by_name, created_at, updated_at,
                  variacoes, projeto_briefing, referencias_fotos, historico_movimentacoes
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                  $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36,$37,$38,
                  $39,$40,$41,$42,$43,$44,$45,$46,$47,$48,$49,$50,$51
                )
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("projeto_id"), ""), _f(doc.get("projeto_nome"), ""),
                _f(doc.get("cliente_id"), ""), _f(doc.get("cliente_nome"), ""),
                _f(doc.get("numero_amostra"), ""), _f(doc.get("nome_produto"), ""),
                _f(doc.get("nome_amostra"), ""), _f(doc.get("categoria"), ""),
                _f(doc.get("stage"), "solicitada"),
                doc.get("rework_de_amostra_id"), _f(doc.get("rework_motivo"), ""),
                _f(doc.get("responsavel_pd"), ""), _f(doc.get("parametro_variacao"), ""),
                _f(doc.get("tipo_amostra"), ""), _f(doc.get("referencia_formula"), ""),
                doc.get("quantidade_por_variacao"), _f(doc.get("unidade_quantidade"), "g"),
                _f(doc.get("prazo_entrega_cliente"), ""),
                _f(doc.get("briefing_base"), ""), _f(doc.get("briefing_especifico"), ""),
                _f(doc.get("feedback_cliente"), ""), _f(doc.get("direcoes_retrabalho"), ""),
                _f(doc.get("resultado"), ""),
                bool(doc.get("aprovacao_interna")), bool(doc.get("aprovacao_externa")),
                doc.get("data_envio"), doc.get("enviado_comercial_em"),
                doc.get("aprovado_cliente_em"), _f(doc.get("reprovacao_motivo"), ""),
                bool(doc.get("tem_variacoes")),
                _f(doc.get("produto"), ""), _f(doc.get("objetivo_projeto"), ""),
                _f(doc.get("aplicacoes_desenvolver"), ""), _f(doc.get("ativos_claims"), ""),
                _f(doc.get("referencias"), ""), _f(doc.get("orcamento_projeto"), ""),
                _f(doc.get("textura_esperada"), ""), _f(doc.get("aplicacao"), ""),
                _f(doc.get("sensorial"), ""), _f(doc.get("ph"), ""),
                _f(doc.get("observacao_tecnica"), ""),
                _f(doc.get("created_by"), ""), _f(doc.get("created_by_name"), ""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("variacoes") or [],
                doc.get("projeto_briefing") or {},
                doc.get("referencias_fotos") or [],
                doc.get("historico_movimentacoes") or [],
            )
            count += 1
        except Exception as e:
            print(f"  ERRO crm_samples {doc.get('id')}: {e}")
    print(f"  {count} crm_samples migrados")

    # ─── skus ─────────────────────────────────────────────────────────────────
    print("\n-- Migrando skus --")
    count = 0
    async for doc in mdb.skus.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO skus(
                  id, tenant_id, codigo_interno, cat2, cat3, cli3, cli4, nome_produto,
                  categoria, formula_vinculada, cliente_id, cliente_nome,
                  projeto_id, projeto_nome, amostra_id, amostra_variacao_id, produto_pai_id,
                  descricao_aplicacao, preco_unitario, preco_unitario_currency, moq, status,
                  descontinuado_motivo, descontinuado_em, descontinuado_por,
                  data_ultimo_pedido, frequencia_media_recompra_dias,
                  created_at, updated_at,
                  anvisa, medias_producao, historico_pedidos
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                  $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32
                )
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("codigo_interno"), ""), _f(doc.get("cat2"), ""),
                _f(doc.get("cat3"), ""), _f(doc.get("cli3"), ""), _f(doc.get("cli4"), ""),
                _f(doc.get("nome_produto"), ""), _f(doc.get("categoria"), ""),
                _f(doc.get("formula_vinculada"), ""),
                _f(doc.get("cliente_id"), ""), _f(doc.get("cliente_nome"), ""),
                _f(doc.get("projeto_id"), ""), _f(doc.get("projeto_nome"), ""),
                _f(doc.get("amostra_id"), ""), _f(doc.get("amostra_variacao_id"), ""),
                doc.get("produto_pai_id"),
                _f(doc.get("descricao_aplicacao"), ""),
                _f(doc.get("preco_unitario"), 0.0), _f(doc.get("preco_unitario_currency"), "BRL"),
                _f(doc.get("moq"), 0), _f(doc.get("status"), "ativo"),
                doc.get("descontinuado_motivo"), doc.get("descontinuado_em"),
                doc.get("descontinuado_por"), doc.get("data_ultimo_pedido"),
                _f(doc.get("frequencia_media_recompra_dias"), 0),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("anvisa") or {"numero": "", "validade": None},
                doc.get("medias_producao") or {},
                doc.get("historico_pedidos") or [],
            )
            count += 1
        except Exception as e:
            print(f"  ERRO skus {doc.get('id')}: {e}")
    print(f"  {count} skus migrados")

    # ─── crm_alerts ──────────────────────────────────────────────────────────
    print("\n-- Migrando crm_alerts --")
    count = 0
    async for doc in mdb.crm_alerts.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO crm_alerts(
                  id, tenant_id, tipo, entidade_ref, entidade_tipo, entidade_nome,
                  mensagem, data_criacao, status, responsavel,
                  resolved_at, resolved_by, resolved_comment, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("tipo"), ""), _f(doc.get("entidade_ref"), ""),
                _f(doc.get("entidade_tipo"), ""), _f(doc.get("entidade_nome"), ""),
                _f(doc.get("mensagem"), ""), _f(doc.get("data_criacao"), ""),
                _f(doc.get("status"), "pendente"), _f(doc.get("responsavel"), ""),
                doc.get("resolved_at"), doc.get("resolved_by"),
                doc.get("resolved_comment"),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO crm_alerts {doc.get('id')}: {e}")
    print(f"  {count} crm_alerts migrados")

    # ─── crm_column_configs ───────────────────────────────────────────────────
    print("\n-- Migrando crm_column_configs --")
    count = 0
    async for doc in mdb.crm_column_configs.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO crm_column_configs(
                  id, tenant_id, crm_type, key, label, color, "order", is_system, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("crm_type"), ""), _f(doc.get("key"), ""),
                _f(doc.get("label"), ""), _f(doc.get("color"), ""),
                _f(doc.get("order"), 0), bool(doc.get("is_system")),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO crm_column_configs {doc.get('id')}: {e}")
    print(f"  {count} crm_column_configs migrados")

    # ─── crm_field_configs ────────────────────────────────────────────────────
    print("\n-- Migrando crm_field_configs --")
    count = 0
    async for doc in mdb.crm_field_configs.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO crm_field_configs(
                  id, tenant_id, column_id, label, type, required, "order", created_at, options
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("column_id"), ""), _f(doc.get("label"), ""),
                _f(doc.get("type"), ""), bool(doc.get("required")),
                _f(doc.get("order"), 0),
                _parse_dt(doc.get("created_at")),
                doc.get("options") or [],
            )
            count += 1
        except Exception as e:
            print(f"  ERRO crm_field_configs {doc.get('id')}: {e}")
    print(f"  {count} crm_field_configs migrados")

    # ─── lead_sources ─────────────────────────────────────────────────────────
    print("\n-- Migrando lead_sources --")
    count = 0
    async for doc in mdb.lead_sources.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO lead_sources(
                  id, tenant_id, valor, nome, grupo, ativo, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), _f(doc.get("tenant_id"), ""),
                _f(doc.get("valor"), ""), _f(doc.get("nome"), ""),
                _f(doc.get("grupo"), ""), bool(doc.get("ativo", True)),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO lead_sources {doc.get('id')}: {e}")
    print(f"  {count} lead_sources migrados")

    await pg.close()
    print("\nMigracao CRM concluida com sucesso.")


if __name__ == "__main__":
    asyncio.run(main())
