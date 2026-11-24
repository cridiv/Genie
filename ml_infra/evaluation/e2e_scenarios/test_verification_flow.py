"""End-to-End integration test scenarios verifying the full scan verification pipeline."""
import base64
from datetime import date
import uuid
import cv2
import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from genie.db.models import Base, Product, ProductVersion
from genie.schemas.scan import ScanImage, ScanRequest
from genie.schemas.verdict import VerdictState
from genie.storage.vector_store import InMemoryVectorStore
from genie.verification.pipeline import VerificationPipeline


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


def _generate_synthetic_pack_b64(
    text="COARTEM 80/480",
    nafdac="04-1234",
    batch="B1001",
    expiry="12/2027",
) -> str:
    """Creates a synthetic clear packaging image and returns base64 JPEG bytes."""
    img = np.full((512, 512, 3), 240, dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (492, 120), (40, 90, 180), -1)  # Blue banner
    cv2.putText(img, text, (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)

    cv2.putText(img, f"NAFDAC REG NO: {nafdac}", (40, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    cv2.putText(img, f"BATCH: {batch} EXP: {expiry}", (40, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2)

    # Security circle
    cv2.circle(img, (400, 240), 40, (100, 30, 180), 3)

    _, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return base64.b64encode(buffer).decode("utf-8")


@pytest.mark.asyncio
async def test_e2e_scenario_1_genuine_product(
    async_session: AsyncSession,
    vector_store: InMemoryVectorStore,
    monkeypatch,
):
    """Scenario 1: Verified genuine scan of active packaging design."""
    product = Product(
        id=uuid.uuid4(),
        brand_name="Coartem 80/480",
        generic_name="Artemether / Lumefantrine",
        manufacturer="Novartis Pharma",
        category="pharmaceuticals_antimalarials",
        primary_nafdac_number="04-1234",
        gtin_list=["06151234567891"],
    )
    async_session.add(product)
    await async_session.flush()

    active_version = ProductVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_label="2025_Design_v1",
        valid_from=date(2025, 1, 1),
        status="active",
    )
    async_session.add(active_version)
    await async_session.commit()

    pack_b64 = _generate_synthetic_pack_b64(text="COARTEM 80/480", nafdac="04-1234", batch="B1001")

    pipeline = VerificationPipeline(async_session, vector_store)
    # Mock barcode decoder to return valid decoded payload
    from genie.barcode.decode import MultiDecoder
    monkeypatch.setattr(
        MultiDecoder,
        "decode",
        lambda img: {"gtin": "06151234567891", "check_digit_valid": True, "batch": "B1001", "expiry": "2027-12-31"},
    )

    request = ScanRequest(
        images=[ScanImage(image_bytes_base64=pack_b64, face_type="front")],
        manual_gtin="06151234567891",
        manual_nafdac="04-1234",
    )

    response = await pipeline.verify_scan(request)

    assert response.verdict == VerdictState.CONSISTENT_WITH_GENUINE
    assert response.confidence >= 0.85
    assert response.matched_product_name == "Coartem 80/480"
    assert response.matched_version_label == "2025_Design_v1"
    assert response.is_legacy_version is False
    assert "Consistent with genuine" in response.explanation
    assert response.execution_time_ms < 4000.0


@pytest.mark.asyncio
async def test_e2e_scenario_2_counterfeit_batch_discrepancy(
    async_session: AsyncSession,
    vector_store: InMemoryVectorStore,
    monkeypatch,
):
    """Scenario 2: Counterfeit product with batch number contradiction between printed text and barcode."""
    product = Product(
        id=uuid.uuid4(),
        brand_name="Coartem 80/480",
        manufacturer="Novartis Pharma",
        primary_nafdac_number="04-1234",
        gtin_list=["06151234567891"],
    )
    async_session.add(product)
    await async_session.flush()

    active_version = ProductVersion(
        id=uuid.uuid4(),
        product_id=product.id,
        version_label="2025_Design_v1",
        valid_from=date(2025, 1, 1),
        status="active",
    )
    async_session.add(active_version)
    await async_session.commit()

    # Image printed batch is B9999
    pack_b64 = _generate_synthetic_pack_b64(text="COARTEM 80/480", batch="B9999")

    pipeline = VerificationPipeline(async_session, vector_store)
    # Mock barcode decoder with batch LOT_ORIGINAL_123
    from genie.barcode.decode import MultiDecoder
    from genie.vision.ocr import OCRExtractionResult
    monkeypatch.setattr(
        MultiDecoder,
        "decode",
        lambda img: {"gtin": "06151234567891", "batch": "LOT_ORIGINAL_123", "check_digit_valid": True},
    )
    # Mock OCR extraction to return printed batch B9999
    monkeypatch.setattr(
        pipeline.ocr,
        "extract_text",
        lambda img: OCRExtractionResult(
            full_text="BN: B9999 NAFDAC: 04-1234",
            raw_text_lines=["BN: B9999", "NAFDAC: 04-1234"],
            batch_number="B9999",
            nafdac_number="04-1234",
        ),
    )

    request = ScanRequest(
        images=[ScanImage(image_bytes_base64=pack_b64, face_type="front")],
        manual_gtin="06151234567891",
        manual_nafdac="04-1234",
    )

    response = await pipeline.verify_scan(request)

    assert response.verdict == VerdictState.SUSPICIOUS
    assert response.confidence >= 0.90
    assert "Suspicious product detected" in response.explanation
