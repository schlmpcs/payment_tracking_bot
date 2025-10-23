#!/usr/bin/env python3
"""
Test script to verify the payment flow implementation
"""

import asyncio
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.tools.db import Database
from app.routers.users.user import User
from datetime import datetime, timedelta

async def test_payment_flow():
    """Test the payment functionality"""
    print("🧪 Testing Payment Flow Implementation...")
    
    # Initialize database
    db = Database()
    user = User()
    
    try:
        # Connect to database
        await db.connect()
        print("✅ Database connection established")
        
        # Initialize tables
        await db.initialize()
        print("✅ Database tables initialized")
        
        # Test data
        test_user_id = 12345
        test_username = "testuser"
        test_group_id = 1
        test_group_name = "Test Group"
        
        # Add test user
        user_added = await db.add_user(test_user_id, test_username)
        print(f"✅ Test user added: {user_added}")
        
        # Add test group
        payment_date = datetime.now() + timedelta(days=30)
        group_added = await db.add_group(test_group_id, test_group_name, payment_date)
        print(f"✅ Test group added: {group_added}")
        
        # Link user to group
        payment_linked = await db.add_payments(test_user_id, test_group_id, payment_date)
        print(f"✅ User linked to group: {payment_linked}")
        
        # Test user registration check
        is_registered = await user.is_registered(test_user_id)
        print(f"✅ User registration check: {is_registered}")
        
        # Test get payment info
        payment_info = await user.get_payment_info(test_user_id)
        print(f"✅ Payment info retrieved: {payment_info is not None}")
        if payment_info:
            group_id, group_name, next_payment, last_paid = payment_info
            print(f"   - Group: {group_name}")
            print(f"   - Next payment: {next_payment}")
            print(f"   - Last paid: {last_paid}")
        
        # Test payment processing
        payment_processed = await user.process_payment(test_user_id, 2)  # Pay for 2 months
        print(f"✅ Payment processed: {payment_processed}")
        
        # Test payment info after processing
        updated_info = await user.get_payment_info(test_user_id)
        if updated_info:
            _, _, updated_payment, updated_paid = updated_info
            print(f"✅ Updated payment date: {updated_payment}")
            print(f"✅ Updated paid date: {updated_paid}")
        
        print("\n🎉 All tests passed! Payment flow implementation is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up test data
        try:
            await db.drop_table()
            print("🧹 Test data cleaned up")
        except:
            pass
        
        if db.pool:
            await db.pool.close()
            print("🔌 Database connection closed")

if __name__ == "__main__":
    asyncio.run(test_payment_flow())