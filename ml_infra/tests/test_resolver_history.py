"""Tests for Phase 7: Candidate product resolution and SCD Type 2 history traversal."""
from datetime import date, timedelta
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from genie.db.models import Base, Product, ProductVersion
from genie.storage.vector_store import InMemoryVectorStore
from genie.verification.resolver import ProductResolver
from genie.verification.signals.history_signal import HistorySignalEvaluator


@pytest.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def vector_store():
    return InMemoryVectorStore()


@pytest.mark.asyncio
async def test_resolve_priority_1_gtin(async_session: AsyncSession, vector_store: InMemoryVectorStore):
    product = Product(
        id=uuid.uuid4(),
        brand_name="Coartem 80/480",
        manufacturer="Novartis Pharma",
        primary_nafdac_number="04-1234",
        gtin_list=["06151234567891", "06159999999999"],
    )
    async_session.add(product)
    await async_session.flush()

    active_version = ProductVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_label="2025_Design_v2",
        valid_from=date(2025, 1, 1),
        status="active",
    )
    async_session.add(active_version)
    await async_session.commit()

    resolver = ProductResolver(async_session, vector_store)
    candidate = await resolver.resolve(gtin="06151234567891")

    assert candidate is not None
    assert candidate.product.brand_name == "Coartem 80/480"
    assert candidate.active_version.version_label == "2025_Design_v2"
    assert candidate.resolution_method == "gtin"
    assert candidate.is_legacy_version is False


@pytest.mark.asyncio
async def test_resolve_priority_2_nafdac(async_session: AsyncSession, vector_store: InMemoryVectorStore):
    product = Product(
        id=uuid.uuid4(),
        brand_name="Amartem Soft Gel",
        manufacturer="Geneith Pharmaceuticals",
        primary_nafdac_number="A4-8921",
        gtin_list=[],
    )
    async_session.add(product)
    await async_session.flush()

    active_version = ProductVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_label="2024_Blister_v1",
        valid_from=date(2024, 1, 1),
        status="active",
    )
    async_session.add(active_version)
    await async_session.commit()

    resolver = ProductResolver(async_session, vector_store)
    # Test case-insensitivity and whitespace stripping
    candidate = await resolver.resolve(nafdac_number=" a4-8921 ")

    assert candidate is not None
    assert candidate.product.brand_name == "Amartem Soft Gel"
    assert candidate.resolution_method == "nafdac"


@pytest.mark.asyncio
async def test_resolve_scd_type2_historical_version(async_session: AsyncSession, vector_store: InMemoryVectorStore):
    today = date(2026, 11, 24)
    product = Product(
        id=uuid.uuid4(),
        brand_name="Lonart Forte",
        manufacturer="Greenlife Pharmaceuticals",
        primary_nafdac_number="B4-5555",
        gtin_list=[],
    )
    async_session.add(product)
    await async_session.flush()

    # Current active version introduced 6 months ago
    active_version = ProductVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_label="2026_Modern_Pack",
        valid_from=date(2026, 5, 1),
        status="active",
    )
    # Superseded legacy version valid until 6 months ago (shelf life 24 months)
    legacy_version_recent = ProductVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_label="2022_Classic_Pack",
        valid_from=date(2022, 1, 1),
        valid_to=date(2026, 4, 30),
        status="superseded",
        shelf_life_months=24,
    )
    # Very old superseded version (valid_to 4 years ago, expired transition)
    legacy_version_expired = ProductVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_label="2018_Old_Pack",
        valid_from=date(2018, 1, 1),
        valid_to=date(2021, 12, 31),
        status="superseded",
        shelf_life_months=24,
    )
    async_session.add_all([active_version, legacy_version_recent, legacy_version_expired])
    await async_session.commit()

    # Register legacy embedding in vector store
    legacy_emb = [0.1] * 768
    await vector_store.upsert(
        id=f"pack_{legacy_version_recent.id}",
        vector=legacy_emb,
        metadata={
            "product_id": str(product.id),
            "product_version_id": str(legacy_version_recent.id),
        },
    )

    resolver = ProductResolver(async_session, vector_store)

    # 1. Traversal verification
    traversal = await resolver.traverse_historical_versions(product.id, current_date=today)
    assert len(traversal) == 2
    # First is recent legacy version (in window: ~7 months <= 24 months)
    assert traversal[0][0].id == legacy_version_recent.id
    assert traversal[0][1] is True
    # Second is expired legacy version (out of window: ~5 years > 24 months)
    assert traversal[1][0].id == legacy_version_expired.id
    assert traversal[1][1] is False

    # 2. Vector match to recent legacy version
    candidate = await resolver.resolve(embedding=legacy_emb, current_date=today)
    assert candidate is not None
    assert candidate.product.brand_name == "Lonart Forte"
    assert candidate.is_legacy_version is True
    assert candidate.in_transition_window is True
    assert candidate.matched_version.version_label == "2022_Classic_Pack"


def test_history_signal_evaluator():
    evaluator = HistorySignalEvaluator()

    # Active match
    active_sig = evaluator.evaluate(is_legacy_match=False)
    assert active_sig.score == 1.0
    assert "active packaging" in active_sig.reasons[0]

    # Valid legacy match within transition window
    legacy_valid = evaluator.evaluate(is_legacy_match=True, version_label="2022_Classic", transition_active=True)
    assert legacy_valid.score >= 0.90
    assert "transition window" in legacy_valid.reasons[0]

    # Legacy match beyond transition window
    legacy_expired = evaluator.evaluate(is_legacy_match=True, version_label="2018_Old", transition_active=False)
    assert legacy_expired.score <= 0.40
    assert "exceeded its permitted" in legacy_expired.reasons[0]
