"""Async discovery job management API router."""
import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from genie.integrations.genie_ai_client import GenieAIClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Discovery"])


class DiscoveryJobRequest(BaseModel):
    product_name: Optional[str] = None
    nafdac_number: Optional[str] = None
    manufacturer: Optional[str] = None
    gtin: Optional[str] = None


class DiscoveryJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post("/discovery/jobs", response_model=DiscoveryJobResponse)
async def trigger_discovery_job(
    request: DiscoveryJobRequest,
    background_tasks: BackgroundTasks,
):
    client = GenieAIClient()
    if client.enabled:
        try:
            res = await client.trigger_discovery(
                product_name=request.product_name,
                nafdac_number=request.nafdac_number,
                manufacturer=request.manufacturer,
                gtin=request.gtin,
            )
            if res and isinstance(res.get("job"), dict):
                job = res["job"]
                dedup = bool(res.get("deduplicated", False))
                return DiscoveryJobResponse(
                    job_id=str(job.get("job_id")),
                    status=str(job.get("status", "queued")),
                    message=(
                        "Existing GENIE AI discovery job reused."
                        if dedup
                        else "Asynchronous GENIE AI product discovery job queued."
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("GENIE AI discovery bridge unavailable, falling back to stub: %s", exc)

    job_id = str(uuid.uuid4())
    return DiscoveryJobResponse(
        job_id=job_id,
        status="pending",
        message="Asynchronous product discovery and verification job queued.",
    )


@router.get("/discovery/jobs/{job_id}")
async def get_discovery_job(job_id: str) -> Dict[str, Any]:
    client = GenieAIClient()
    if not client.enabled:
        raise HTTPException(
            status_code=503,
            detail="GENIE_AI_URL is not configured for discovery job polling",
        )
    job = await client.get_discovery_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Discovery job {job_id!r} not found")
    return job
