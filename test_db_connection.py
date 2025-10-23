#!/usr/bin/env python3
"""
Test database connection with Koyeb configuration
"""
import asyncio
from app.tools.db import Database

async def test_connection():
    """Test database connection"""
    try:
        db = Database()
        print(f"DSN (without sensitive data): dbname=spotify-payments user=koyeb-adm host={db.dsn.split('host=')[1].split()[0]}")
        print(f"Full DSN structure: {' '.join([part for part in db.dsn.split() if not part.startswith('password=')])}")
        
        print("🔄 Attempting to connect to database...")
        result = await db.connect()
        
        if not result:
            print("📋 Check the error log for details...")
        
        if result:
            print("✅ Database connection successful!")
            
            # Test table initialization
            print("🔄 Testing table initialization...")
            init_result = await db.initialize()
            
            if init_result:
                print("✅ Database tables initialized successfully!")
            else:
                print("❌ Failed to initialize tables")
                
        else:
            print("❌ Database connection failed")
            
        if db.pool:
            await db.close()
        return result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())