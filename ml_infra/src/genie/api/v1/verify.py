"""Verification API router."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from genie.api.deps import get_db, get_vector_store
from genie.schemas.scan import ScanRequest
from genie.schemas.verdict import VerificationResponse
from genie.storage.vector_store import VectorStore
from genie.verification.pipeline import VerificationPipeline

router = APIRouter(tags=["Verification"])


@router.post("/verify", response_model=VerificationResponse)
async def verify_scan(
    request: ScanRequest,
    db: AsyncSession = Depends(get_db),
    vector_store: VectorStore = Depends(get_vector_store),
):
    """
    Main Genium consumer scan endpoint.
    Executes image quality gating, pack rectification, barcode decode, OCR,
    candidate resolution, and calibrated multi-signal fusion (<4s latency budget).
    """
    pipeline = VerificationPipeline(db_session=db, vector_store=vector_store)
    return await pipeline.verify_scan(request)
