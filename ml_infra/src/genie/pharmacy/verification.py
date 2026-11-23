"""Pharmacy license verification service."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genie.db.models import Pharmacy


class PharmacyVerificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify_license(self, license_id: str) -> bool:
        stmt = select(Pharmacy).filter(Pharmacy.license_id == license_id)
        res = await self.db.execute(stmt)
        pharmacy = res.scalars().first()
        return bool(pharmacy and pharmacy.is_verified)
