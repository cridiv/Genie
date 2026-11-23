"""Product Intelligence API router."""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genie.api.deps import get_db
from genie.db.models import Product, ProductVersion
from genie.schemas.product import ProductRead
from genie.schemas.version import ProductVersionRead

router = APIRouter(tags=["Products"])


@router.get("/products", response_model=List[ProductRead])
async def list_products(db: AsyncSession = Depends(get_db)):
    stmt = select(Product).limit(50)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/products/{product_id}/versions", response_model=List[ProductVersionRead])
async def get_product_versions(product_id: UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(ProductVersion).filter(ProductVersion.product_id == product_id)
    res = await db.execute(stmt)
    versions = res.scalars().all()
    if not versions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product versions not found")
    return versions
