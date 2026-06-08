import asyncio, bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['kuryos_crm']
    u = await db.users.find_one({'email': 'admin@kuryos.com'})
    if not u:
        print("User not found")
        return
    print(f"id={u.get('id')} email={u.get('email')} role={u.get('role')}")
    stored = u.get('password_hash', '')
    print(f"hash={stored[:30]}...")
    # Test password
    test = bcrypt.checkpw(b'admin123', stored.encode())
    print(f"admin123 matches: {test}")

asyncio.run(main())
