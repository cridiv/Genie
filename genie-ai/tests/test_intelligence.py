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
    RawImageCheck,
    collect_candidate_image_urls,
    compute_dhash,
    download_and_deduplicate_images,
    hamming_distance,
    synthesize_dossier,
    verify_images,
)


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
            im.resize((320, 320), Image.Resampling.LANCZOS).save(buf, format="JPEG", quality=80)
            box_a_resized = buf.getvalue()
        box_b = _make_pattern_image((400, 400), variant="box_b", fmt="PNG")
        tiny = _make_pattern_image((120, 120), variant="box_a", fmt="JPEG")
        banner = _make_pattern_image((1200, 300), variant="box_b", fmt="JPEG")

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
            verified, rejected = verify_images(
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

    def test_gemini_provider_requires_key_and_respects_model_env(self) -> None:
        with mock.patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-pro"}, clear=True):
            provider = GeminiProvider()
            self.assertEqual(provider.model_name, "gemini-2.5-pro")
            with self.assertRaises(ValueError):
                provider.generate_structured("hello", ExtractedDossierResponse)


if __name__ == "__main__":
    unittest.main()
