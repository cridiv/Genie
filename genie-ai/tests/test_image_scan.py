"""Tests for Vision-LLM live image verification (`verification/image_scan.py`)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator import GenieOrchestrator
from verification.image_scan import (
    ExtractedImageScan,
    VisualComparisonOutput,
    infer_mime_type,
    verify_image_bytes,
)


class _StubVisionLLM:
    def __init__(self, extracted: ExtractedImageScan, comparison: VisualComparisonOutput) -> None:
        self._extracted = extracted
        self._comparison = comparison
        self.calls = []

    @property
    def model_name(self) -> str:
        return "stub-vision-v1"

    def generate_structured(self, prompt, schema, *, system_instruction=None):
        raise NotImplementedError

    def generate_structured_with_images(self, prompt, images, schema, *, system_instruction=None):
        self.calls.append((schema.__name__, len(images)))
        if schema is ExtractedImageScan:
            return self._extracted
        if schema is VisualComparisonOutput:
            return self._comparison
        raise AssertionError(f"Unexpected schema: {schema}")


class TestImageScan(unittest.TestCase):
    def test_infer_mime_type(self) -> None:
        self.assertEqual(infer_mime_type("pack.jpg"), "image/jpeg")
        self.assertEqual(infer_mime_type("pack.PNG"), "image/png")
        self.assertEqual(infer_mime_type("pack.webp"), "image/webp")
        self.assertEqual(infer_mime_type("upload", "image/jpg"), "image/jpeg")
        with self.assertRaises(ValueError):
            infer_mime_type("document.pdf", "application/pdf")

    def test_verify_image_bytes_runs_ocr_and_visual_reference_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod_dir = root / "products" / "augmentin_625_mg"
            img_dir = prod_dir / "images"
            img_dir.mkdir(parents=True)
            ref_file = img_dir / "front.jpg"
            ref_file.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-ref")

            dossier = {
                "brand_name": "Augmentin 625 mg",
                "nafdac_number": "04-1927",
                "manufacturer": "GlaxoSmithKline",
                "registration_status": "Active",
                "active_ingredients": ["Amoxicillin", "Clavulanic acid"],
                "strength": "625 mg",
                "dosage_form": "Tablets",
                "shelf_life_months": 24,
                "reference_level": "B",
                "dossier_status": "approved",
                "packaging_versions": [
                    {
                        "edition_id": "edition_1",
                        "is_primary": True,
                        "status": "approved",
                        "images": [
                            {
                                "image_id": "front1",
                                "storage_path": "images/front.jpg",
                                "mime_type": "image/jpeg",
                                "view_type": "front_box",
                                "status": "approved",
                            }
                        ],
                    }
                ],
                "known_counterfeit_tells": [],
                "recalls": [],
            }
            (prod_dir / "product.json").write_text(json.dumps(dossier), encoding="utf-8")

            orch = GenieOrchestrator(
                products_dir=root / "products",
                genie_db_path=root / "genie.db",
                load_default_greenbook=False,
            )
            try:
                llm = _StubVisionLLM(
                    extracted=ExtractedImageScan(
                        product_name_hint="Augmentin 625 mg",
                        nafdac_number="04-1927",
                        batch_number="A9921X",
                        mfg_date="01/2025",
                        expiry_date="01/2027",
                        ocr_text="Augmentin 625 mg Amoxicillin Clavulanic acid GlaxoSmithKline",
                        ocr_confidence=0.95,
                        angle="front_box",
                    ),
                    comparison=VisualComparisonOutput(
                        similarity_score=0.93,
                        is_same_product_packaging=True,
                        anomalies=[],
                        summary="Matches approved Augmentin 625 mg front box.",
                    ),
                )
                resp = verify_image_bytes(
                    b"\xff\xd8\xff\xe0fake-scan-bytes",
                    "image/jpeg",
                    orchestrator=orch,
                    llm=llm,
                    compare_visual=True,
                    auto_discover=False,
                    scan_date="2026-06-01",
                )
                self.assertTrue(resp.visual_comparison_used)
                self.assertEqual(resp.reference_images_compared, ["images/front.jpg"])
                self.assertEqual(resp.vision_model, "stub-vision-v1")
                self.assertEqual(llm.calls, [("ExtractedImageScan", 1), ("VisualComparisonOutput", 2)])
                self.assertEqual(resp.verification.result.verdict, "authentic")
                self.assertEqual(resp.verification.result.ml_infra_verdict, "Consistent with genuine")
            finally:
                orch.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
