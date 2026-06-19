"""
Migration m003 — Add cli4 and cli4_congelado fields to existing clients (R23)

- For clients that already have cli3: derive cli4 by extending (cli3 + first letter
  of remaining name, or pad with 'X').
- For clients that already have SKUs: set cli4_congelado=True.
- For clients without cli3: suggest from nome_empresa, pick the first available code.

Idempotent: clients that already have cli4 are skipped.
Run:
    cd backend && python -m migrations.m003_client_cli4
"""

import asyncio
import motor.motor_asyncio

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "kuryos"


def normalise_cli4(raw: str) -> str:
    letters = "".join(c for c in (raw or "").upper() if c.isalpha())[:4]
    return letters.ljust(4, "X") if letters else "GENX"


def suggest_cli4_from_name(nome: str) -> list:
    nome_up = (nome or "").upper()
    words = nome_up.split()
    word_letters = ["".join(c for c in w if c.isalpha()) for w in words if any(c.isalpha() for c in w)]
    all_letters = "".join(word_letters)

    candidates = []
    if all_letters:
        candidates.append(all_letters[:4].ljust(4, "X"))
    if len(word_letters) >= 2 and len(word_letters[0]) >= 3:
        candidates.append((word_letters[0][:3] + word_letters[1][0]).ljust(4, "X"))
    if len(word_letters) >= 2:
        candidates.append((word_letters[0][:2] + word_letters[1][:2]).ljust(4, "X"))
    initials = "".join(w[0] for w in word_letters if w)
    if len(initials) >= 2:
        candidates.append(initials[:4].ljust(4, "X"))
    for start in range(1, max(0, len(all_letters) - 3)):
        candidates.append(all_letters[start:start + 4].ljust(4, "X"))

    seen, result = set(), []
    for c in candidates:
        if c not in seen and len(c) == 4 and c.isalpha():
            seen.add(c)
            result.append(c)
    return result


async def run(db):
    print("=== m003: Add cli4 to clients ===")

    all_clients = await db.crm_clients.find(
        {}, {"_id": 0, "id": 1, "tenant_id": 1, "nome_empresa": 1, "cli3": 1, "cli4": 1}
    ).to_list(None)

    to_migrate = [c for c in all_clients if not c.get("cli4")]
    print(f"  Total clients: {len(all_clients)} | To migrate: {len(to_migrate)}")

    # Build a per-tenant set of existing cli4 codes to detect conflicts
    from collections import defaultdict
    used: dict = defaultdict(set)
    for c in all_clients:
        if c.get("cli4"):
            used[c["tenant_id"]].add(c["cli4"])

    updated = 0
    for client in to_migrate:
        tenant_id = client["tenant_id"]
        nome = client.get("nome_empresa", "")
        cli3 = client.get("cli3", "")

        # Build candidates: prioritize extending cli3 if available
        if cli3 and len(cli3) == 3:
            name_letters = "".join(c for c in nome.upper() if c.isalpha())
            ext = name_letters[3:4] if len(name_letters) >= 4 else "X"
            priority = [cli3 + ext] + suggest_cli4_from_name(nome)
        else:
            priority = suggest_cli4_from_name(nome)
            if not priority:
                priority = [normalise_cli4(nome)]

        chosen = None
        for code in priority:
            if code not in used[tenant_id]:
                chosen = code
                used[tenant_id].add(code)
                break
        if not chosen:
            chosen = priority[0] if priority else normalise_cli4(nome)
            # Even if conflicted, assign — operator can fix manually
            used[tenant_id].add(chosen)

        # Check if this client has any SKUs → freeze cli4
        has_skus = await db.skus.count_documents({"cliente_id": client["id"], "tenant_id": tenant_id})
        congelado = has_skus > 0

        await db.crm_clients.update_one(
            {"id": client["id"]},
            {"$set": {"cli4": chosen, "cli4_congelado": congelado}},
        )
        updated += 1

    print(f"  Updated: {updated} clients")

    # Ensure unique index (sparse allows multiple nulls — but we shouldn't have nulls now)
    await db.crm_clients.create_index(
        [("tenant_id", 1), ("cli4", 1)],
        unique=True,
        sparse=True,
        name="tenant_cli4_unique",
    )
    print("  Index tenant_cli4 ensured")
    print("=== m003 complete ===")


async def main():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await run(db)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
