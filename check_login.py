import asyncio, bcrypt, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from motor.motor_asyncio import AsyncIOMotorClient

# Check BOTH databases to see which one the server might be using
async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')

    dbs = await client.list_database_names()
    print("Databases:", dbs)

    for dbname in ['kuryos_crm', 'kuryos_dev', 'kuryos', 'kuryos_demo', 'test']:
        if dbname in dbs:
            db = client[dbname]
            users = await db.users.find({'email': 'admin@kuryos.com'}, {'email':1,'role':1,'password_hash':1}).to_list(5)
            for u in users:
                h = u.get('password_hash','')
                match = bcrypt.checkpw(b'admin123', h.encode()) if h else False
                print(f"DB={dbname} email={u['email']} hash_ok={match} hash_prefix={h[:20]}")

asyncio.run(main())
