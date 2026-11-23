"""Nearby verified pharmacies API router."""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from genie.api.deps import get_db
from genie.pharmacy.discovery import PharmacyDiscoveryService
from genie.schemas.verdict import SaferAlternative

router = APIRouter(tags=["Pharmacies"])


@router.get("/pharmacies/nearby", response_model=List[SaferAlternative])
async def get_nearby_pharmacies(
    lat: float = Query(..., example=6.5244),
    lng: float = Query(..., example=3.3792),
    radius_km: float = Query(10.0, ge=1.0, le=50.0),
    product_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = PharmacyDiscoveryService(db)
    return await service.find_nearby(lat=lat, lon=lng, radius_km=radius_km, product_id=product_id)
