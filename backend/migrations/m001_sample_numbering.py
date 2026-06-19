"""
Migration m001 — Sample numbering: {YEAR}-{NNNN} + lowercase letter suffix

Converts existing samples from the legacy format (numero_amostra=int, codigo="101/A")
to the new format (numero_amostra="2026-1001", codigo="2026-1001-a").

Idempotent: samples already in YYYY-NNNN format are skipped.
Run:
    cd backend && python -m migrations.m001_sample_numbering
"""

import asyncio
import re
from datetime import timezone, datetime

import motor.motor_asyncio

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "kuryos"


def int_to_letters(n: int) -> str:
    result = ""
    while n >= 0:
        result = chr(ord("a") + (n % 26)) + result
        n = n // 26 - 1
    return result


def _is_new_format(numero: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{4}$", str(numero)))


async def run(db):
    print("=== m001: Sample numbering migration ===")

    # --- Collect samples that need migration ---
    all_samples = await db.crm_samples.find(
        {}, {"_id": 0, "id": 1, "tenant_id": 1, "numero_amostra": 1, "variacoes": 1, "created_at": 1}
    ).to_list(None)

    to_migrate = [s for s in all_samples if not _is_new_format(s.get("numero_amostra", ""))]
    already_done = len(all_samples) - len(to_migrate)
    print(f"  Total samples: {len(all_samples)}  |  Already migrated: {already_done}  |  To migrate: {len(to_migrate)}")

    if not to_migrate:
        print("  Nothing to do.")
        return

    # --- Group by tenant + year, sorted by created_at to preserve order ---
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for s in to_migrate:
        year = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00")).year
        groups[(s["tenant_id"], year)].append(s)

    for (tenant_id, year), samples in groups.items():
        samples.sort(key=lambda x: x.get("created_at", ""))

        # Start counter after any already-migrated samples in the same year
        existing_new = [
            s for s in all_samples
            if s["tenant_id"] == tenant_id
            and _is_new_format(s.get("numero_amostra", ""))
            and str(s["numero_amostra"]).startswith(str(year))
        ]
        # Find max seq already used
        max_seq = 0
        for s in existing_new:
            try:
                seq = int(str(s["numero_amostra"]).split("-")[1])
                max_seq = max(max_seq, seq)
            except (IndexError, ValueError):
                pass
        next_seq = max(max_seq, 1000) + 1  # start at 1001 if no prior

        print(f"  Tenant {tenant_id} / {year}: {len(samples)} samples, starting seq at {next_seq}")

        for sample in samples:
            new_numero = f"{year}-{str(next_seq).zfill(4)}"
            next_seq += 1

            # Update variação codes: "101/A" → "2026-1001-a"
            variacoes = sample.get("variacoes") or []
            new_variacoes = []
            for idx, v in enumerate(variacoes):
                letra = int_to_letters(idx)
                new_codigo = f"{new_numero}-{letra}"
                new_v = dict(v)
                new_v["codigo"] = new_codigo
                new_v["letra"] = letra
                new_variacoes.append(new_v)

            await db.crm_samples.update_one(
                {"id": sample["id"]},
                {"$set": {
                    "numero_amostra": new_numero,
                    "variacoes": new_variacoes,
                }},
            )

            # Update pd_cards that reference these variacoes
            for old_v, new_v in zip(variacoes, new_variacoes):
                old_codigo = old_v.get("codigo", "")
                new_codigo = new_v["codigo"]
                if old_codigo and old_codigo != new_codigo:
                    await db.pd_cards.update_many(
                        {"amostra_variacao_id": old_v["id"]},
                        {"$set": {
                            "numero_completo": new_codigo,
                            "amostra_numero": new_numero,
                        }},
                    )

            # Sync the counter so the live system won't issue a duplicate
            counter_key = f"sample_seq:{year}:{tenant_id}"
            seq_value = next_seq - 1001  # value stored = seq - start(1000)
            await db.counters.update_one(
                {"_id": counter_key},
                {"$max": {"seq": seq_value}},
                upsert=True,
            )

        print(f"    Done: last assigned was {year}-{str(next_seq - 1).zfill(4)}")

    print("=== m001 complete ===")


async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await run(db)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
