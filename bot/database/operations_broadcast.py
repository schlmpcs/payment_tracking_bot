
    async def get_users_by_region(self, region: str) -> List[int]:
        """Get all user IDs by region ('ru', 'kz', or 'all')"""
        if not self.pool:
            return []

        try:
            async with self.pool.acquire() as conn:
                if region == 'all':
                    # Get all users who are in any group
                    query = """
                        SELECT DISTINCT u.user_id 
                        FROM users u
                        JOIN user_groups ug ON u.user_id = ug.user_id
                        JOIN groups g ON ug.group_id = g.group_id
                    """
                    rows = await conn.fetch(query)
                else:
                    # Filter by display_id pattern
                    # 100+ = RU, 000-099 = KZ
                    pattern = '1%' if region == 'ru' else '0%'
                    
                    # Use parameterized query for safety
                    query = """
                        SELECT DISTINCT u.user_id 
                        FROM users u
                        JOIN user_groups ug ON u.user_id = ug.user_id
                        JOIN groups g ON ug.group_id = g.group_id
                        WHERE g.display_id LIKE $1
                    """
                    rows = await conn.fetch(query, pattern)
                
                return [row['user_id'] for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get users for region {region}: {e}")
            return []
