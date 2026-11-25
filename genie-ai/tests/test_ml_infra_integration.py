"""Integration tests for the `ml_infra` <-> GENIE AI bridge."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator import GenieOrchestrator
from verification.adapters import (
    MLInfraBarcodeInput,
    MLInfraOCRInput,
    MLInfraPackComparisonInput,
    MLInfraVerifyPayload,
    scan_input_from_ml_infra,
    to_ml_infra_response,
)

GENIE_AI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = GENIE_AI_ROOT.parent


class TestMLInfraIntegration(unittest.TestCase):
    def test_authentic_pack_comparator_payload_maps_to_ml_infra_response(self) -> None:
        orch = GenieOrchestrator(
            products_dir=GENIE_AI_ROOT / "data" / "products",
            genie_db_path=GENIE_AI_ROOT / "data" / "genie.db",
            load_default_greenbook=True,
        )
        try:
            payload = MLInfraVerifyPayload(
                ocr=MLInfraOCRInput(
                    nafdac_number="04-1928",
                    batch_number="A9921X",
                    mfg_date="01/2025",
                    expiry_date="01/2027",
                    brand_name="Augmentin 625 mg",
                    raw_text_lines=[
                        "Augmentin 625 mg",
                        "Amoxicillin 500 mg Clavulanic Acid 125 mg",
                        "GlaxoSmithKline Consumer Nigeria PLC",
                    ],
                ),
                pack_comparison=MLInfraPackComparisonInput(
                    overall_similarity_score=0.92,
                    is_counterfeit_suspect=False,
                    alignment_matched=True,
                    inlier_ratio=0.78,
                    color_score=0.94,
                    layout_score=0.91,
                    anomaly_score=0.08,
                ),
                matched_version_label="edition_1",
                scan_date="2026-06-01",
            )
            scan = scan_input_from_ml_infra(payload)
            orch_resp = orch.verify_scan(scan, auto_discover=False)
            ml_resp = to_ml_infra_response(orch_resp, payload=payload)

            self.assertEqual(ml_resp["verdict"], "Consistent with genuine")
            self.assertEqual(ml_resp["genie_ai"]["verdict"], "authentic")
            self.assertEqual(ml_resp["matched_product_name"], "Augmentin 625 mg")
            self.assertGreaterEqual(ml_resp["confidence"], 0.75)
            self.assertIsNotNone(ml_resp["signals"]["visual_similarity_score"])
            self.assertEqual(ml_resp["signals"]["patch_anomaly_score"], 0.08)
            self.assertIsNotNone(ml_resp["signals"]["nafdac_score"])
        finally:
            orch.shutdown(wait=False)

    def test_recalled_batch_from_ml_infra_triggers_suspicious_verdict(self) -> None:
        orch = GenieOrchestrator(
            products_dir=GENIE_AI_ROOT / "data" / "products",
            genie_db_path=GENIE_AI_ROOT / "data" / "genie.db",
            load_default_greenbook=True,
        )
        try:
            payload = MLInfraVerifyPayload(
                ocr=MLInfraOCRInput(
                    nafdac_number="04-1928",
                    batch_number="562626",
                    brand_name="Augmentin 625 mg",
                ),
                barcode=MLInfraBarcodeInput(batch="562626", check_digit_valid=True),
                scan_date="2026-06-01",
            )
            scan = scan_input_from_ml_infra(payload)
            orch_resp = orch.verify_scan(scan, auto_discover=False)
            ml_resp = to_ml_infra_response(orch_resp, payload=payload)

            self.assertEqual(ml_resp["verdict"], "Suspicious")
            self.assertEqual(ml_resp["genie_ai"]["verdict"], "likely_counterfeit")
            self.assertTrue(len(ml_resp["genie_ai"]["counterfeit_tell_hits"]) >= 1)
        finally:
            orch.shutdown(wait=False)

    def test_pack_comparator_counterfeit_suspect_maps_high_severity_anomalies(self) -> None:
        payload = MLInfraVerifyPayload(
            ocr=MLInfraOCRInput(nafdac_number="04-1928", brand_name="Augmentin 625 mg"),
            pack_comparison=MLInfraPackComparisonInput(
                overall_similarity_score=0.41,
                is_counterfeit_suspect=True,
                alignment_matched=False,
                inlier_ratio=0.14,
                anomaly_score=0.82,
                flagged_grid_zones=["top-left", "bottom-right"],
                inconsistencies=["Color delta-E exceeds threshold (18.4 > 10.0)"],
            ),
        )
        scan = scan_input_from_ml_infra(payload)
        self.assertIsNotNone(scan.visual_match)
        self.assertEqual(scan.visual_match.similarity_score, 0.41)
        self.assertTrue(any(a.severity == "high" for a in scan.visual_match.anomalies))

    def test_real_ml_infra_vlm_extraction_json_resolves_against_greenbook(self) -> None:
        sample_path = REPO_ROOT / "ml_infra" / "images" / "extraction_result.json"
        if not sample_path.is_file():
            self.skipTest("ml_infra/images/extraction_result.json not present")

        vlm_data = json.loads(sample_path.read_text(encoding="utf-8"))
        payload = MLInfraVerifyPayload(vlm_extraction=vlm_data, scan_date="2026-06-01")
        scan = scan_input_from_ml_infra(payload)
        self.assertEqual(scan.nafdac_number, "B4-6458")
        self.assertIn("IBUMARTEM", scan.product_name_hint or "")
        self.assertTrue(any("scratch" in f.lower() for f in scan.observed_security_features))

        with tempfile.TemporaryDirectory() as tmp:
            orch = GenieOrchestrator(
                products_dir=GENIE_AI_ROOT / "data" / "products",
                genie_db_path=Path(tmp) / "genie.db",
                load_default_greenbook=True,
            )
            try:
                orch_resp = orch.verify_scan(scan, auto_discover=False)
                ml_resp = to_ml_infra_response(orch_resp, payload=payload)
                self.assertIn(
                    ml_resp["verdict"],
                    ("Cannot verify", "Consistent with genuine", "Suspicious"),
                )
                self.assertTrue(ml_resp["genie_ai"]["recommend_discovery"])
            finally:
                orch.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
