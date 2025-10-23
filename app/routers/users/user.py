from .admin import db

class User:
    async def get_payment_info(self, user_id: int):
        """Get user's payment information"""
        if not db.pool:
            return None
        return await db.get_user_payment_info(user_id)
    
    async def is_registered(self, user_id: int):
        """Check if user is registered in the system"""
        if not db.pool:
            return False
        return await db.is_user_registered(user_id)
    
    async def process_payment(self, user_id: int, months: int):
        """Process payment for user"""
        if not db.pool:
            return False
        return await db.mark_payment(user_id, months)