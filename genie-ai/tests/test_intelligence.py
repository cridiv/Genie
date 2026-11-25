"""Offline unit tests for Step 3 Dossier Synthesis & Visual Verification."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional, Tuple, Type
from unittest import mock

from PIL import Image, ImageDraw

from discovery.models import DiscoveredSource, DiscoveryBundle, DiscoverySeed
from intelligence import (
    BatchImageVerificationResponse,
    CounterfeitTell,
    EvidenceClaim,
    ExtractedDossierResponse,
    GeminiProvider,
    LocalImageStorage,
    NvidiaProvider,
    PackagingVersion,
    RawImageCheck,
    SecurityFeatureSpec,
    VerifiedReferenceImage,
    build_dossier_prompt,
    collect_candidate_image_urls,
    compute_dhash,
    compute_reference_level,
    download_and_deduplicate_images,
    extract_smpc_key_sections,
    get_default_provider,
    hamming_distance,
    parse_allowed_pack_counts,
    parse_shelf_life_months,
    synthesize_dossier,
    verify_images,
)
from intelligence.llm import _extract_json_object


def _make_pattern_image(
    size: Tuple[int, int] = (400, 400),
    *,
    variant: str = "box_a",
    fmt: str = "JPEG",
) -> bytes:
    img = Image.new("RGB", size, color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    w, h = size
    if variant == "box_a":
        draw.rectangle([20, 20, w - 20, h // 3], fill=(220, 60, 20))
        draw.rectangle([40, h // 2, w - 40, h - 30], fill=(30, 80, 180))
        draw.ellipse([w // 3, h // 4, 2 * w // 3, 2 * h // 3], fill=(250, 220, 40))
    elif variant == "box_b":
        draw.rectangle([0, 0, w // 2, h], fill=(15, 110, 70))
        draw.polygon([(w // 2, 20), (w - 20, h // 2), (w // 2, h - 20)], fill=(230, 230, 230))
        draw.line([(0, 0), (w, h)], fill=(10, 10, 10), width=12)
    else:
        draw.rectangle([50, 50, w - 50, h - 50], fill=(120, 40, 160))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


class MockLLMProvider:
    model_name = "mock-gemini-2.5-flash"

    def __init__(
        self,
        dossier_response: ExtractedDossierResponse,
        image_response: BatchImageVerificationResponse,
    ) -> None:
        self._dossier_response = dossier_response
        self._image_response = image_response
        self.text_prompts: List[str] = []
        self.image_calls: List[Tuple[str, int]] = []

    def generate_structured(
        self,
        prompt: str,
        schema: Type,
        *,
        system_instruction: Optional[str] = None,
    ):
        self.text_prompts.append(prompt)
        return schema.model_validate(self._dossier_response.model_dump())

    def generate_structured_with_images(
        self,
        prompt: str,
        images: List[Tuple[bytes, str]],
        schema: Type,
        *,
        system_instruction: Optional[str] = None,
    ):
        self.image_calls.append((prompt, len(images)))
        return schema.model_validate(self._image_response.model_dump())


class TestImagesAndStorage(unittest.TestCase):
    def test_dhash_similarity_for_resized_and_distinct_images(self) -> None:
        raw_a_400 = _make_pattern_image((400, 400), variant="box_a", fmt="PNG")
        with Image.open(io.BytesIO(raw_a_400)) as im_400:
            im_resized = im_400.resize((300, 300), Image.Resampling.LANCZOS)
            h1 = compute_dhash(im_400)
            h2 = compute_dhash(im_resized)

        raw_b = _make_pattern_image((400, 400), variant="box_b", fmt="PNG")
        with Image.open(io.BytesIO(raw_b)) as im_b:
            hb = compute_dhash(im_b)

        self.assertLessEqual(hamming_distance(h1, h2), 6)
        self.assertGreater(hamming_distance(h1, hb), 6)

    def test_download_and_deduplicate_filters_tiny_banner_and_duplicates(self) -> None:
        box_a_big = _make_pattern_image((500, 500), variant="box_a", fmt="JPEG")
        with Image.open(io.BytesIO(box_a_big)) as im:
            buf = io.BytesIO()
            im.resize((360, 360), Image.Resampling.LANCZOS).save(buf, format="JPEG", quality=80)
            box_a_resized = buf.getvalue()
        box_b = _make_pattern_image((400, 400), variant="box_b", fmt="PNG")
        tiny = _make_pattern_image((120, 120), variant="box_a", fmt="JPEG")
        banner = _make_pattern_image((1400, 360), variant="box_b", fmt="JPEG")

        payloads = {
            "https://example.com/tiny.jpg": (tiny, "image/jpeg"),
            "https://example.com/banner.jpg": (banner, "image/jpeg"),
            "https://example.com/a1.jpg": (box_a_big, "image/jpeg"),
            "https://example.com/a1-exact.jpg": (box_a_big, "image/jpeg"),
            "https://example.com/a1-resized.jpg": (box_a_resized, "image/jpeg"),
            "https://example.com/b1.png": (box_b, "image/png"),
        }
        candidates = [{"url": u, "source_page_url": "https://example.com", "source_trust_tier": 1} for u in payloads]

        kept, rejected = download_and_deduplicate_images(
            candidates,
            downloader=lambda u: payloads[u],
        )
        self.assertEqual([k.url for k in kept], ["https://example.com/a1.jpg", "https://example.com/b1.png"])
        reasons = {r["url"]: r["reason"] for r in rejected}
        self.assertEqual(reasons["https://example.com/tiny.jpg"], "too_small")
        self.assertEqual(reasons["https://example.com/banner.jpg"], "banner_aspect")
        self.assertEqual(reasons["https://example.com/a1-exact.jpg"], "duplicate_sha256")
        self.assertEqual(reasons["https://example.com/a1-resized.jpg"], "duplicate_dhash")

    def test_local_image_storage_idempotent_save_read_and_traversal_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalImageStorage(tmp)
            data = b"fake-jpeg-bytes"
            rel1 = storage.save("04-1928 / Augmentin", "abcdef1234567890ffff", data, "image/jpeg")
            rel2 = storage.save("04-1928 / Augmentin", "abcdef1234567890ffff", data, "image/jpeg")
            self.assertEqual(rel1, rel2)
            self.assertEqual(rel1, "04-1928_augmentin/abcdef1234567890.jpg")
            self.assertTrue(storage.exists(rel1))
            self.assertEqual(storage.read(rel1), data)
            with self.assertRaises(ValueError):
                storage.resolve("../outside.jpg")


class TestDossierSynthesis(unittest.TestCase):
    def _sample_bundle(self) -> DiscoveryBundle:
        seed = DiscoverySeed(product_name="Augmentin 625mg")
        enriched = DiscoverySeed(
            product_name="Augmentin 625 mg",
            manufacturer="GlaxoSmithKline Consumer Nigeria PLC (GSK)",
            nafdac_number="04-1928",
        )
        gb_match = {
            "product_id": 42,
            "product_name": "Augmentin 625 mg",
            "nafdac_number": "04-1928",
            "ingredient_name": "Amoxicillin; Clavulanic Acid",
            "strength": "500 mg; 125 mg",
            "form_name": "Tablet",
            "route_name": "Oral",
            "applicant_name": "GlaxoSmithKline Consumer Nigeria PLC (GSK)",
            "pack_size": "2 x 7's",
            "status": "Active",
            "detail_url": "https://greenbook.nafdac.gov.ng/products/details/42",
        }
        src = DiscoveredSource(
            url="https://gsk.com/en-ng/augmentin-625",
            canonical_url="https://gsk.com/en-ng/augmentin-625",
            domain="gsk.com",
            trust_tier=1,
            trust_label="official_manufacturer",
            angles=["manufacturer"],
            title="Augmentin 625mg Official Pack",
            content="Augmentin 625mg white film-coated tablets in white and orange carton. NAFDAC 04-1928.",
            stage="static",
            images=[
                {"url": "https://gsk.com/augmentin-front.jpg", "source": "jsonld", "alt": "Augmentin 625mg box"},
                {"url": "https://gsk.com/logo-badge.png", "source": "img", "alt": "Logo"},
                {"url": "https://gsk.com/augmentin-375.jpg", "source": "img", "alt": "Augmentin 375mg"},
            ],
        )
        return DiscoveryBundle(
            seed=seed,
            enriched_seed=enriched,
            greenbook_matches=[gb_match],
            sources=[src],
        )

    def test_verify_images_persists_only_valid_packaging_photos(self) -> None:
        bundle = self._sample_bundle()
        payloads = {
            "https://gsk.com/augmentin-front.jpg": (_make_pattern_image((400, 400), variant="box_a"), "image/jpeg"),
            "https://gsk.com/logo-badge.png": (_make_pattern_image((400, 400), variant="box_b", fmt="PNG"), "image/png"),
            "https://gsk.com/augmentin-375.jpg": (_make_pattern_image((400, 400), variant="other"), "image/jpeg"),
        }
        provider = MockLLMProvider(
            dossier_response=ExtractedDossierResponse(),
            image_response=BatchImageVerificationResponse(
                results=[
                    RawImageCheck(
                        candidate_index=0,
                        is_product_packaging=True,
                        matches_target_product=True,
                        view_type="front_box",
                        visible_cues=["white and orange box"],
                        visible_text_snippets=["Augmentin 625mg"],
                        quality_ok=True,
                    ),
                    RawImageCheck(
                        candidate_index=1,
                        is_product_packaging=False,
                        matches_target_product=False,
                        view_type="other",
                        quality_ok=True,
                        rejection_reason="Company logo, not product box",
                    ),
                    RawImageCheck(
                        candidate_index=2,
                        is_product_packaging=True,
                        matches_target_product=False,
                        view_type="front_box",
                        quality_ok=True,
                        rejection_reason="Shows 375mg instead of 625mg",
                    ),
                ]
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalImageStorage(tmp)
            verified, rejected, _summaries = verify_images(
                bundle,
                provider,
                storage,
                downloader=lambda u: payloads[u],
            )
            self.assertEqual(len(verified), 1)
            self.assertEqual(verified[0].view_type, "front_box")
            self.assertEqual(verified[0].status, "staging")
            self.assertTrue(storage.exists(verified[0].storage_path))
            self.assertEqual(len(rejected), 2)
            self.assertEqual([r["reason"] for r in rejected], ["not_product_packaging", "wrong_product"])

    def test_synthesize_dossier_end_to_end(self) -> None:
        bundle = self._sample_bundle()
        payloads = {
            "https://gsk.com/augmentin-front.jpg": (_make_pattern_image((400, 400), variant="box_a"), "image/jpeg"),
            "https://gsk.com/logo-badge.png": (_make_pattern_image((400, 400), variant="box_b", fmt="PNG"), "image/png"),
            "https://gsk.com/augmentin-375.jpg": (_make_pattern_image((400, 400), variant="other"), "image/jpeg"),
        }
        dossier_resp = ExtractedDossierResponse(
            brand_name="Augmentin 625 mg",
            generic_name="Amoxicillin / Clavulanic Acid",
            active_ingredients=["Amoxicillin 500 mg", "Clavulanic Acid 125 mg"],
            strength="500 mg; 125 mg",
            dosage_form="Tablet",
            pack_size="2 x 7's",
            manufacturer="GlaxoSmithKline Consumer Nigeria PLC (GSK)",
            nafdac_number="04-1928",
            registration_status="Active",
            packaging_description="White film-coated tablets in white and orange carton",
            color_scheme=["white", "orange"],
            distinctive_features=["GSK logo"],
            claims=[
                EvidenceClaim(
                    field_name="nafdac_number",
                    value="04-1928",
                    source_url="https://greenbook.nafdac.gov.ng/products/details/42",
                    verbatim_quote="NAFDAC Number: 04-1928",
                )
            ],
        )
        img_resp = BatchImageVerificationResponse(
            results=[
                RawImageCheck(
                    candidate_index=0,
                    is_product_packaging=True,
                    matches_target_product=True,
                    view_type="front_box",
                    visible_cues=["white and orange carton"],
                    quality_ok=True,
                ),
            ]
        )
        provider = MockLLMProvider(dossier_resp, img_resp)

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalImageStorage(tmp)
            dossier = synthesize_dossier(
                bundle,
                provider=provider,
                storage=storage,
                image_downloader=lambda u: payloads[u],
            )

        self.assertEqual(dossier.brand_name, "Augmentin 625 mg")
        self.assertEqual(dossier.nafdac_number, "04-1928")
        self.assertEqual(len(dossier.claims), 1)
        self.assertEqual(len(dossier.reference_images), 1)
        self.assertEqual(dossier.stats["reference_images_count"], 1)
        self.assertEqual(dossier.stats["rejected_images_count"], 2)  # index 1 and 2 omitted by mock LLM
        self.assertEqual(dossier.model_used, "mock-gemini-2.5-flash")
        dumped = dossier.model_dump()
        self.assertIn("reference_images", dumped)

    def test_collect_candidate_images_includes_image_search_by_trust_tier(self) -> None:
        bundle = DiscoveryBundle(
            seed=DiscoverySeed(product_name="Augmentin 625 mg"),
            enriched_seed=DiscoverySeed(product_name="Augmentin 625 mg"),
            sources=[
                DiscoveredSource(
                    url="https://someblog.ng/aug",
                    canonical_url="https://someblog.ng/aug",
                    domain="someblog.ng",
                    trust_tier=3,
                    trust_label="general_web",
                    angles=["pharma_reference"],
                    title="Blog",
                    content="Augmentin",
                    stage="static",
                    images=[{"url": "https://someblog.ng/pic.jpg", "source": "img"}],
                )
            ],
            image_candidates=[
                {
                    "url": "https://medplusnigeria.com/aug-box.jpg",
                    "source_page_url": "https://medplusnigeria.com/p/aug",
                    "source_trust_tier": 2,
                    "source": "image_search",
                    "title": "Augmentin 625mg box",
                }
            ],
        )
        cands = collect_candidate_image_urls(bundle)
        self.assertEqual(
            [c["url"] for c in cands],
            ["https://medplusnigeria.com/aug-box.jpg", "https://someblog.ng/pic.jpg"],
        )

    def test_verify_images_groups_editions_and_drops_stock_renders(self) -> None:
        bundle = self._sample_bundle()
        payloads = {
            "https://gsk.com/augmentin-front.jpg": (_make_pattern_image((600, 600), variant="box_a"), "image/jpeg"),
            "https://gsk.com/logo-badge.png": (_make_pattern_image((500, 500), variant="box_b", fmt="PNG"), "image/png"),
            "https://gsk.com/augmentin-375.jpg": (_make_pattern_image((800, 800), variant="other"), "image/jpeg"),
        }
        provider = MockLLMProvider(
            dossier_response=ExtractedDossierResponse(brand_name="Augmentin 625 mg"),
            image_response=BatchImageVerificationResponse(
                results=[
                    RawImageCheck(
                        candidate_index=0,
                        is_product_packaging=True,
                        matches_target_product=True,
                        is_real_photo=False,
                        packaging_edition_id="edition_render",
                        view_type="front_box",
                        quality_ok=True,
                    ),
                    RawImageCheck(
                        candidate_index=1,
                        is_product_packaging=True,
                        matches_target_product=True,
                        is_real_photo=True,
                        has_local_regulatory_markers=False,
                        packaging_edition_id="edition_legacy",
                        edition_summary="Old black GSK logo + hologram",
                        view_type="front_box",
                        quality_ok=True,
                    ),
                    RawImageCheck(
                        candidate_index=2,
                        is_product_packaging=True,
                        matches_target_product=True,
                        is_real_photo=True,
                        has_local_regulatory_markers=True,
                        packaging_edition_id="edition_ng_current",
                        edition_summary="Orange GSK logo + Sproxil MAS PIN + NAFDAC 04-1928",
                        view_type="front_box",
                        quality_ok=True,
                    ),
                ]
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            dossier = synthesize_dossier(
                bundle,
                provider=provider,
                storage=LocalImageStorage(tmp),
                image_downloader=lambda u: payloads[u],
            )
            self.assertEqual(len(dossier.packaging_versions), 2)
            self.assertEqual(dossier.packaging_versions[0].edition_id, "edition_ng_current")
            self.assertTrue(dossier.packaging_versions[0].is_primary)
            self.assertEqual(dossier.packaging_versions[1].edition_id, "edition_legacy")
            self.assertFalse(dossier.packaging_versions[1].is_primary)
            self.assertEqual([r["reason"] for r in dossier.rejected_images], ["stock_render"])

    def test_parse_allowed_pack_counts(self) -> None:
        self.assertEqual(parse_allowed_pack_counts("3 x 6's; 4 x 6's"), {18, 24})
        self.assertEqual(parse_allowed_pack_counts("2 x 7's (in Alu-Alu blisters)"), {14})
        self.assertEqual(parse_allowed_pack_counts("1 x 500's"), {500})
        self.assertEqual(parse_allowed_pack_counts("14 tablets"), {14})

    def test_deterministic_greenbook_gates_reject_wrong_formulation_pack_and_watermark(self) -> None:
        bundle = DiscoveryBundle(
            seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
            enriched_seed=DiscoverySeed(
                product_name="Coartem 20/120 Tablets",
                manufacturer="Novartis Nigeria Limited",
                nafdac_number="04-3275",
            ),
            greenbook_matches=[
                {
                    "product_id": 8114,
                    "product_name": "Coartem 20/120 Tablets",
                    "nafdac_number": "04-3275",
                    "form_name": "Tablet",
                    "pack_size": "3 x 6's; 4 x 6's",
                    "applicant_name": "Novartis Nigeria Limited",
                    "detail_url": "https://greenbook.nafdac.gov.ng/products/details/8114",
                }
            ],
            image_candidates=[
                {
                    "url": "https://example.com/coartem-disp.jpg",
                    "source_page_url": "https://gomed.ng/product/coartem-dispersible-x6",
                    "source_trust_tier": 3,
                    "source": "image_search",
                },
                {
                    "url": "https://example.com/coartem-12.jpg",
                    "source_page_url": "https://gomed.ng/product/coartem-12",
                    "source_trust_tier": 3,
                    "source": "image_search",
                },
                {
                    "url": "https://example.com/coartem-photoroom.jpg",
                    "source_page_url": "https://medplusnig.com/product/coartem-18",
                    "source_trust_tier": 3,
                    "source": "image_search",
                },
                {
                    "url": "https://example.com/coartem-18-front.jpg",
                    "source_page_url": "https://gomed.ng/product/coartem-18",
                    "source_trust_tier": 3,
                    "source": "image_search",
                },
                {
                    "url": "https://example.com/coartem-18-back.jpg",
                    "source_page_url": "https://medplusnig.com/product/coartem-18-back",
                    "source_trust_tier": 3,
                    "source": "image_search",
                },
            ],
        )
        # 5 visually distinct 400x400 images (distinct geometric patterns so dHash doesn't collide)
        payloads = {}
        urls = [c["url"] for c in bundle.image_candidates]
        for idx, u in enumerate(urls):
            sz = (400 + idx * 10, 400 + idx * 10)
            img = Image.new("RGB", sz, color=(240, 240, 240))
            draw = ImageDraw.Draw(img)
            w, h = sz
            if idx == 0:
                draw.rectangle([0, 0, w // 2, h], fill=(220, 40, 40))
            elif idx == 1:
                draw.rectangle([0, 0, w, h // 2], fill=(40, 80, 220))
            elif idx == 2:
                draw.rectangle([w // 2, 0, w, h], fill=(30, 150, 70))
                draw.line([(0, 0), (w, h)], fill=(10, 10, 10), width=20)
            elif idx == 3:
                draw.polygon([(0, 0), (w, 0), (0, h)], fill=(200, 120, 20))
            else:
                draw.polygon([(w, 0), (w, h), (0, h)], fill=(130, 30, 180))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            payloads[u] = (buf.getvalue(), "image/jpeg")

        # Mock LLM mistakenly marks ALL 5 as matches_target_product=True
        provider = MockLLMProvider(
            dossier_response=ExtractedDossierResponse(brand_name="Coartem 20/120 Tablets"),
            image_response=BatchImageVerificationResponse(
                results=[
                    RawImageCheck(
                        candidate_index=0,
                        is_product_packaging=True,
                        matches_target_product=True,
                        detected_formulation="dispersible tablet",
                        detected_pack_count=6,
                        visible_text_snippets=["Coartem D Dispersible", "6 Dispersible Tablets"],
                        view_type="front_box",
                    ),
                    RawImageCheck(
                        candidate_index=1,
                        is_product_packaging=True,
                        matches_target_product=True,
                        detected_formulation="tablet",
                        detected_pack_count=12,
                        visible_text_snippets=["Coartem 20/120", "12 Tablets"],
                        view_type="front_box",
                    ),
                    RawImageCheck(
                        candidate_index=2,
                        is_product_packaging=True,
                        matches_target_product=True,
                        has_watermark=True,
                        detected_formulation="tablet",
                        detected_pack_count=18,
                        visible_text_snippets=["Coartem", "18 Tablets", "Photoroom"],
                        view_type="back_box",
                    ),
                    RawImageCheck(
                        candidate_index=3,
                        is_product_packaging=True,
                        matches_target_product=True,
                        detected_formulation="tablet",
                        detected_pack_count=18,
                        pack_size_variant="18 tablets",
                        packaging_edition_id="edition_peach",
                        edition_summary="Coartem 20/120mg 18 tablets peach stripe carton",
                        visible_text_snippets=["Coartem 20 mg/120 mg", "18 Tablets"],
                        view_type="front_box",
                    ),
                    RawImageCheck(
                        candidate_index=4,
                        is_product_packaging=True,
                        matches_target_product=True,
                        detected_formulation="tablet",
                        detected_pack_count=18,
                        pack_size_variant="18 tablets",
                        packaging_edition_id="edition_peach",
                        edition_summary="Coartem 20/120mg 18 tablets peach stripe carton",
                        visible_text_snippets=["Coartem 20 mg/120 mg", "18 Tablets"],
                        view_type="back_box",
                    ),
                ]
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            dossier = synthesize_dossier(
                bundle,
                provider=provider,
                storage=LocalImageStorage(tmp),
                image_downloader=lambda u: payloads[u],
            )
            reasons = {r["url"]: r["reason"] for r in dossier.rejected_images}
            self.assertEqual(reasons["https://example.com/coartem-disp.jpg"], "formulation_mismatch")
            self.assertEqual(reasons["https://example.com/coartem-12.jpg"], "pack_size_mismatch")
            self.assertEqual(reasons["https://example.com/coartem-photoroom.jpg"], "watermarked")
            self.assertEqual(len(dossier.reference_images), 2)
            self.assertEqual(len(dossier.packaging_versions), 1)
            self.assertEqual(dossier.packaging_versions[0].pack_size_variant, "18 tablets")
            self.assertEqual([i.view_type for i in dossier.packaging_versions[0].images], ["front_box", "back_box"])

    def test_gemini_provider_requires_key_and_respects_model_env(self) -> None:
        with mock.patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-pro"}, clear=True):
            provider = GeminiProvider()
            self.assertEqual(provider.model_name, "gemini-2.5-pro")
            with self.assertRaises(ValueError):
                provider.generate_structured("hello", ExtractedDossierResponse)

    def test_nvidia_provider_extracts_json_and_auto_selects_with_env_key(self) -> None:
        raw = '<think>reasoning here</think>\n```json\n{"brand_name": "Coartem"}\n```'
        self.assertEqual(_extract_json_object(raw), '{"brand_name": "Coartem"}')

        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "nvapi-test"}, clear=True):
            provider = get_default_provider()
            self.assertIsInstance(provider, NvidiaProvider)
            self.assertEqual(provider.model_name, "nvidia/nemotron-3.5-lightning-30b-a3b")

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "gem-test"}, clear=True):
            provider = get_default_provider()
            self.assertIsInstance(provider, GeminiProvider)

    def test_smpc_key_sections_survive_truncation_and_parse_shelf_life(self) -> None:
        long_middle = "Clinical pharmacology details. " * 400  # > 12,000 chars
        smpc_text = (
            "1. NAME OF THE MEDICINAL PRODUCT\nCoartem 20 mg/120 mg tablets\n"
            "3. PHARMACEUTICAL FORM\nLight yellow, round tablet with NC debossed on one side and CG on the other.\n"
            + long_middle
            + "\n6.3 Shelf life\n24 months.\n"
            + "6.4 Special precautions for storage\nDo not store above 30°C. Store in the original package.\n"
            + "6.5 Nature and contents of container\nPVC/PE/PVDC aluminium blister packs of 18 or 24 tablets.\n"
            + "7. MARKETING AUTHORISATION HOLDER\nNovartis Nigeria Limited"
        )
        extracted = extract_smpc_key_sections(smpc_text)
        self.assertIn("24 months", extracted)
        self.assertIn("Do not store above 30°C", extracted)
        self.assertIn("NC debossed", extracted)
        self.assertEqual(parse_shelf_life_months(extracted), 24)
        self.assertEqual(parse_shelf_life_months("6.3 Shelf life\n3 years"), 36)

        bundle = DiscoveryBundle(
            seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
            enriched_seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
            sources=[
                DiscoveredSource(
                    url="https://admin.greenbook.nafdac.gov.ng/smpc/coartem.pdf",
                    canonical_url="https://admin.greenbook.nafdac.gov.ng/smpc/coartem.pdf",
                    domain="admin.greenbook.nafdac.gov.ng",
                    trust_tier=1,
                    trust_label="regulatory",
                    angles=["greenbook_smpc"],
                    title="Coartem SmPC",
                    content=smpc_text,
                    stage="pdf",
                    is_smpc_pdf=True,
                )
            ],
        )
        prompt = build_dossier_prompt(bundle, max_chars_per_source=1000)
        self.assertIn("smpc_extracted_sections:", prompt)
        self.assertIn("24 months", prompt)
        self.assertIn("Do not store above 30°C", prompt)

    def test_compute_reference_level_counts_only_approved_images(self) -> None:
        def _img(view: str, status: str) -> VerifiedReferenceImage:
            return VerifiedReferenceImage(
                image_id="abc123",
                storage_path="images/abc.jpg",
                source_url="https://healthplusnigeria.com/a.jpg",
                source_page_url="https://healthplusnigeria.com/p/a",
                source_trust_tier=2,
                sha256="a" * 64,
                dhash="0" * 16,
                width=500,
                height=500,
                mime_type="image/jpeg",
                view_type=view,
                status=status,
            )

        # Staging images never count -> Level C
        v_staging = [PackagingVersion(edition_id="e1", images=[_img("front_box", "staging"), _img("back_box", "staging")])]
        self.assertEqual(compute_reference_level(v_staging), "C")

        # 1 approved view -> Level B
        v_one = [PackagingVersion(edition_id="e1", images=[_img("front_box", "approved"), _img("front_box", "approved")])]
        self.assertEqual(compute_reference_level(v_one), "B")

        # >= 2 distinct approved views -> Level A
        v_multi = [PackagingVersion(edition_id="e1", images=[_img("front_box", "approved"), _img("back_box", "approved")])]
        self.assertEqual(compute_reference_level(v_multi), "A")

    def test_synthesize_dossier_merges_gtins_shelf_life_and_normalizes_tell_source_kind(self) -> None:
        bundle = DiscoveryBundle(
            seed=DiscoverySeed(product_name="Augmentin 625 mg"),
            enriched_seed=DiscoverySeed(product_name="Augmentin 625 mg", nafdac_number="04-1928"),
            sources=[
                DiscoveredSource(
                    url="https://admin.greenbook.nafdac.gov.ng/smpc/aug.pdf",
                    canonical_url="https://admin.greenbook.nafdac.gov.ng/smpc/aug.pdf",
                    domain="admin.greenbook.nafdac.gov.ng",
                    trust_tier=1,
                    trust_label="regulatory",
                    angles=["greenbook_smpc"],
                    title="Augmentin SmPC",
                    content="Header\n" + ("x" * 5000) + "\n6.3 Shelf life\n3 years\n6.4 Special precautions for storage\nStore below 25°C.",
                    stage="pdf",
                    is_smpc_pdf=True,
                ),
                DiscoveredSource(
                    url="https://healthplusnigeria.com/products/augmentin-625",
                    canonical_url="https://healthplusnigeria.com/products/augmentin-625",
                    domain="healthplusnigeria.com",
                    trust_tier=2,
                    trust_label="vetted_pharma",
                    angles=["pharma_reference"],
                    title="Augmentin 625mg",
                    content="Augmentin 625mg",
                    stage="static",
                    identifiers={"gtins": ["5012345678900"]},
                ),
                DiscoveredSource(
                    url="https://nafdac.gov.ng/alert-42",
                    canonical_url="https://nafdac.gov.ng/alert-42",
                    domain="nafdac.gov.ng",
                    trust_tier=1,
                    trust_label="regulatory",
                    angles=["regulatory_alerts"],
                    title="NAFDAC Alert 42",
                    content="NAFDAC Public Alert 42: Falsified Augmentin 625mg Batch 562626.",
                    stage="static",
                ),
            ],
        )
        dossier_resp = ExtractedDossierResponse(
            brand_name="Augmentin 625 mg",
            nafdac_number="04-1928",
            storage_statement="Store below 25°C.",
            expected_security_features=[
                SecurityFeatureSpec(
                    feature_type="tablet_debossing",
                    description="Debossed with AC on one side",
                    required=True,
                    verifiable=False,
                )
            ],
            known_counterfeit_tells=[
                CounterfeitTell(
                    tell_type="compromised_batch",
                    summary="Falsified Augmentin 625mg Batch 562626",
                    affected_batches=["562626"],
                    source_url="https://nafdac.gov.ng/alert-42",
                    source_kind="independent",  # should be normalized to nafdac_derived!
                ),
                CounterfeitTell(
                    tell_type="spelling_error",
                    summary="WHO alert noted misspelled manufacturer line",
                    source_url="https://who.int/news/item/alert-99",
                    source_kind="independent",
                ),
            ],
        )
        provider = MockLLMProvider(dossier_resp, BatchImageVerificationResponse())
        dossier = synthesize_dossier(bundle, provider=provider, verify_visuals=False)

        self.assertEqual(dossier.gtins, ["5012345678900"])
        self.assertEqual(dossier.shelf_life_months, 36)  # parsed deterministically from SmPC fallback!
        self.assertEqual(dossier.storage_statement, "Store below 25°C.")
        self.assertEqual(dossier.reference_level, "C")
        self.assertEqual(len(dossier.expected_security_features), 1)
        self.assertEqual(dossier.known_counterfeit_tells[0].source_kind, "nafdac_derived")
        self.assertEqual(dossier.known_counterfeit_tells[1].source_kind, "independent")

    def test_collect_candidate_images_drops_counterfeit_news_and_alert_sources(self) -> None:
        bundle = DiscoveryBundle(
            seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
            enriched_seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
            sources=[
                DiscoveredSource(
                    url="https://nafdac.gov.ng/alerts/coartem-recall",
                    canonical_url="https://nafdac.gov.ng/alerts/coartem-recall",
                    domain="nafdac.gov.ng",
                    trust_tier=1,
                    trust_label="regulatory",
                    angles=["regulatory_alerts"],
                    title="Safety Alert",
                    content="Alert notice",
                    stage="static",
                    images=[{"url": "https://nafdac.gov.ng/seized-pack.jpg", "source": "img"}],
                ),
                DiscoveredSource(
                    url="https://medplusnigeria.com/products/coartem-20-120",
                    canonical_url="https://medplusnigeria.com/products/coartem-20-120",
                    domain="medplusnigeria.com",
                    trust_tier=2,
                    trust_label="vetted_pharma",
                    angles=["pharma_reference"],
                    title="Coartem 20/120",
                    content="Coartem 20/120 Tablets",
                    stage="static",
                    images=[{"url": "https://medplusnigeria.com/coartem-front.jpg", "source": "jsonld"}],
                ),
            ],
            image_candidates=[
                {
                    "url": "https://realnewsmagazine.net/wp-content/uploads/2026/09/IMG-20260924-WA0048.jpg",
                    "source_page_url": "https://realnewsmagazine.net/pharmaceutical-firm-2-arraigned-over-counterfeit-coartem-tablets-nafdac/",
                    "source_trust_tier": 3,
                    "source": "image_search",
                    "title": "Pharmaceutical firm arraigned over counterfeit Coartem",
                },
                {
                    "url": "https://gomed.ng/assets/coartem-24.webp",
                    "source_page_url": "https://gomed.ng/product/coartem-20-120-24",
                    "source_trust_tier": 3,
                    "source": "image_search",
                    "title": "Coartem 20/120 x24 Tablets",
                },
            ],
        )
        cands = collect_candidate_image_urls(bundle)
        self.assertEqual(
            [c["url"] for c in cands],
            [
                "https://medplusnigeria.com/coartem-front.jpg",
                "https://gomed.ng/assets/coartem-24.webp",
            ],
        )

    def test_deterministic_gates_reject_other_view_type_and_bulk_dispenser_pack(self) -> None:
        bundle = DiscoveryBundle(
            seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
            enriched_seed=DiscoverySeed(
                product_name="Coartem 20/120 Tablets",
                manufacturer="Novartis Nigeria Limited",
                nafdac_number="04-3275",
            ),
            greenbook_matches=[
                {
                    "product_id": 8114,
                    "product_name": "Coartem 20/120 Tablets",
                    "nafdac_number": "04-3275",
                    "form_name": "Tablet",
                    "pack_size": "3 x 6's; 4 x 6's",
                    "applicant_name": "Novartis Nigeria Limited",
                    "detail_url": "https://greenbook.nafdac.gov.ng/products/details/8114",
                }
            ],
            image_candidates=[
                {
                    "url": "https://gomed.ng/coartem-floor.jpg",
                    "source_page_url": "https://gomed.ng/coartem",
                    "source_trust_tier": 2,
                    "source": "image_search",
                },
                {
                    "url": "https://gomed.ng/coartem-hospital-box.jpg",
                    "source_page_url": "https://gomed.ng/coartem-bulk",
                    "source_trust_tier": 2,
                    "source": "image_search",
                },
                {
                    "url": "https://gomed.ng/coartem-retail-24.jpg",
                    "source_page_url": "https://gomed.ng/coartem-24",
                    "source_trust_tier": 2,
                    "source": "image_search",
                },
            ],
        )
        payloads = {
            "https://gomed.ng/coartem-floor.jpg": (_make_pattern_image((420, 420), variant="box_a"), "image/jpeg"),
            "https://gomed.ng/coartem-hospital-box.jpg": (_make_pattern_image((440, 440), variant="box_b"), "image/jpeg"),
            "https://gomed.ng/coartem-retail-24.jpg": (_make_pattern_image((460, 460), variant="other"), "image/jpeg"),
        }
        provider = MockLLMProvider(
            dossier_response=ExtractedDossierResponse(brand_name="Coartem 20/120 Tablets"),
            image_response=BatchImageVerificationResponse(
                results=[
                    RawImageCheck(
                        candidate_index=0,
                        is_product_packaging=True,
                        matches_target_product=True,
                        detected_formulation="tablet",
                        detected_pack_count=24,
                        view_type="other",
                        quality_ok=True,
                    ),
                    RawImageCheck(
                        candidate_index=1,
                        is_product_packaging=True,
                        matches_target_product=True,
                        detected_formulation="tablet",
                        detected_pack_count=24,
                        visible_text_snippets=["Coartem 20/120", "24 tablets/30 blister strips"],
                        view_type="front_box",
                        quality_ok=True,
                    ),
                    RawImageCheck(
                        candidate_index=2,
                        is_product_packaging=True,
                        matches_target_product=True,
                        is_real_photo=True,
                        detected_formulation="tablet",
                        detected_pack_count=24,
                        pack_size_variant="24 tablets",
                        packaging_edition_id="edition_1",
                        edition_summary="Coartem 20/120 24 tablets retail pack",
                        visible_text_snippets=["Coartem 20 mg/120 mg", "24 tablets"],
                        view_type="front_box",
                        quality_ok=True,
                    ),
                ]
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            dossier = synthesize_dossier(
                bundle,
                provider=provider,
                storage=LocalImageStorage(tmp),
                image_downloader=lambda u: payloads[u],
            )
            reasons = {r["url"]: r["reason"] for r in dossier.rejected_images}
            self.assertEqual(reasons["https://gomed.ng/coartem-floor.jpg"], "unusable_view_type")
            self.assertEqual(reasons["https://gomed.ng/coartem-hospital-box.jpg"], "bulk_dispenser_pack")
            self.assertEqual(len(dossier.reference_images), 1)
            self.assertEqual(dossier.reference_images[0].source_url, "https://gomed.ng/coartem-retail-24.jpg")


if __name__ == "__main__":
    unittest.main()
