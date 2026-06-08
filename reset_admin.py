import asyncio, bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['kuryos_crm']
    new_pass = 'admin123'
    hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
    r = await db.users.update_one({'email': 'admin@kuryos.com'}, {'$set': {'password_hash': hashed}})
    print(f'Senha resetada: {r.modified_count} documento(s) atualizado(s)')

asyncio.run(main())
