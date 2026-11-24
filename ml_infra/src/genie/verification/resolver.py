"""Candidate product resolution via hierarchical voting between GTIN, NAFDAC, and visual vectors, with SCD Type 2 history traversal."""
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genie.db.models import Product, ProductVersion
from genie.storage.vector_store import VectorStore


@dataclass
class ResolvedCandidate:
    product: Product
    active_version: ProductVersion
    matched_version: ProductVersion
    is_legacy_version: bool = False
    in_transition_window: bool = True
    confidence: float = 0.0
    resolution_method: str = "unknown"  # gtin | nafdac | vector


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
        current_date: Optional[date] = None,
    ) -> Optional[ResolvedCandidate]:
        """Executes hierarchical voting to identify the product entity and active/historical version."""
        curr_d = current_date or date.today()

        # Priority 1: Resolve by GTIN
        if gtin:
            clean_gtin = gtin.strip()
            stmt = select(Product)
            res = await self.db.execute(stmt)
            products = res.scalars().all()
            for p in products:
                if p.gtin_list and clean_gtin in [str(g).strip() for g in p.gtin_list]:
                    active_v = await self._get_active_version(p.id)
                    if active_v:
                        return ResolvedCandidate(
                            product=p,
                            active_version=active_v,
                            matched_version=active_v,
                            is_legacy_version=False,
                            in_transition_window=True,
                            confidence=0.98,
                            resolution_method="gtin",
                        )

        # Priority 2: Resolve by NAFDAC Number
        if nafdac_number:
            clean_nafdac = nafdac_number.strip().upper()
            stmt = select(Product).filter(Product.primary_nafdac_number == clean_nafdac)
            res = await self.db.execute(stmt)
            product = res.scalars().first()
            if product:
                active_v = await self._get_active_version(product.id)
                if active_v:
                    return ResolvedCandidate(
                        product=product,
                        active_version=active_v,
                        matched_version=active_v,
                        is_legacy_version=False,
                        in_transition_window=True,
                        confidence=0.92,
                        resolution_method="nafdac",
                    )

        # Priority 3: Resolve by Visual Vector Search
        if embedding:
            matches = await self.vector_store.search(embedding, top_k=1)
            if matches and matches[0].score >= 0.75:
                v_id_str = matches[0].metadata.get("product_version_id")
                if v_id_str:
                    v_uuid = UUID(v_id_str)
                    stmt = select(ProductVersion).filter(ProductVersion.id == v_uuid)
                    res = await self.db.execute(stmt)
                    version = res.scalars().first()
                    if version:
                        p_stmt = select(Product).filter(Product.id == version.product_id)
                        p_res = await self.db.execute(p_stmt)
                        product = p_res.scalars().first()
                        if product:
                            active_v = await self._get_active_version(product.id) or version
                            is_legacy = version.status == "superseded"
                            in_window = True

                            if is_legacy and version.valid_to:
                                shelf_days = getattr(version, "shelf_life_months", 24) * 30
                                days_since_expiry = (curr_d - version.valid_to).days
                                in_window = days_since_expiry <= shelf_days

                            return ResolvedCandidate(
                                product=product,
                                active_version=active_v,
                                matched_version=version,
                                is_legacy_version=is_legacy,
                                in_transition_window=in_window,
                                confidence=matches[0].score,
                                resolution_method="vector",
                            )

        return None

    async def traverse_historical_versions(
        self,
        product_id: UUID,
        current_date: Optional[date] = None,
    ) -> List[Tuple[ProductVersion, bool]]:
        """Traverses historical (superseded) versions and calculates transition window validity.

        Returns list of (ProductVersion, is_within_transition_window).
        """
        curr_d = current_date or date.today()
        stmt = (
            select(ProductVersion)
            .filter(ProductVersion.product_id == product_id, ProductVersion.status == "superseded")
            .order_by(ProductVersion.valid_to.desc())
        )
        res = await self.db.execute(stmt)
        superseded_versions = res.scalars().all()

        results = []
        for v in superseded_versions:
            if v.valid_to:
                shelf_days = getattr(v, "shelf_life_months", 24) * 30
                days_since_transition = (curr_d - v.valid_to).days
                in_window = days_since_transition <= shelf_days
            else:
                in_window = True
            results.append((v, in_window))

        return results

    async def _get_active_version(self, product_id: UUID) -> Optional[ProductVersion]:
        stmt = (
            select(ProductVersion)
            .filter(ProductVersion.product_id == product_id, ProductVersion.status == "active")
            .order_by(ProductVersion.created_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()
