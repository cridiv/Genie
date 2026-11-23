"""Pharmacy confirmed stock inventory service."""
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genie.db.models import PharmacyInventory


class PharmacyInventoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_stock_confirmed(self, pharmacy_id: UUID, product_id: UUID) -> bool:
        """Confirms stock if verified within the last 48 hours."""
        cutoff = datetime.utcnow() - timedelta(hours=48)
        stmt = select(PharmacyInventory).filter(
            PharmacyInventory.pharmacy_id == pharmacy_id,
            PharmacyInventory.product_id == product_id,
            PharmacyInventory.availability_status == "confirmed",
            PharmacyInventory.last_confirmed_at >= cutoff,
        )
        res = await self.db.execute(stmt)
        record = res.scalars().first()
        return record is not None
