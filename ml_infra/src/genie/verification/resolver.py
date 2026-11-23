"""Candidate product resolution via voting between GTIN, NAFDAC, and visual vectors."""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genie.db.models import Product, ProductVersion
from genie.storage.vector_store import VectorStore


@dataclass
class ResolvedCandidate:
    product: Product
    active_version: ProductVersion
    is_legacy_version: bool = False
    confidence: float = 0.0


class ProductResolver:
    """Resolves scan signals to candidate product versions in the intelligence database."""

    def __init__(self, db_session: AsyncSession, vector_store: VectorStore):
        self.db = db_session
        self.vector_store = vector_store

    async def resolve(
        self,
        gtin: Optional[str] = None,
        nafdac_number: Optional[str] = None,
        embedding: Optional[List[float]] = None,
    ) -> Optional[ResolvedCandidate]:
        # 1. Resolve by GTIN
        if gtin:
            stmt = select(Product).filter(Product.gtin_list.contains([gtin]))
            res = await self.db.execute(stmt)
            product = res.scalars().first()
            if product:
                version = await self._get_active_version(product.id)
                if version:
                    return ResolvedCandidate(product=product, active_version=version, confidence=0.9)

        # 2. Resolve by NAFDAC Number
        if nafdac_number:
            stmt = select(Product).filter(Product.primary_nafdac_number == nafdac_number)
            res = await self.db.execute(stmt)
            product = res.scalars().first()
            if product:
                version = await self._get_active_version(product.id)
                if version:
                    return ResolvedCandidate(product=product, active_version=version, confidence=0.85)

        # 3. Resolve by Visual Vector Search
        if embedding:
            matches = await self.vector_store.search(embedding, top_k=1)
            if matches and matches[0].score > 0.75:
                v_id = matches[0].metadata.get("product_version_id")
                if v_id:
                    stmt = select(ProductVersion).filter(ProductVersion.id == UUID(v_id))
                    res = await self.db.execute(stmt)
                    version = res.scalars().first()
                    if version:
                        p_stmt = select(Product).filter(Product.id == version.product_id)
                        p_res = await self.db.execute(p_stmt)
                        product = p_res.scalars().first()
                        if product:
                            is_legacy = version.status == "superseded"
                            return ResolvedCandidate(
                                product=product,
                                active_version=version,
                                is_legacy_version=is_legacy,
                                confidence=matches[0].score,
                            )

        return None

    async def _get_active_version(self, product_id: UUID) -> Optional[ProductVersion]:
        stmt = (
            select(ProductVersion)
            .filter(ProductVersion.product_id == product_id, ProductVersion.status == "active")
            .order_by(ProductVersion.created_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()
