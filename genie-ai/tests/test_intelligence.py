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
    EvidenceClaim,
    ExtractedDossierResponse,
    GeminiProvider,
    LocalImageStorage,
    NvidiaProvider,
    RawImageCheck,
    collect_candidate_image_urls,
    compute_dhash,
    download_and_deduplicate_images,
    get_default_provider,
    hamming_distance,
    parse_allowed_pack_counts,
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
