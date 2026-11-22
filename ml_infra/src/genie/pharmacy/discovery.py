"""Geospatial radius lookup for licensed pharmacies using Haversine formula."""
import math
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genie.db.models import Pharmacy
from genie.schemas.verdict import SaferAlternative


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class PharmacyDiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_nearby(
        self,
        lat: float,
        lon: float,
        radius_km: float = 10.0,
        product_id: UUID | None = None,
    ) -> List[SaferAlternative]:
        stmt = select(Pharmacy).filter(Pharmacy.is_verified == True)
        res = await self.db.execute(stmt)
        pharmacies = res.scalars().all()

        results: List[SaferAlternative] = []
        for p in pharmacies:
            dist = haversine_distance_km(lat, lon, p.latitude, p.longitude)
            if dist <= radius_km:
                results.append(
                    SaferAlternative(
                        pharmacy_id=p.id,
                        pharmacy_name=p.name,
                        address=p.address,
                        distance_km=round(dist, 2),
                        pharmacy_verified=p.is_verified,
                        stock_confirmed=False,  # Enforces confirmation separation
                    )
                )

        results.sort(key=lambda x: x.distance_km)
        return results
