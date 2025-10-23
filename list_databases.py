#!/usr/bin/env python3
"""
Test database connection and list available databases
"""
import asyncio
import aiopg

async def test_connection():
    """Test database connection and list databases"""
    
    # Connection without specifying database
    dsn = "user=koyeb-adm password=npg_pKe72xVLrJZq host=ep-frosty-smoke-a2qpit14.eu-central-1.pg.koyeb.app"
    
    try:
        print("🔄 Attempting to connect to PostgreSQL server...")
        pool = await aiopg.create_pool(dsn)
        
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                print("✅ Connected successfully!")
                
                # List databases
                print("📋 Available databases:")
                await cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
                databases = await cursor.fetchall()
                
                for db in databases:
                    print(f"  - {db[0]}")
                    
        pool.close()
        await pool.wait_closed()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())