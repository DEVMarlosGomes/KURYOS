"""
Migração de usuários MongoDB → Supabase Auth + PostgreSQL users table.

Uso:
    cd backend
    python ../migrations/migrate_users_to_supabase.py

O script:
  1. Lê todos os usuários do MongoDB
  2. Cria cada um no Supabase Auth (com app_metadata: tenant_id, user_role, name, kuryos_id)
  3. Insere na tabela PostgreSQL users (ON CONFLICT DO NOTHING — idempotente)
  4. Grava um relatório em migrations/migration_report.json

Importante:
  - Usuários com "supabase_id" já preenchido no MongoDB são ignorados (já migrados)
  - A senha no Supabase é setada como temporária; o usuário receberá email de redefinição
  - Execute apenas UMA vez por ambiente
"""
import asyncio
import os
import json
import secrets
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Adiciona o diretório backend ao path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env", override=False)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

import auth_supabase as supa_auth
import database as pg_db
from motor.motor_asyncio import AsyncIOMotorClient


async def migrate():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
    db_name = os.environ.get("DB_NAME", "kuryos_crm")

    # Inicializa MongoDB
    mongo_client = AsyncIOMotorClient(mongo_url)
    mongo_db = mongo_client[db_name]

    # Inicializa PostgreSQL (opcional — migração continua sem ele)
    pg_available = False
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            await pg_db.init_db()
            pg_available = True
            logger.info("PostgreSQL pool inicializado")
        except Exception as e:
            logger.warning(f"PostgreSQL indisponível — usuários serão migrados só para Supabase Auth: {e}")

    # Inicializa Supabase Auth
    ok = supa_auth.init_supabase_auth()
    if not ok:
        logger.error("Supabase Auth não disponível. Verifique SUPABASE_URL e SUPABASE_SERVICE_KEY.")
        return

    # Sincroniza tenants no PostgreSQL antes dos usuários (FK dependency)
    if pg_available and pg_db._pool:
        from datetime import datetime, timezone as tz
        tenants = await mongo_db.tenants.find({}, {"_id": 0}).to_list(1000)
        logger.info(f"Sincronizando {len(tenants)} tenant(s) no PostgreSQL")
        for t in tenants:
            try:
                raw_ts = t.get("created_at")
                if isinstance(raw_ts, str):
                    created_dt = datetime.fromisoformat(raw_ts)
                elif isinstance(raw_ts, datetime):
                    created_dt = raw_ts
                else:
                    created_dt = datetime.now(tz.utc)
                await pg_db.execute(
                    """
                    INSERT INTO tenants(id, name, created_at, updated_at)
                    VALUES($1, $2, $3, NOW())
                    ON CONFLICT(id) DO UPDATE SET name = EXCLUDED.name
                    """,
                    t["id"], t.get("name", ""), created_dt,
                )
                logger.info(f"  Tenant OK: {t.get('name')} ({t['id']})")
            except Exception as e:
                logger.warning(f"  Tenant SKIP {t['id']}: {e}")

    # Busca todos os usuários MongoDB
    users = await mongo_db.users.find({}, {"_id": 0}).to_list(10000)
    logger.info(f"Encontrados {len(users)} usuários no MongoDB")

    report = {
        "executado_em": datetime.now(timezone.utc).isoformat(),
        "total": len(users),
        "migrados": [],
        "ja_migrados": [],
        "erros": [],
    }

    for user in users:
        email = user.get("email", "")
        kuryos_id = user.get("id", "")
        tenant_id = user.get("tenant_id", "")
        role = user.get("role", "vendedor")
        name = user.get("name", email)

        # Já migrado para Supabase Auth — apenas garante o insert no PostgreSQL
        if user.get("supabase_id"):
            report["ja_migrados"].append({"email": email, "id": kuryos_id})
            logger.info(f"  SKIP Supabase {email} (já migrado) — sync PG...")
            if pg_available and pg_db._pool:
                try:
                    await pg_db.execute(
                        """
                        INSERT INTO users(id, tenant_id, email, name, role, created_at, updated_at)
                        VALUES($1, $2, $3, $4, $5, NOW(), NOW())
                        ON CONFLICT(id) DO UPDATE SET
                            tenant_id = EXCLUDED.tenant_id,
                            role = EXCLUDED.role,
                            name = EXCLUDED.name
                        """,
                        kuryos_id, tenant_id, email, name, role
                    )
                    logger.info(f"    PG OK {email}")
                except Exception as e:
                    logger.warning(f"    PG SKIP {email}: {e}")
            continue

        # Cria no Supabase Auth com senha temporária
        temp_password = secrets.token_urlsafe(12)
        supa_user = supa_auth.create_supabase_user(
            email=email,
            password=temp_password,
            tenant_id=tenant_id,
            role=role,
            name=name,
            kuryos_id=kuryos_id,
        )

        if not supa_user:
            report["erros"].append({"email": email, "motivo": "falha ao criar no Supabase"})
            logger.warning(f"  ERRO {email}")
            continue

        supabase_id = supa_user.get("id", "")

        # Atualiza MongoDB com supabase_id
        await mongo_db.users.update_one(
            {"id": kuryos_id},
            {"$set": {"supabase_id": supabase_id}}
        )

        # Insere na tabela PostgreSQL
        if pg_available and pg_db._pool:
            try:
                await pg_db.execute(
                    """
                    INSERT INTO users(id, tenant_id, email, name, role, created_at, updated_at)
                    VALUES($1, $2, $3, $4, $5, NOW(), NOW())
                    ON CONFLICT(id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        role = EXCLUDED.role,
                        name = EXCLUDED.name
                    """,
                    kuryos_id, tenant_id, email, name, role
                )
            except Exception as e:
                logger.warning(f"  PG INSERT falhou para {email}: {e}")

        report["migrados"].append({
            "email": email,
            "kuryos_id": kuryos_id,
            "supabase_id": supabase_id,
        })
        logger.info(f"  OK {email} → {supabase_id}")

    # Grava relatório
    report_path = REPO_ROOT / "migrations" / "migration_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        f"\nRelatório: {report_path}\n"
        f"  Migrados:    {len(report['migrados'])}\n"
        f"  Já migrados: {len(report['ja_migrados'])}\n"
        f"  Erros:       {len(report['erros'])}"
    )

    if pg_available:
        await pg_db.close_db()
    mongo_client.close()


if __name__ == "__main__":
    asyncio.run(migrate())
