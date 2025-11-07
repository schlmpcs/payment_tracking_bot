#!/usr/bin/env python3
"""
Test Koyeb PostgreSQL connection with different configurations
"""

import asyncio
import asyncpg
import ssl
import sys
from bot.config.settings import Settings

async def test_connection():
    """Test database connection with various SSL configurations"""
    
    settings = Settings()
    
    print(f"🔍 Testing connection to: {settings.db_host}")
    print(f"📊 Database: {settings.db_database}")
    print(f"👤 User: {settings.db_username.get_secret_value()}")
    print(f"🔌 Port: {settings.db_port or 5432}")
    print()
    
    # Test 1: SSL with no verification (Koyeb recommended)
    print("🧪 Test 1: SSL with no verification...")
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        conn = await asyncpg.connect(
            host=settings.db_host,
            port=settings.db_port or 5432,
            user=settings.db_username.get_secret_value(),
            password=settings.db_password.get_secret_value(),
            database=settings.db_database,
            ssl=ssl_context,
            command_timeout=30
        )
        
        # Test query
        result = await conn.fetchval("SELECT version()")
        print(f"✅ Connection successful!")
        print(f"📝 PostgreSQL version: {result}")
        
        # Test table creation
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_connection (
                id SERIAL PRIMARY KEY,
                test_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await conn.execute("""
            INSERT INTO test_connection (test_message) 
            VALUES ('Connection test successful!')
        """)
        
        count = await conn.fetchval("SELECT COUNT(*) FROM test_connection")
        print(f"📊 Test records in database: {count}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        print(f"🔍 Error type: {type(e).__name__}")
    
    # Test 2: SSL require mode
    print("\n🧪 Test 2: SSL require mode...")
    try:
        conn = await asyncpg.connect(
            host=settings.db_host,
            port=settings.db_port or 5432,
            user=settings.db_username.get_secret_value(),
            password=settings.db_password.get_secret_value(),
            database=settings.db_database,
            ssl='require',
            command_timeout=30
        )
        
        result = await conn.fetchval("SELECT 1")
        print(f"✅ Test 2 successful!")
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
    
    # Test 3: No SSL (should fail with Koyeb)
    print("\n🧪 Test 3: No SSL...")
    try:
        conn = await asyncpg.connect(
            host=settings.db_host,
            port=settings.db_port or 5432,
            user=settings.db_username.get_secret_value(),
            password=settings.db_password.get_secret_value(),
            database=settings.db_database,
            ssl=False,
            command_timeout=30
        )
        
        result = await conn.fetchval("SELECT 1")
        print(f"✅ Test 3 successful!")
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Test 3 failed (expected): {e}")
    
    print("\n❌ All connection tests failed!")
    return False

if __name__ == "__main__":
    print("🔬 Koyeb PostgreSQL Connection Test")
    print("=" * 50)
    
    try:
        success = asyncio.run(test_connection())
        if success:
            print("\n🎉 Database connection is working!")
            sys.exit(0)
        else:
            print("\n💥 Database connection failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)