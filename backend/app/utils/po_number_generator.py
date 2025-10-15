"""
Enhanced PO Number Generation with Uniqueness
"""
import asyncio
import uuid
from typing import Dict, Any, List
from datetime import date, datetime
import logging
from app.database.connection import db

logger = logging.getLogger(__name__)

class PONumberGenerator:
    def __init__(self):
        self.po_counter_cache = {}  # Cache for daily counters
        
    async def generate_unique_po_number(
        self, 
        user_id: int, 
        project_id: str, 
        order_date: str, 
        vendor_id: str
    ) -> str:
        """Generate unique PO number with format: PO-YYYYMMDD-VID-XXX"""
        
        try:

            # Convert standardized string to date object for database operations
            order_date_obj = datetime.strptime(order_date, '%Y-%m-%d').date()

            # Format: PO-YYYYMMDD-VENDOR-SEQUENCE
            date_str = order_date.replace('-', '')
            vendor_short = vendor_id[:]  # First 4 chars of vendor ID
            
            # Get next sequence number for this date
            sequence = await self._get_next_sequence_number(user_id, project_id, order_date_obj)
            
            # Generate PO number: PO-20250915-V001-001
            po_number = f"PO-{date_str}-{vendor_short}-{sequence:03d}"
            
            # Ensure uniqueness by checking database
            po_number = await self._ensure_unique_po_number(po_number, user_id, project_id)
            
            return po_number

        except Exception as e:
            logger.error(f"Error generating PO number: {e}")
            # Fallback to UUID-based number
            return f"PO-{date_str}-{uuid.uuid4().hex[:8].upper()}"

    async def _get_next_sequence_number(self, user_id: int, project_id: str, order_date: date) -> int:
        """Get next sequence number for the date"""
        
        try:
            cache_key = f"{user_id}_{project_id}_{order_date}"
            
            # Check cache first
            if cache_key in self.po_counter_cache:
                self.po_counter_cache[cache_key] += 1
                return self.po_counter_cache[cache_key]
            
            # Get count from database
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                count = await connection.fetchval("""
                    SELECT COUNT(*) FROM purchase_orders 
                    WHERE user_id = $1 AND project_id = $2 AND order_date = $3
                """,user_id, project_id, order_date)
                
                next_sequence = (count or 0) + 1
                self.po_counter_cache[cache_key] = next_sequence
                
                return next_sequence
                
        except Exception as e:
            logger.error(f"Error getting sequence number: {e}")
            return 1

    async def _ensure_unique_po_number(self, po_number: str, user_id: int, project_id: str) -> str:
        """Ensure PO number is unique, append suffix if needed"""
        
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                # Check if PO number exists
                exists = await connection.fetchval("""
                    SELECT EXISTS(
                        SELECT 1 FROM purchase_orders 
                        WHERE po_number = $1 AND user_id = $2 AND project_id = $3
                    )
                """, po_number, user_id, project_id)
                
                if not exists:
                    return po_number
                
                # If exists, append suffix
                suffix = 1
                while True:
                    new_po_number = f"{po_number}-{suffix:02d}"
                    
                    exists = await connection.fetchval("""
                        SELECT EXISTS(
                            SELECT 1 FROM purchase_orders 
                            WHERE po_number = $1 AND user_id = $2 AND project_id = $3
                        )
                    """, new_po_number, user_id, project_id)
                    
                    if not exists:
                        return new_po_number
                    
                    suffix += 1
                    
                    # Safety check to avoid infinite loop
                    if suffix > 99:
                        return f"{po_number}-{uuid.uuid4().hex[:4].upper()}"
                        
        except Exception as e:
            logger.error(f"Error ensuring unique PO number: {e}")
            return f"{po_number}-{uuid.uuid4().hex[:4].upper()}"

# Global instance
po_number_generator = PONumberGenerator()
