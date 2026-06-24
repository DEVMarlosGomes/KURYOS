"""
migrate_pd.py — Backfill das 25 coleções P&D do MongoDB para PostgreSQL.

Uso:
    cd backend
    python ../migrations/migrate_pd.py
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


PD_COUNTER_KEYS = [
    "lab_mp_seq",
    "lab_in_seq",
    "lab_am_seq",
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

    # ─── Seed counters ────────────────────────────────────────────────────────
    print("\n-- Sincronizando contadores P&D --")
    tenant_ids = []
    async for t in mdb.tenants.find({}, {"_id": 0, "id": 1}):
        if t.get("id"):
            tenant_ids.append(t["id"])
    pg_tenants = await pg.fetch("SELECT id FROM tenants")
    for row in pg_tenants:
        if row["id"] not in tenant_ids:
            tenant_ids.append(row["id"])

    for tenant_id in tenant_ids:
        for key in PD_COUNTER_KEYS:
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

    # ─── pd_requests ─────────────────────────────────────────────────────────
    print("\n-- Migrando pd_requests --")
    count = 0
    async for doc in mdb.pd_requests.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_requests(
                  id, tenant_id, client_card_id, client_name,
                  project_name, technical_name, commercial_name, internal_code,
                  request_type, category, description, "references", restrictions,
                  volume, packaging, priority, deadline, status,
                  is_internal_research, kickoff_completed, amostra_id,
                  created_by, created_by_name, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), doc.get("tenant_id",""),
                doc.get("client_card_id"), _f(doc.get("client_name"),""),
                _f(doc.get("project_name"),""), _f(doc.get("technical_name"),""),
                _f(doc.get("commercial_name"),""), _f(doc.get("internal_code"),""),
                _f(doc.get("request_type"),""), _f(doc.get("category"),""),
                _f(doc.get("description"),""), _f(doc.get("references"),""),
                _f(doc.get("restrictions"),""), _f(doc.get("volume"),""),
                _f(doc.get("packaging"),""), _f(doc.get("priority"),"Normal"),
                doc.get("deadline"), _f(doc.get("status"),"OPEN"),
                bool(doc.get("is_internal_research")), bool(doc.get("kickoff_completed")),
                doc.get("amostra_id"),
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_requests {doc.get('id')}: {e}")
    print(f"  {count} pd_requests migrados")

    # ─── pd_request_status_history ───────────────────────────────────────────
    print("\n-- Migrando pd_request_status_history --")
    count = 0
    async for doc in mdb.pd_request_status_history.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_request_status_history(
                  id, tenant_id, pd_request_id, from_status, to_status,
                  changed_by, changed_by_name, comment, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(id) DO NOTHING
                """,
                _f(doc.get("id"), str(doc.get("_id",""))),
                _f(doc.get("tenant_id"),""),
                doc.get("pd_request_id",""),
                doc.get("from_status"),
                _f(doc.get("to_status"),"OPEN"),
                doc.get("changed_by"), _f(doc.get("changed_by_name"),""),
                _f(doc.get("comment"),""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_request_status_history {doc.get('id')}: {e}")
    print(f"  {count} registros status_history migrados")

    # ─── pd_developments ─────────────────────────────────────────────────────
    print("\n-- Migrando pd_developments --")
    count = 0
    async for doc in mdb.pd_developments.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_developments(
                  id, tenant_id, pd_request_id, assigned_to, assigned_to_name,
                  lab_responsible, current_version, status, started_at, completed_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("pd_request_id",""),
                doc.get("assigned_to"), _f(doc.get("assigned_to_name"),""),
                doc.get("lab_responsible"),
                _f(doc.get("current_version"), 0),
                _f(doc.get("status"),"active"),
                doc.get("started_at"), doc.get("completed_at"),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_developments {doc.get('id')}: {e}")
    print(f"  {count} pd_developments migrados")

    # ─── pd_formulas ─────────────────────────────────────────────────────────
    print("\n-- Migrando pd_formulas --")
    count = 0
    async for doc in mdb.pd_formulas.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_formulas(
                  id, tenant_id, development_id, version, name, notes,
                  volume, volume_unit, indice_perdas, cotacao_usd, fragrance_target,
                  locked, locked_at, locked_by, locked_by_name,
                  created_by, created_by_name, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("development_id",""),
                _f(doc.get("version"), 1),
                _f(doc.get("name"),""), _f(doc.get("notes"),""),
                _f(doc.get("volume"), 0), _f(doc.get("volume_unit"),"mL"),
                _f(doc.get("indice_perdas"), 0), _f(doc.get("cotacao_usd"), 6.0),
                doc.get("fragrance_target"),
                bool(doc.get("locked")),
                doc.get("locked_at"), doc.get("locked_by"),
                _f(doc.get("locked_by_name"),""),
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_formulas {doc.get('id')}: {e}")
    print(f"  {count} pd_formulas migradas")

    # ─── pd_formula_items ────────────────────────────────────────────────────
    print("\n-- Migrando pd_formula_items --")
    count = 0
    async for doc in mdb.pd_formula_items.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_formula_items(
                  id, formula_id, ingredient_name, percentage,
                  price_per_kg, price_usd, cost_brl, cost_kg_usd, cost_brl_via_cambio,
                  fornecedor, phase, "function", catalog_id
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), doc.get("formula_id",""),
                _f(doc.get("ingredient_name"),""),
                _f(doc.get("percentage"), 0),
                _f(doc.get("price_per_kg"), 0), doc.get("price_usd"),
                _f(doc.get("cost_brl"), 0), doc.get("cost_kg_usd"),
                doc.get("cost_brl_via_cambio"),
                _f(doc.get("fornecedor"),""), _f(doc.get("phase"),""),
                _f(doc.get("function"),""), doc.get("catalog_id"),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_formula_items {doc.get('id')}: {e}")
    print(f"  {count} pd_formula_items migrados")

    # ─── pd_tests ────────────────────────────────────────────────────────────
    print("\n-- Migrando pd_tests --")
    count = 0
    async for doc in mdb.pd_tests.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_tests(
                  id, tenant_id, development_id, test_type, dados, status,
                  created_by, created_by_name, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("development_id",""),
                _f(doc.get("test_type"),""),
                doc.get("dados") or {},
                _f(doc.get("status"),"PENDING"),
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_tests {doc.get('id')}: {e}")
    print(f"  {count} pd_tests migrados")

    # ─── pd_lab_results ──────────────────────────────────────────────────────
    print("\n-- Migrando pd_lab_results --")
    count = 0
    async for doc in mdb.pd_lab_results.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_lab_results(
                  id, tenant_id, development_id,
                  estabilidade, ph, viscosidade, sensorial, compatibilidade, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(id) DO NOTHING
                """,
                _f(doc.get("id"), doc.get("development_id","")),
                _f(doc.get("tenant_id"),""),
                doc.get("development_id",""),
                doc.get("estabilidade") or {},
                doc.get("ph") or {},
                doc.get("viscosidade") or {},
                doc.get("sensorial") or {},
                doc.get("compatibilidade") or {},
                _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_lab_results {doc.get('id')}: {e}")
    print(f"  {count} pd_lab_results migrados")

    # ─── pd_stability_studies ────────────────────────────────────────────────
    print("\n-- Migrando pd_stability_studies --")
    count = 0
    async for doc in mdb.pd_stability_studies.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_stability_studies(
                  id, tenant_id, pd_card_id, amostra_id, amostra_variacao_id,
                  status, conditions, d0_completed, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("pd_card_id"), doc.get("amostra_id"),
                doc.get("amostra_variacao_id"),
                _f(doc.get("status"),"ativo"),
                doc.get("conditions") or [],
                bool(doc.get("d0_completed")),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_stability_studies {doc.get('id')}: {e}")
    print(f"  {count} pd_stability_studies migrados")

    # ─── pd_stability_readings ───────────────────────────────────────────────
    print("\n-- Migrando pd_stability_readings --")
    count = 0
    async for doc in mdb.pd_stability_readings.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_stability_readings(
                  id, tenant_id, study_id, pd_card_id, amostra_id, amostra_variacao_id,
                  condition_code, condition_label, day_offset, reading_at,
                  parameters, notes, photo_urls, created_at, created_by, created_by_name
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("study_id",""), doc.get("pd_card_id"),
                doc.get("amostra_id"), doc.get("amostra_variacao_id"),
                _f(doc.get("condition_code"),""),
                _f(doc.get("condition_label"),""),
                _f(doc.get("day_offset"), 0),
                doc.get("reading_at"),
                doc.get("parameters") or {},
                _f(doc.get("notes"),""),
                doc.get("photo_urls") or [],
                _parse_dt(doc.get("created_at")),
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_stability_readings {doc.get('id')}: {e}")
    print(f"  {count} pd_stability_readings migrados")

    # ─── pd_samples ──────────────────────────────────────────────────────────
    print("\n-- Migrando pd_samples --")
    count = 0
    async for doc in mdb.pd_samples.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_samples(
                  id, tenant_id, development_id, formula_version,
                  sent_to_client, sent_at, feedback,
                  internal_approved, client_approved, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("development_id",""),
                doc.get("formula_version"),
                bool(doc.get("sent_to_client")), doc.get("sent_at"),
                _f(doc.get("feedback"),""),
                bool(doc.get("internal_approved")),
                bool(doc.get("client_approved")),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_samples {doc.get('id')}: {e}")
    print(f"  {count} pd_samples migrados")

    # ─── pd_approvals ────────────────────────────────────────────────────────
    print("\n-- Migrando pd_approvals --")
    count = 0
    async for doc in mdb.pd_approvals.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_approvals(
                  id, tenant_id, development_id, pd_request_id,
                  approved_by_client, approved_by_internal, approved_by_comercial,
                  approved_by_comercial_id, approved_by_comercial_name,
                  approval_date, approved_at, notes,
                  approved_by_user, approved_by_user_name,
                  created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("development_id",""), doc.get("pd_request_id"),
                bool(doc.get("approved_by_client")),
                bool(doc.get("approved_by_internal")),
                bool(doc.get("approved_by_comercial")),
                doc.get("approved_by_comercial_id"),
                _f(doc.get("approved_by_comercial_name"),""),
                doc.get("approval_date"), doc.get("approved_at"),
                _f(doc.get("notes"),""),
                doc.get("approved_by_user"),
                _f(doc.get("approved_by_user_name"),""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_approvals {doc.get('id')}: {e}")
    print(f"  {count} pd_approvals migrados")

    # ─── pd_costs ────────────────────────────────────────────────────────────
    print("\n-- Migrando pd_costs --")
    count = 0
    async for doc in mdb.pd_costs.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_costs(
                  id, tenant_id, development_id,
                  ingredient_cost, packaging_cost, labor_cost, total_cost, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("development_id",""),
                _f(doc.get("ingredient_cost"), 0),
                _f(doc.get("packaging_cost"), 0),
                _f(doc.get("labor_cost"), 0),
                _f(doc.get("total_cost"), 0),
                _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_costs {doc.get('id')}: {e}")
    print(f"  {count} pd_costs migrados")

    # ─── pd_cost_versions ────────────────────────────────────────────────────
    print("\n-- Migrando pd_cost_versions --")
    count = 0
    async for doc in mdb.pd_cost_versions.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_cost_versions(
                  id, tenant_id, development_id, v1, v2, total_final, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT(id) DO NOTHING
                """,
                _f(doc.get("id"), doc.get("development_id","")),
                _f(doc.get("tenant_id"),""),
                doc.get("development_id",""),
                doc.get("v1") or {},
                doc.get("v2"),
                _f(doc.get("total_final"), 0),
                _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_cost_versions {doc.get('id')}: {e}")
    print(f"  {count} pd_cost_versions migrados")

    # ─── pd_documents ────────────────────────────────────────────────────────
    print("\n-- Migrando pd_documents --")
    count = 0
    async for doc in mdb.pd_documents.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_documents(
                  id, tenant_id, development_id, doc_type,
                  file_url, file_name, uploaded_by, uploaded_by_name, uploaded_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("development_id",""),
                _f(doc.get("doc_type"),""),
                _f(doc.get("file_url"),""), _f(doc.get("file_name"),""),
                doc.get("uploaded_by"), _f(doc.get("uploaded_by_name"),""),
                _parse_dt(doc.get("uploaded_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_documents {doc.get('id')}: {e}")
    print(f"  {count} pd_documents migrados")

    # ─── pd_document_versions ────────────────────────────────────────────────
    print("\n-- Migrando pd_document_versions --")
    count = 0
    async for doc in mdb.pd_document_versions.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_document_versions(
                  id, tenant_id, pd_request_id, doc_type, version_number,
                  status, active_for_operation, snapshot,
                  changed_fields, source_changes, reason, trigger,
                  created_by, created_by_name, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("pd_request_id",""), _f(doc.get("doc_type"),""),
                _f(doc.get("version_number"), 1),
                _f(doc.get("status"),"rascunho"),
                bool(doc.get("active_for_operation")),
                doc.get("snapshot") or {},
                doc.get("changed_fields") or [],
                doc.get("source_changes") or [],
                _f(doc.get("reason"),""),
                _f(doc.get("trigger"),"manual"),
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_document_versions {doc.get('id')}: {e}")
    print(f"  {count} pd_document_versions migrados")

    # ─── pd_catalog ──────────────────────────────────────────────────────────
    print("\n-- Migrando pd_catalog --")
    count = 0
    async for doc in mdb.pd_catalog.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_catalog(
                  id, tenant_id, nome, inci, codigo_interno,
                  fornecedor, preco_rs_kg, moeda, unidade, categoria, observacoes,
                  fornecedores, ultima_atualizacao,
                  atualizado_por, atualizado_por_id,
                  created_by, created_by_name, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                _f(doc.get("nome"),""), _f(doc.get("inci"),""),
                _f(doc.get("codigo_interno"),""),
                _f(doc.get("fornecedor"),""),
                _f(doc.get("preco_rs_kg"), 0),
                _f(doc.get("moeda"),"BRL"), _f(doc.get("unidade"),"kg"),
                _f(doc.get("categoria"),""), _f(doc.get("observacoes"),""),
                doc.get("fornecedores") or [],
                doc.get("ultima_atualizacao"),
                _f(doc.get("atualizado_por"),""),
                doc.get("atualizado_por_id"),
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_catalog {doc.get('id')}: {e}")
    print(f"  {count} pd_catalog migrados")

    # ─── pd_catalog_price_history ────────────────────────────────────────────
    print("\n-- Migrando pd_catalog_price_history --")
    count = 0
    async for doc in mdb.pd_catalog_price_history.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_catalog_price_history(
                  id, tenant_id, catalog_item_id,
                  preco_anterior, preco_novo, moeda,
                  atualizado_por, atualizado_por_id, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("catalog_item_id",""),
                _f(doc.get("preco_anterior"), 0),
                _f(doc.get("preco_novo"), 0),
                _f(doc.get("moeda"),"BRL"),
                _f(doc.get("atualizado_por"),""),
                doc.get("atualizado_por_id"),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_catalog_price_history {doc.get('id')}: {e}")
    print(f"  {count} pd_catalog_price_history migrados")

    # ─── pd_cards ────────────────────────────────────────────────────────────
    print("\n-- Migrando pd_cards --")
    count = 0
    async for doc in mdb.pd_cards.find({}, {"_id": 0}):
        try:
            extra = {k: v for k, v in doc.items() if k not in {
                "id","tenant_id","amostra_id","amostra_variacao_id","pd_request_id",
                "status_pd","executor_id","executor_name","atribuido_em",
                "atribuido_por","atribuido_por_nome","created_at","updated_at","_id",
            }}
            await pg.execute(
                """
                INSERT INTO pd_cards(
                  id, tenant_id, amostra_id, amostra_variacao_id, pd_request_id,
                  status_pd, executor_id, executor_name, atribuido_em,
                  atribuido_por, atribuido_por_nome, extra, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("amostra_id"), doc.get("amostra_variacao_id"),
                doc.get("pd_request_id"),
                _f(doc.get("status_pd"),"solicitado"),
                doc.get("executor_id"), _f(doc.get("executor_name"),""),
                doc.get("atribuido_em"), doc.get("atribuido_por"),
                _f(doc.get("atribuido_por_nome"),""),
                extra or {},
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_cards {doc.get('id')}: {e}")
    print(f"  {count} pd_cards migrados")

    # ─── pd_ficha_tecnica ────────────────────────────────────────────────────
    print("\n-- Migrando pd_ficha_tecnica --")
    count = 0
    async for doc in mdb.pd_ficha_tecnica.find({}, {"_id": 0}):
        try:
            conteudo = {k: v for k, v in doc.items() if k not in {"id","tenant_id","pd_request_id","versao","created_at","updated_at","_id"}}
            await pg.execute(
                """
                INSERT INTO pd_ficha_tecnica(
                  id, tenant_id, pd_request_id, conteudo, versao, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("pd_request_id",""),
                conteudo,
                _f(doc.get("versao"), 1),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_ficha_tecnica {doc.get('id')}: {e}")
    print(f"  {count} pd_ficha_tecnica migrados")

    # ─── pd_stock_items ──────────────────────────────────────────────────────
    print("\n-- Migrando pd_stock_items --")
    count = 0
    async for doc in mdb.pd_stock_items.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_stock_items(
                  id, tenant_id, nome, codigo_interno, categoria, unidade,
                  quantidade_atual, quantidade_minima, validade, lote,
                  custo_unitario, fornecedor, observacoes, catalog_id,
                  formula_ref, fragrancia_percentual,
                  linked_pd_request_id, linked_formula_id,
                  created_by, created_by_name, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                _f(doc.get("nome"),""),
                _f(doc.get("codigo_interno"),""),
                _f(doc.get("categoria"),""),
                _f(doc.get("unidade_medida") or doc.get("unidade"),""),
                _f(doc.get("quantidade_atual"), 0),
                _f(doc.get("quantidade_minima"), 0),
                doc.get("validade"), _f(doc.get("lote"),""),
                _f(doc.get("custo_unitario"), 0),
                _f(doc.get("fornecedor"),""),
                _f(doc.get("observacoes"),""),
                doc.get("catalog_id"),
                _f(doc.get("formula_ref"),""),
                doc.get("fragrancia_percentual"),
                doc.get("linked_pd_request_id"),
                doc.get("linked_formula_id"),
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_stock_items {doc.get('id')}: {e}")
    print(f"  {count} pd_stock_items migrados")

    # ─── pd_stock_movements ──────────────────────────────────────────────────
    print("\n-- Migrando pd_stock_movements --")
    count = 0
    async for doc in mdb.pd_stock_movements.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_stock_movements(
                  id, tenant_id, stock_item_id, tipo, quantidade,
                  quantidade_antes, quantidade_depois, motivo, lote,
                  user_id, user_name, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("stock_item_id",""),
                _f(doc.get("tipo"),"entrada"),
                _f(doc.get("quantidade"), 0),
                _f(doc.get("quantidade_antes"), 0),
                _f(doc.get("quantidade_depois"), 0),
                _f(doc.get("motivo"),""),
                doc.get("lote"),
                doc.get("user_id"), _f(doc.get("user_name"),""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_stock_movements {doc.get('id')}: {e}")
    print(f"  {count} pd_stock_movements migrados")

    # ─── pd_updates ──────────────────────────────────────────────────────────
    print("\n-- Migrando pd_updates --")
    count = 0
    async for doc in mdb.pd_updates.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_updates(
                  id, tenant_id, pd_request_id, tipo, mensagem,
                  visivel_comercial, recebido, recebido_em,
                  user_id, user_name, user_role, pending_item_id, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("pd_request_id",""),
                _f(doc.get("tipo"),"observacao"),
                _f(doc.get("mensagem"),""),
                bool(doc.get("visivel_comercial")),
                bool(doc.get("recebido")),
                doc.get("recebido_em"),
                doc.get("user_id"), _f(doc.get("user_name"),""),
                _f(doc.get("user_role"),""),
                doc.get("pending_item_id"),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_updates {doc.get('id')}: {e}")
    print(f"  {count} pd_updates migrados")

    # ─── pd_pending_items ────────────────────────────────────────────────────
    print("\n-- Migrando pd_pending_items --")
    count = 0
    async for doc in mdb.pd_pending_items.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_pending_items(
                  id, tenant_id, pd_request_id, tipo, descricao,
                  data_solicitacao, data_prevista, data_recebido,
                  fornecedor, observacoes, status,
                  user_id, user_name, created_at, updated_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("pd_request_id",""),
                _f(doc.get("tipo"),""),
                _f(doc.get("descricao"),""),
                doc.get("data_solicitacao"), doc.get("data_prevista"),
                doc.get("data_recebido"),
                _f(doc.get("fornecedor"),""),
                _f(doc.get("observacoes"),""),
                _f(doc.get("status"),"pendente"),
                doc.get("user_id"), _f(doc.get("user_name"),""),
                _parse_dt(doc.get("created_at")), _parse_dt(doc.get("updated_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_pending_items {doc.get('id')}: {e}")
    print(f"  {count} pd_pending_items migrados")

    # ─── pd_sample_batches ───────────────────────────────────────────────────
    print("\n-- Migrando pd_sample_batches --")
    count = 0
    async for doc in mdb.pd_sample_batches.find({}, {"_id": 0}):
        try:
            conteudo = {k: v for k, v in doc.items() if k not in {
                "id","tenant_id","development_id","created_by","created_by_name","created_at","_id"
            }}
            await pg.execute(
                """
                INSERT INTO pd_sample_batches(
                  id, tenant_id, development_id, conteudo,
                  created_by, created_by_name, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                _f(doc.get("development_id"),""),
                conteudo,
                doc.get("created_by"), _f(doc.get("created_by_name"),""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_sample_batches {doc.get('id')}: {e}")
    print(f"  {count} pd_sample_batches migrados")

    # ─── pd_batch_orders ─────────────────────────────────────────────────────
    print("\n-- Migrando pd_batch_orders --")
    count = 0
    async for doc in mdb.pd_batch_orders.find({}, {"_id": 0}):
        try:
            await pg.execute(
                """
                INSERT INTO pd_batch_orders(
                  id, tenant_id, ordem_numero, amostra_ids,
                  volume_por_amostra_ml, n_amostras,
                  base_compartilhada, ingredientes_por_variacao,
                  observacao, criado_por, criado_por_nome, created_at
                ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT(id) DO NOTHING
                """,
                doc.get("id",""), _f(doc.get("tenant_id"),""),
                doc.get("ordem_numero"),
                doc.get("amostra_ids") or [],
                _f(doc.get("volume_por_amostra_ml"), 0),
                _f(doc.get("n_amostras"), 0),
                doc.get("base_compartilhada") or [],
                doc.get("ingredientes_por_variacao") or {},
                _f(doc.get("observacao"),""),
                doc.get("criado_por"), _f(doc.get("criado_por_nome"),""),
                _parse_dt(doc.get("created_at")),
            )
            count += 1
        except Exception as e:
            print(f"  ERRO pd_batch_orders {doc.get('id')}: {e}")
    print(f"  {count} pd_batch_orders migrados")

    await pg.close()
    print("\nMigracao P&D concluida com sucesso.")


if __name__ == "__main__":
    asyncio.run(main())
