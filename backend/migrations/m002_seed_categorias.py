"""
Migration m002 — Seed initial product categories (R22)

Seeds db.categorias with the canonical list of categories that were
previously hardcoded in CATEGORIA_INTERESSE_OPTIONS. All seeded records
are inserted as status='ativa' (already approved — system defaults).

Idempotent: categories already present by cat3 are skipped.
Run:
    cd backend && python -m migrations.m002_seed_categorias
"""

import asyncio
import motor.motor_asyncio

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "kuryos"

# Same as SEED_CATEGORIAS in workflow_engine.py
SEED = [
    ("CAP", "Capilares"),
    ("SKC", "Skin Care / Dermocosméticos"),
    ("HGP", "Higiene Pessoal"),
    ("PFM", "Perfumaria"),
    ("MAQ", "Maquiagem"),
    ("COR", "Corporal / Spa"),
    ("INF", "Infantil"),
    ("MAS", "Masculino"),
    ("PRS", "Profissional / Salão"),
    ("BSP", "Body Splash"),
]

SYSTEM_USER = "system"
SEED_JUSTIFICATIVA = "Categoria padrão do sistema — migrada automaticamente (m002)"


async def run(db):
    print("=== m002: Seed categorias ===")

    # Find all tenants
    tenants = await db.tenants.distinct("id")
    if not tenants:
        # Fallback: find tenant_ids from users
        tenants = await db.users.distinct("tenant_id")
    print(f"  Tenants found: {len(tenants)}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    import uuid

    for tenant_id in tenants:
        inserted = 0
        skipped = 0
        for cat3, nome in SEED:
            existing = await db.categorias.find_one({"tenant_id": tenant_id, "cat3": cat3})
            if existing:
                skipped += 1
                continue
            doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "cat3": cat3,
                "nome": nome,
                "status": "ativa",
                "solicitado_por": SYSTEM_USER,
                "solicitado_por_id": SYSTEM_USER,
                "solicitado_em": now,
                "aprovado_por": SYSTEM_USER,
                "aprovado_por_id": SYSTEM_USER,
                "aprovado_em": now,
                "justificativa": SEED_JUSTIFICATIVA,
                "justificativa_aprovacao": SEED_JUSTIFICATIVA,
                "created_at": now,
                "updated_at": now,
            }
            await db.categorias.insert_one(doc)
            inserted += 1

        print(f"  Tenant {tenant_id}: inserted {inserted}, skipped {skipped}")

    # Ensure unique index exists (ignore if already created with different name)
    try:
        await db.categorias.create_index(
            [("tenant_id", 1), ("cat3", 1)], unique=True, name="tenant_cat3_unique"
        )
        print("  Index tenant_cat3 created")
    except Exception as e:
        print(f"  Index tenant_cat3 already exists ({e.__class__.__name__}) — skipping")
    print("=== m002 complete ===")


async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await run(db)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
