"""Async HTTP client and dossier sync bridge from `ml_infra` to `genie-ai`."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from genie.common.config import settings
from genie.schemas.verdict import SaferAlternative, SignalBreakdown, VerificationResponse, VerdictState

logger = logging.getLogger(__name__)


class GenieAIClient:
    """Thin async client calling the `genie-ai` Product Intelligence & Verification API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        raw = base_url if base_url is not None else settings.GENIE_AI_URL
        self.base_url = raw.rstrip("/") if raw else None
        self.timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(settings.GENIE_AI_TIMEOUT_SECONDS)
        )

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    async def health(self) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(f"{self.base_url}/v1/health")
            resp.raise_for_status()
            return resp.json()

    async def verify_ml_infra_payload(
        self,
        payload: Dict[str, Any],
        *,
        auto_discover: bool = True,
    ) -> Optional[VerificationResponse]:
        """Delegate final multi-signal verification to `genie-ai` (`POST /v1/verify/ml-infra`)."""
        if not self.enabled:
            return None
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                f"{self.base_url}/v1/verify/ml-infra",
                params={"auto_discover": str(auto_discover).lower()},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        verdict_val = data.get("verdict", VerdictState.CANNOT_VERIFY.value)
        try:
            verdict_enum = VerdictState(verdict_val)
        except ValueError:
            verdict_enum = VerdictState.CANNOT_VERIFY

        signals_data = data.get("signals") or {}
        alts = [
            SaferAlternative.model_validate(item)
            for item in (data.get("safer_alternatives") or [])
        ]
        return VerificationResponse(
            verdict=verdict_enum,
            confidence=float(data.get("confidence", 0.0)),
            matched_product_name=data.get("matched_product_name"),
            matched_version_label=data.get("matched_version_label"),
            is_legacy_version=bool(data.get("is_legacy_version", False)),
            explanation=str(data.get("explanation") or ""),
            signals=SignalBreakdown(**signals_data),
            visual_anomaly_heatmap_url=data.get("visual_anomaly_heatmap_url"),
            safer_alternatives=alts,
            execution_time_ms=float(data.get("execution_time_ms", 0.0)),
        )

    async def trigger_discovery(
        self,
        *,
        product_name: Optional[str] = None,
        nafdac_number: Optional[str] = None,
        manufacturer: Optional[str] = None,
        gtin: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Enqueue a real background discovery job in `genie-ai` (`POST /v1/discovery/jobs`)."""
        if not self.enabled:
            return None
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                f"{self.base_url}/v1/discovery/jobs",
                json={
                    "product_name": product_name,
                    "nafdac_number": nafdac_number,
                    "manufacturer": manufacturer,
                    "gtin": gtin,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_discovery_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(f"{self.base_url}/v1/jobs/{job_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def list_products(self) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(f"{self.base_url}/v1/products")
            resp.raise_for_status()
            return resp.json()


def sync_genie_ai_dossiers_to_index(genie_ai_products_dir: Path | str) -> List[Dict[str, Any]]:
    """Read approved reference images from `genie-ai/data/products/` for `ml_infra` indexing.

    Returns a normalized list of product + approved reference image records ready to be
    ingested into `ml_infra`'s `ReferencePackIndexer`.
    """
    root = Path(genie_ai_products_dir)
    if not root.is_dir():
        return []

    records: List[Dict[str, Any]] = []
    for prod_json in sorted(root.glob("*/product.json")):
        try:
            dossier = json.loads(prod_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue

        approved_images: List[Dict[str, Any]] = []
        for ver in dossier.get("packaging_versions") or []:
            edition_id = ver.get("edition_id") or "edition_1"
            for img in ver.get("images") or []:
                if img.get("status") != "approved":
                    continue
                rel = img.get("storage_path")
                if not rel:
                    continue
                full_path = prod_json.parent / rel
                if not full_path.is_file():
                    continue
                approved_images.append(
                    {
                        "edition_id": edition_id,
                        "is_primary": bool(ver.get("is_primary")),
                        "face_type": img.get("view_type") or "front_box",
                        "image_path": str(full_path),
                        "source_url": img.get("source_page_url") or img.get("source_url"),
                        "trust_tier": int(img.get("source_trust_tier") or 1),
                    }
                )

        if approved_images:
            records.append(
                {
                    "slug": prod_json.parent.name,
                    "brand_name": dossier.get("brand_name"),
                    "nafdac_number": dossier.get("nafdac_number"),
                    "manufacturer": dossier.get("manufacturer"),
                    "gtins": dossier.get("gtins") or [],
                    "approved_images": approved_images,
                }
            )
    return records
