"""Structured dossier synthesis and multimodal packaging image verification."""
from __future__ import annotations

import json
import time
from typing import Callable, Dict, List, Optional, Tuple

from discovery.models import DiscoveryBundle

from .images import (
    DownloadedImage,
    collect_candidate_image_urls,
    download_and_deduplicate_images,
    prepare_image_for_llm,
)
from .llm import LLMProvider, get_default_provider
from .schemas import (
    BatchImageVerificationResponse,
    CandidateProductDossier,
    ExtractedDossierResponse,
    PackagingVersion,
    VerifiedReferenceImage,
)
from .storage import ImageStorage, LocalImageStorage

DOSSIER_SYSTEM_INSTRUCTION = """You are GENIE AI's pharmaceutical intelligence extraction engine.
Your job is to synthesize a structured Product Dossier ONLY from the provided NAFDAC Greenbook records and scraped web/SmPC sources.

Strict grounding rules:
1. Never invent, extrapolate, or guess drug details, NAFDAC registration numbers, strengths, pack sizes, or manufacturers. If a field is not supported by the sources, leave it null or [].
2. For EVERY populated field (such as brand_name, generic_name, active_ingredients, strength, dosage_form, pack_size, manufacturer, nafdac_number, registration_status, packaging_description, recall_alerts, version_notes), emit at least one entry in `claims`.
3. Every `EvidenceClaim` MUST specify:
   - `field_name`: the schema field name it supports
   - `value`: the concise extracted value
   - `source_url`: the exact `source_url` from the prompt where this evidence came from
   - `verbatim_quote`: an EXACT, contiguous substring copied character-for-character from that source's text (do not paraphrase or alter numbers).
4. Prefer Tier 1 regulatory/Greenbook and official manufacturer sources over Tier 2/3 when summarizing canonical identity, and surface any recall alerts or packaging change notices in `recall_alerts` and `version_notes`."""

IMAGE_VERIFY_SYSTEM_INSTRUCTION = """You are GENIE AI's pharmaceutical visual verification specialist.
Evaluate each candidate image strictly against the target pharmaceutical product AND compare candidate images against each other to separate distinct packaging editions.

Rules for every `candidate_index`:
1. Set `is_product_packaging=true` ONLY if the image clearly depicts actual pharmaceutical packaging (box, bottle, blister pack, vial, sachet, or package leaflet). Reject website logos, icons, generic pill stock photos, doctor/lifestyle photos, and marketing banners.
2. Set `matches_target_product=true` ONLY if visible branding, product name, dosage strength, pack size, and manufacturer are consistent with the target product (reject images showing a clearly different strength, pack count, or unrelated brand).
3. Set `is_real_photo=false` for flat 3D CGI renders, vector mockups, or generic studio illustrations; set `true` for real photographs of physical packaging.
4. Set `has_local_regulatory_markers=true` if the image visibly shows Nigerian regulatory/authentication markings such as a `NAFDAC` registration number, `Scratch PIN` / Sproxil / MAS authentication sticker, or Nigerian distributor/importer markings.
5. Group visually matching packaging designs using `packaging_edition_id` (`edition_1`, `edition_2`, etc.):
   - Assign the SAME `packaging_edition_id` ONLY when two images depict the exact same packaging design (same logo style & placement, color/stripe layout, and security feature style).
   - Assign a DIFFERENT `packaging_edition_id` if logo style/placement, stripe patterns, or security labels differ (e.g. old black logo vs. new orange logo), and briefly describe the edition in `edition_summary`.
6. Classify `view_type` accurately (`front_box`, `back_box`, `blister_pack`, `bottle`, `leaflet`, or `other`).
7. Extract visible `visible_cues` and `visible_text_snippets` (printed drug name, strength, pack count, NAFDAC number, MAN/EXP dates if readable).
8. Set `quality_ok=false` for blurry, unreadable, cropped-out, or heavily watermarked images, and provide a concise `rejection_reason` whenever any check fails."""


def _format_greenbook_source(match: Dict) -> str:
    source_url = str(match.get("detail_url") or "")
    lines = [
        f"### NAFDAC Greenbook Record (Tier 1 Regulatory Mirror)",
        f"source_url: {source_url}",
        f"Product Name: {match.get('product_name', '')}",
        f"NAFDAC Number: {match.get('nafdac_number', '')}",
        f"Active Ingredients: {match.get('ingredient_name', '')}",
        f"Strength: {match.get('strength', '')}",
        f"Dosage Form: {match.get('form_name', '')}",
        f"Route: {match.get('route_name', '')}",
        f"Applicant / Manufacturer: {match.get('applicant_name', '')}",
        f"Pack Size: {match.get('pack_size', '')}",
        f"Registration Status: {match.get('status', '')}",
        f"Approval Date: {match.get('approval_date', '')}",
        f"Expiry Date: {match.get('expiry_date', '')}",
        f"Composition: {match.get('composition', '')}",
        f"Product Description: {match.get('product_description', '')}",
    ]
    return "\n".join(line for line in lines if not line.endswith(": "))


def build_dossier_prompt(
    bundle: DiscoveryBundle,
    *,
    max_chars_per_source: int = 4000,
) -> str:
    """Serialize Greenbook records and scraped discovery sources for grounded LLM synthesis."""
    sections: List[str] = [
        "## Discovery Seed",
        f"Original Seed: {json.dumps(bundle.seed.to_dict(), ensure_ascii=False)}",
        f"Enriched Seed: {json.dumps(bundle.enriched_seed.to_dict(), ensure_ascii=False)}",
    ]

    if bundle.greenbook_matches:
        sections.append("## Local Regulatory Baseline (NAFDAC Greenbook)")
        for match in bundle.greenbook_matches[:3]:
            sections.append(_format_greenbook_source(match))

    if bundle.sources:
        sections.append("## Scraped Web & SmPC Sources")
        for idx, src in enumerate(bundle.sources):
            parts = [
                f"### Source {idx + 1} (Tier {src.trust_tier} - {src.trust_label})",
                f"source_url: {src.url}",
                f"title: {src.title}",
                f"angles: {', '.join(src.angles)}",
                f"is_smpc_pdf: {src.is_smpc_pdf}",
            ]
            if src.product:
                parts.append(f"json_ld_product: {json.dumps(src.product, ensure_ascii=False)}")
            if src.identifiers and (src.identifiers.get("nafdac_numbers") or src.identifiers.get("gtins")):
                parts.append(f"extracted_identifiers: {json.dumps(src.identifiers, ensure_ascii=False)}")
            text = (src.content or "")[:max_chars_per_source].strip()
            parts.append(f"content:\n{text}")
            sections.append("\n".join(parts))

    return "\n\n".join(sections)


def build_image_verify_prompt(
    bundle: DiscoveryBundle,
    images: List[DownloadedImage],
) -> str:
    """Build the multimodal verification prompt describing the target drug and indexed images."""
    seed = bundle.enriched_seed
    lines = [
        "## Target Pharmaceutical Product",
        f"Product Name: {seed.product_name or 'Unknown'}",
        f"Manufacturer / Applicant: {seed.manufacturer or 'Unknown'}",
        f"NAFDAC Number: {seed.nafdac_number or 'Unknown'}",
        f"GTIN: {seed.gtin or 'Unknown'}",
    ]
    if bundle.greenbook_matches:
        top = bundle.greenbook_matches[0]
        lines.extend(
            [
                f"Active Ingredients: {top.get('ingredient_name') or 'Unknown'}",
                f"Strength: {top.get('strength') or 'Unknown'}",
                f"Dosage Form: {top.get('form_name') or 'Unknown'}",
                f"Pack Size: {top.get('pack_size') or 'Unknown'}",
                f"Official Description: {top.get('product_description') or 'N/A'}",
            ]
        )

    lines.append("")
    lines.append(
        "## Candidate Images (attached in exact 0-based order below; evaluate every index)"
    )
    for idx, img in enumerate(images):
        lines.append(
            f"Candidate {idx}: url={img.url} | source_page={img.source_page_url} | "
            f"trust_tier={img.source_trust_tier} | extraction={img.extraction_source} | "
            f"dimensions={img.width}x{img.height} | alt={img.alt!r}"
        )
    return "\n".join(lines)


def _derive_product_key(bundle: DiscoveryBundle) -> str:
    seed = bundle.enriched_seed
    return seed.nafdac_number or seed.product_name or seed.gtin or "unknown"


def verify_images(
    bundle: DiscoveryBundle,
    provider: LLMProvider,
    storage: ImageStorage,
    *,
    product_key: Optional[str] = None,
    max_unique: int = 6,
    downloader: Optional[Callable[[str], Tuple[bytes, str]]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[List[VerifiedReferenceImage], List[Dict], Dict[str, str]]:
    """Download, deduplicate, visually verify via multimodal LLM, and persist valid packaging images."""
    candidates = collect_candidate_image_urls(bundle)
    if not candidates:
        return [], [], {}

    if progress_cb:
        progress_cb(f"[3b] Downloading & deduplicating {len(candidates)} candidate image(s)...")
    t_dl = time.monotonic()
    kept, rejected = download_and_deduplicate_images(
        candidates,
        max_unique=max_unique,
        downloader=downloader,
    )
    if progress_cb:
        progress_cb(
            f"[3b] Image download done in {time.monotonic() - t_dl:.1f}s "
            f"({len(kept)} unique kept, {len(rejected)} pre-filtered)"
        )
    if not kept:
        return [], rejected, {}

    prompt = build_image_verify_prompt(bundle, kept)
    image_parts = [prepare_image_for_llm(img.raw_bytes, img.mime_type) for img in kept]
    if progress_cb:
        progress_cb(f"[3c] Verifying {len(image_parts)} unique image(s) with {provider.model_name}...")
    t_vis = time.monotonic()
    batch_res = provider.generate_structured_with_images(
        prompt,
        image_parts,
        BatchImageVerificationResponse,
        system_instruction=IMAGE_VERIFY_SYSTEM_INSTRUCTION,
    )
    if progress_cb:
        progress_cb(f"[3c] Visual verification done in {time.monotonic() - t_vis:.1f}s")

    checks_by_idx = {item.candidate_index: item for item in batch_res.results}
    key = product_key or _derive_product_key(bundle)

    # Check if at least one real physical photograph passed so we can drop 3D stock renders
    has_real_photo = any(
        (c := checks_by_idx.get(idx)) is not None
        and c.is_product_packaging
        and c.matches_target_product
        and c.quality_ok
        and c.is_real_photo
        for idx in range(len(kept))
    )

    verified: List[VerifiedReferenceImage] = []
    edition_summaries: Dict[str, str] = {}

    for idx, img in enumerate(kept):
        check = checks_by_idx.get(idx)
        if check is None:
            rejected.append({"url": img.url, "reason": "llm_omitted"})
            continue

        if not check.is_product_packaging:
            rejected.append(
                {
                    "url": img.url,
                    "reason": "not_product_packaging",
                    "detail": check.rejection_reason,
                }
            )
            continue
        if not check.matches_target_product:
            rejected.append(
                {
                    "url": img.url,
                    "reason": "wrong_product",
                    "detail": check.rejection_reason,
                }
            )
            continue
        if not check.quality_ok:
            rejected.append(
                {
                    "url": img.url,
                    "reason": "low_quality",
                    "detail": check.rejection_reason,
                }
            )
            continue
        if has_real_photo and not check.is_real_photo:
            rejected.append(
                {
                    "url": img.url,
                    "reason": "stock_render",
                    "detail": check.rejection_reason or "3D render/mockup dropped because real packaging photos exist",
                }
            )
            continue

        edition_id = (check.packaging_edition_id or "edition_1").strip() or "edition_1"
        if check.edition_summary and edition_id not in edition_summaries:
            edition_summaries[edition_id] = check.edition_summary

        storage_path = storage.save(key, img.sha256, img.raw_bytes, img.mime_type)
        verified.append(
            VerifiedReferenceImage(
                image_id=img.sha256[:16],
                storage_path=storage_path,
                source_url=img.url,
                source_page_url=img.source_page_url,
                source_trust_tier=img.source_trust_tier,
                sha256=img.sha256,
                dhash=img.dhash,
                width=img.width,
                height=img.height,
                mime_type=img.mime_type,
                view_type=check.view_type,
                packaging_edition_id=edition_id,
                is_real_photo=check.is_real_photo,
                has_local_regulatory_markers=check.has_local_regulatory_markers,
                visible_cues=list(check.visible_cues),
                visible_text_snippets=list(check.visible_text_snippets),
                status="staging",
            )
        )

    return verified, rejected, edition_summaries


def group_packaging_versions(
    images: List[VerifiedReferenceImage],
    edition_summaries: Optional[Dict[str, str]] = None,
) -> List[PackagingVersion]:
    """Group verified images by packaging edition and mark the strongest Nigerian edition as primary."""
    if not images:
        return []
    summaries = edition_summaries or {}
    buckets: Dict[str, List[VerifiedReferenceImage]] = {}
    for img in images:
        buckets.setdefault(img.packaging_edition_id or "edition_1", []).append(img)

    versions: List[PackagingVersion] = []
    for edition_id, imgs in buckets.items():
        has_reg = any(i.has_local_regulatory_markers for i in imgs)
        versions.append(
            PackagingVersion(
                edition_id=edition_id,
                summary=summaries.get(edition_id),
                is_primary=False,
                has_local_regulatory_markers=has_reg,
                status="staging",
                images=imgs,
            )
        )

    def _rank_key(v: PackagingVersion) -> tuple:
        best_res = max((i.width * i.height for i in v.images), default=0)
        best_tier = min((i.source_trust_tier for i in v.images), default=3)
        return (
            not v.has_local_regulatory_markers,
            best_tier,
            -best_res,
            -len(v.images),
            v.edition_id,
        )

    versions.sort(key=_rank_key)
    versions[0].is_primary = True
    return versions


def synthesize_dossier(
    bundle: DiscoveryBundle,
    *,
    provider: Optional[LLMProvider] = None,
    storage: Optional[ImageStorage] = None,
    product_key: Optional[str] = None,
    verify_visuals: bool = True,
    max_unique_images: int = 6,
    image_downloader: Optional[Callable[[str], Tuple[bytes, str]]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> CandidateProductDossier:
    """Synthesize a source-grounded CandidateProductDossier from a DiscoveryBundle."""
    t0 = time.monotonic()
    active_provider = provider or get_default_provider()
    active_storage = storage or LocalImageStorage()

    dossier_prompt = build_dossier_prompt(bundle)
    if progress_cb:
        progress_cb(f"[3a] Synthesizing dossier with {active_provider.model_name}...")
    t_dos = time.monotonic()
    extracted = active_provider.generate_structured(
        dossier_prompt,
        ExtractedDossierResponse,
        system_instruction=DOSSIER_SYSTEM_INSTRUCTION,
    )
    if progress_cb:
        progress_cb(
            f"[3a] Dossier synthesized in {time.monotonic() - t_dos:.1f}s "
            f"(model={active_provider.model_name})"
        )

    verified_images: List[VerifiedReferenceImage] = []
    rejected_images: List[Dict] = []
    packaging_versions: List[PackagingVersion] = []
    if verify_visuals:
        verified_images, rejected_images, edition_summaries = verify_images(
            bundle,
            active_provider,
            active_storage,
            product_key=product_key,
            max_unique=max_unique_images,
            downloader=image_downloader,
            progress_cb=progress_cb,
        )
        packaging_versions = group_packaging_versions(verified_images, edition_summaries)

    elapsed = round(time.monotonic() - t0, 3)
    return CandidateProductDossier(
        seed=bundle.seed.to_dict(),
        enriched_seed=bundle.enriched_seed.to_dict(),
        brand_name=extracted.brand_name,
        generic_name=extracted.generic_name,
        active_ingredients=list(extracted.active_ingredients),
        strength=extracted.strength,
        dosage_form=extracted.dosage_form,
        pack_size=extracted.pack_size,
        manufacturer=extracted.manufacturer,
        nafdac_number=extracted.nafdac_number,
        registration_status=extracted.registration_status,
        packaging_description=extracted.packaging_description,
        color_scheme=list(extracted.color_scheme),
        distinctive_features=list(extracted.distinctive_features),
        recall_alerts=list(extracted.recall_alerts),
        version_notes=list(extracted.version_notes),
        claims=list(extracted.claims),
        packaging_versions=packaging_versions,
        reference_images=verified_images,
        rejected_images=rejected_images,
        model_used=active_provider.model_name,
        stats={
            "elapsed_s": elapsed,
            "claims_count": len(extracted.claims),
            "packaging_versions_count": len(packaging_versions),
            "reference_images_count": len(verified_images),
            "rejected_images_count": len(rejected_images),
            "sources_used": len(bundle.sources),
            "greenbook_matches_used": len(bundle.greenbook_matches),
        },
    )
