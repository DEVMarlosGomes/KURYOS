"""
migrate_cq.py — Backfill de dados CQ do MongoDB para PostgreSQL.

A maioria das coleções CQ começa vazia; este script:
1. Semeia os contadores no PostgreSQL para evitar colisões com sequences futuras.
2. Migra documentos existentes com ON CONFLICT DO NOTHING (idempotente).

Uso:
    cd backend
    python ../migrations/migrate_cq.py
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


# CQ counter keys used by next_sequence_pg
CQ_COUNTER_KEYS = [
    "cq_ra", "cq_rnc", "cq_ret", "cq_ck", "cq_instr",
]


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
    print("\n— Sincronizando contadores CQ —")
    tenant_ids = []
    async for t in mdb.tenants.find({}, {"_id": 0, "id": 1}):
        if t.get("id"):
            tenant_ids.append(t["id"])
    # Also get from PostgreSQL tenants table
    pg_tenants = await pg.fetch("SELECT id FROM tenants")
    for row in pg_tenants:
        if row["id"] not in tenant_ids:
            tenant_ids.append(row["id"])

    year = datetime.utcnow().year
    for tenant_id in tenant_ids:
        for key in CQ_COUNTER_KEYS:
            mongo_key = f"{key}_{year}"
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
                await pg.execute(
                    "UPDATE counters SET seq=$1, updated_at=NOW() WHERE id=$2",
                    mongo_seq, pg_key,
                )
                print(f"  [sync] {pg_key}: {existing} → {mongo_seq}")

    # ─── Migrate cq_registros_analise ─────────────────────────────────────────
    print("\n— Migrando cq_registros_analise —")
    count_ra = 0
    async for doc in mdb.cq_registros_analise.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO cq_registros_analise(
                  id, tenant_id, numero_ra, tipo, status,
                  lote_id, lote_numero, item_id, item_nome, item_tipo,
                  fornecedor_id, fornecedor_nome, nf_numero, nf_data,
                  quantidade_recebida, unidade, numero_lote_fornecedor,
                  data_fabricacao_fornecedor, data_validade_fornecedor,
                  parametros, resultado_geral,
                  analista_id, analista_nome, data_analise,
                  fotos_file_ids, amostra_retencao_id, rnc_id,
                  coa_gerado, coa_enviado_cliente, coa_enviado_em,
                  created_at, updated_at, log_auditoria
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                  $11,$12,$13,$14,$15,$16,$17,$18,$19,
                  $20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,
                  $31,$32,$33
                ) ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("numero_ra"), doc.get("tipo"), doc.get("status", "rascunho"),
                doc.get("lote_id"), doc.get("lote_numero"),
                doc.get("item_id"), doc.get("item_nome"), doc.get("item_tipo"),
                doc.get("fornecedor_id"), doc.get("fornecedor_nome"),
                doc.get("nf_numero"), doc.get("nf_data"),
                doc.get("quantidade_recebida"), doc.get("unidade"),
                doc.get("numero_lote_fornecedor"),
                doc.get("data_fabricacao_fornecedor"), doc.get("data_validade_fornecedor"),
                doc.get("parametros", []), doc.get("resultado_geral"),
                doc.get("analista_id"), doc.get("analista_nome"), doc.get("data_analise"),
                doc.get("fotos_file_ids", []), doc.get("amostra_retencao_id"), doc.get("rnc_id"),
                doc.get("coa_gerado", False), doc.get("coa_enviado_cliente", False),
                doc.get("coa_enviado_em"),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("log_auditoria", []),
            )
            count_ra += 1
        except Exception as e:
            print(f"  ERRO RA {doc.get('id')}: {e}")
    print(f"  {count_ra} RAs migrados")

    # ─── Migrate cq_checklists ────────────────────────────────────────────────
    print("\n— Migrando cq_checklists —")
    count_ck = 0
    async for doc in mdb.cq_checklists.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO cq_checklists(
                  id, tenant_id, numero_ck, tipo, nome, status,
                  op_id, op_numero, lote_id, linha, turno,
                  subtipo_insumo, horario_previsto_ronda, ra_id,
                  itens, ncs_identificadas, rncs_geradas,
                  preenchido_por_id, preenchido_por_nome,
                  aprovado_por_id, aprovado_por_nome, aprovado_em,
                  created_at, updated_at, log_auditoria
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                  $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                  $21,$22,$23,$24,$25
                ) ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("numero_ck"), doc.get("tipo"), doc.get("nome"),
                doc.get("status", "em_preenchimento"),
                doc.get("op_id"), doc.get("op_numero"),
                doc.get("lote_id"), doc.get("linha"), doc.get("turno"),
                doc.get("subtipo_insumo"), doc.get("horario_previsto_ronda"), doc.get("ra_id"),
                doc.get("itens", []), doc.get("ncs_identificadas", 0),
                doc.get("rncs_geradas", []),
                doc.get("preenchido_por_id"), doc.get("preenchido_por_nome"),
                doc.get("aprovado_por_id"), doc.get("aprovado_por_nome"), doc.get("aprovado_em"),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("log_auditoria", []),
            )
            count_ck += 1
        except Exception as e:
            print(f"  ERRO CK {doc.get('id')}: {e}")
    print(f"  {count_ck} Checklists migrados")

    # ─── Migrate cq_rncs ──────────────────────────────────────────────────────
    print("\n— Migrando cq_rncs —")
    count_rnc = 0
    async for doc in mdb.cq_rncs.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO cq_rncs(
                  id, tenant_id, numero_rnc, classificacao, origem,
                  descricao, status, ra_id, ck_id,
                  lote_id, lote_numero, item_nome,
                  fornecedor_id, fornecedor_nome, quantidade_afetada,
                  fotos_file_ids, disposicao_imediata,
                  responsavel_id, responsavel_nome, prazo_resolucao,
                  comunicado_fornecedor_enviado, comunicado_enviado_em,
                  resposta_fornecedor, capa_descricao, evidencia_resolucao,
                  encerrado_por_id, encerrado_em, autorizacao_concessao,
                  created_at, updated_at, log_auditoria
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                  $11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                  $21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31
                ) ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("numero_rnc"), doc.get("classificacao"), doc.get("origem"),
                doc.get("descricao"), doc.get("status", "aberta"),
                doc.get("ra_id"), doc.get("ck_id"),
                doc.get("lote_id"), doc.get("lote_numero"), doc.get("item_nome"),
                doc.get("fornecedor_id"), doc.get("fornecedor_nome"),
                doc.get("quantidade_afetada"),
                doc.get("fotos_file_ids", []), doc.get("disposicao_imediata"),
                doc.get("responsavel_id"), doc.get("responsavel_nome"),
                doc.get("prazo_resolucao"),
                doc.get("comunicado_fornecedor_enviado", False),
                doc.get("comunicado_enviado_em"),
                doc.get("resposta_fornecedor"), doc.get("capa_descricao"),
                doc.get("evidencia_resolucao"),
                doc.get("encerrado_por_id"), doc.get("encerrado_em"),
                doc.get("autorizacao_concessao"),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
                doc.get("log_auditoria", []),
            )
            count_rnc += 1
        except Exception as e:
            print(f"  ERRO RNC {doc.get('id')}: {e}")
    print(f"  {count_rnc} RNCs migradas")

    # ─── Migrate cq_retencoes ─────────────────────────────────────────────────
    print("\n— Migrando cq_retencoes —")
    count_ret = 0
    async for doc in mdb.cq_retencoes.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO cq_retencoes(
                  id, tenant_id, numero_ret, tipo, ra_id,
                  lote_id, lote_numero, item_nome, fornecedor_nome,
                  quantidade_retida, unidade, localizacao_fisica,
                  data_coleta, data_limite_guarda, status,
                  created_at, updated_at
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                  $11,$12,$13,$14,$15,$16,$17
                ) ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("numero_ret"), doc.get("tipo"), doc.get("ra_id"),
                doc.get("lote_id"), doc.get("lote_numero"),
                doc.get("item_nome"), doc.get("fornecedor_nome"),
                doc.get("quantidade_retida"), doc.get("unidade"),
                doc.get("localizacao_fisica"),
                doc.get("data_coleta"), doc.get("data_limite_guarda"),
                doc.get("status", "em_guarda"),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count_ret += 1
        except Exception as e:
            print(f"  ERRO RET {doc.get('id')}: {e}")
    print(f"  {count_ret} Retenções migradas")

    # ─── Migrate cq_instrumentos ──────────────────────────────────────────────
    print("\n— Migrando cq_instrumentos —")
    count_instr = 0
    async for doc in mdb.cq_instrumentos.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO cq_instrumentos(
                  id, tenant_id, nome, codigo_interno, tipo,
                  localizacao, frequencia_calibracao_dias,
                  ultima_calibracao, proxima_calibracao, status,
                  certificado_file_id, historico_calibracoes,
                  created_at, updated_at
                ) VALUES(
                  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14
                ) ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("nome"), doc.get("codigo_interno"),
                doc.get("tipo"), doc.get("localizacao"),
                doc.get("frequencia_calibracao_dias"),
                doc.get("ultima_calibracao"), doc.get("proxima_calibracao"),
                doc.get("status", "calibrado"),
                doc.get("certificado_file_id"),
                doc.get("historico_calibracoes", []),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count_instr += 1
        except Exception as e:
            print(f"  ERRO INSTR {doc.get('id')}: {e}")
    print(f"  {count_instr} Instrumentos migrados")

    # ─── Migrate cq_status_lote ───────────────────────────────────────────────
    print("\n— Migrando cq_status_lote —")
    count_sl = 0
    async for doc in mdb.cq_status_lote.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO cq_status_lote(
                  id, tenant_id, lote_id, lote_numero,
                  status_anterior, status_novo, motivo,
                  ra_id, rnc_id, alterado_por_id, alterado_por_nome,
                  created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id", ""), doc.get("tenant_id", ""),
                doc.get("lote_id"), doc.get("lote_numero"),
                doc.get("status_anterior"), doc.get("status_novo"),
                doc.get("motivo"),
                doc.get("ra_id"), doc.get("rnc_id"),
                doc.get("alterado_por_id"), doc.get("alterado_por_nome"),
                _parse_dt(doc.get("created_at")),
            )
            count_sl += 1
        except Exception as e:
            print(f"  ERRO SL {doc.get('id')}: {e}")
    print(f"  {count_sl} Status-lote migrados")

    await pg.close()
    print("\nMigracao CQ concluida com sucesso.")


def _parse_dt(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


if __name__ == "__main__":
    asyncio.run(main())
