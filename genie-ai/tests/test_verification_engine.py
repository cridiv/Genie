"""Offline unit tests for Phase D: Multi-Signal Verification Engine & Graceful Degradation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from registry.greenbook import GreenbookStore
from verification import (
    MockCVAdapter,
    ScanInput,
    VerificationEngine,
    VisualAnomaly,
    VisualMatchInput,
    to_ml_infra_verdict,
)


def _augmentin_dossier(*, approved_views=("front_box", "back_box")) -> dict:
    images = [
        {
            "image_id": f"img_{idx}",
            "storage_path": f"images/img_{idx}.jpg",
            "view_type": view,
            "status": "approved",
        }
        for idx, view in enumerate(approved_views)
    ]
    versions = []
    if images:
        versions.append(
            {
                "edition_id": "edition_ng_current",
                "pack_size_variant": "14 tablets",
                "summary": "Orange GSK logo + NAFDAC 04-1928",
                "is_primary": True,
                "status": "approved",
                "images": images,
            }
        )
        versions.append(
            {
                "edition_id": "edition_legacy",
                "pack_size_variant": "14 tablets",
                "summary": "Legacy black GSK logo",
                "is_primary": False,
                "status": "approved",
                "images": [
                    {
                        "image_id": "img_legacy",
                        "storage_path": "images/legacy.webp",
                        "view_type": "front_box",
                        "status": "approved",
                    }
                ],
            }
        )
    return {
        "brand_name": "Augmentin 625 mg",
        "generic_name": "Amoxicillin and Potassium Clavulanate",
        "strength": "500 mg; 125 mg",
        "dosage_form": "Tablet",
        "pack_size": "2 x 7's",
        "manufacturer": "GlaxoSmithKline Consumer Nigeria PLC (GSK)",
        "nafdac_number": "04-1928",
        "registration_status": "Active",
        "gtins": ["5012345678900"],
        "shelf_life_months": 24,
        "storage_statement": "Do not store above 25°C",
        "expected_security_features": [
            {
                "feature_type": "scratch_pin",
                "description": "Sproxil MAS scratch PIN sticker",
                "required": True,
                "verifiable": True,
            },
            {
                "feature_type": "tablet_debossing",
                "description": "Debossed AC on one side",
                "required": False,
                "verifiable": False,
            },
        ],
        "known_counterfeit_tells": [
            {
                "tell_type": "compromised_batch",
                "summary": "Falsified Augmentin 625mg Batch 562626",
                "affected_batches": ["562626"],
                "alert_ref": "NAFDAC Public Alert No. 42",
                "source_url": "https://nafdac.gov.ng/alert-42",
                "source_kind": "nafdac_derived",
            }
        ],
        "recall_alerts": [
            "Public Alert No: 42 – Suspected Falsified Augmentin 625mg Batch No. 562626"
        ],
        "packaging_versions": versions,
    }


def _coartem_level_c_dossier() -> dict:
    return {
        "brand_name": "Coartem 20/120 Tablets",
        "generic_name": "Artemether; Lumefantrine",
        "strength": "20 mg; 120 mg",
        "dosage_form": "Tablet",
        "pack_size": "3 x 6's; 4 x 6's",
        "manufacturer": "Novartis Nigeria Limited",
        "nafdac_number": "04-3275",
        "registration_status": "Ongoing Renewal",
        "gtins": [],
        "shelf_life_months": 24,
        "expected_security_features": [],
        "known_counterfeit_tells": [],
        "recall_alerts": [],
        "packaging_versions": [
            {
                "edition_id": "edition_1",
                "status": "staging",  # staging images MUST NOT count toward Level A/B!
                "images": [
                    {
                        "image_id": "staged_1",
                        "view_type": "front_box",
                        "status": "staging",
                    }
                ],
            }
        ],
    }


class TestVerificationEngine(unittest.TestCase):
    def test_genuine_level_a_and_level_b_scans_reach_authentic(self) -> None:
        # Level A (front + back approved)
        engine_a = VerificationEngine(
            dossiers=[_augmentin_dossier(approved_views=("front_box", "back_box"))],
            greenbook=None,
            cv_adapter=MockCVAdapter(),
        )
        res_a = engine_a.verify(
            ScanInput(
                product_name_hint="Augmentin 625 mg",
                nafdac_number="04-1928",
                ocr_text="Augmentin 625 mg GSK 2 x 7 tablets NAFDAC 04-1928",
                mfg_date="2025-06",
                expiry_date="2027-06",
                scan_date="2026-11-24",
            )
        )
        self.assertEqual(res_a.reference_level, "A")
        self.assertEqual(res_a.verdict, "authentic")
        self.assertEqual(res_a.ml_infra_verdict, "Consistent with genuine")
        self.assertGreaterEqual(res_a.coverage, 0.80)

        # Level B (single front_box approved, no GTIN/security features in dossier -> still reaches authentic!)
        dos_b = _augmentin_dossier(approved_views=("front_box",))
        dos_b["gtins"] = []
        dos_b["expected_security_features"] = []
        engine_b = VerificationEngine(dossiers=[dos_b], greenbook=None, cv_adapter=MockCVAdapter())
        res_b = engine_b.verify(
            ScanInput(
                nafdac_number="04-1928",
                ocr_text="Augmentin 625 mg GSK",
                mfg_date="2025-06",
                expiry_date="2027-06",
                scan_date="2026-11-24",
            )
        )
        self.assertEqual(res_b.reference_level, "B")
        self.assertEqual(res_b.verdict, "authentic")
        self.assertGreaterEqual(res_b.coverage, 0.65)
        self.assertTrue(any("Single-angle" in lim for lim in res_b.limitations))

    def test_historical_valid_edition_recognized_without_false_alarm(self) -> None:
        engine = VerificationEngine(
            dossiers=[_augmentin_dossier(approved_views=("front_box", "back_box"))],
            greenbook=None,
        )
        res = engine.verify(
            ScanInput(
                nafdac_number="04-1928",
                ocr_text="Augmentin 625 mg GSK",
                mfg_date="2025-01",
                expiry_date="2027-01",
                scan_date="2026-11-24",
                visual_match=VisualMatchInput(
                    matched_edition_id="edition_legacy",
                    is_historical_version=True,
                    similarity_score=0.91,
                ),
            )
        )
        self.assertEqual(res.verdict, "authentic")
        self.assertTrue(res.matched_version["is_historical_version"])
        self.assertEqual(res.matched_version["edition_id"], "edition_legacy")

    def test_level_c_ongoing_renewal_caps_at_registered_unverified_not_penalized(self) -> None:
        engine = VerificationEngine(dossiers=[_coartem_level_c_dossier()], greenbook=None)
        res = engine.verify(
            ScanInput(
                nafdac_number="04-3275",
                ocr_text="Coartem 20/120 mg Novartis tablets",
                mfg_date="2025-06",
                expiry_date="2027-06",
                scan_date="2026-11-24",
            )
        )
        self.assertEqual(res.reference_level, "C")
        self.assertEqual(res.verdict, "registered_unverified")
        self.assertEqual(res.ml_infra_verdict, "Cannot verify")
        self.assertTrue(any("not visually compared" in lim for lim in res.limitations))
        nafdac_sig = next(s for s in res.signals if s.name == "nafdac")
        self.assertEqual(nafdac_sig.direction, "positive")
        self.assertIsNone(nafdac_sig.hard_negative)

    def test_gtin_and_observed_sticker_alone_never_unlock_likely_authentic(self) -> None:
        dos = _augmentin_dossier(approved_views=())  # Level C (no approved photos)
        engine = VerificationEngine(dossiers=[dos], greenbook=None)
        res = engine.verify(
            ScanInput(
                nafdac_number="04-1928",
                gtin="5012345678900",
                ocr_text="Augmentin 625 mg GSK",
                observed_security_features=["scratch_pin"],  # merely seen, NOT externally verified
                mfg_date="2025-06",
                expiry_date="2027-06",
                scan_date="2026-11-24",
            )
        )
        self.assertEqual(res.reference_level, "C")
        self.assertEqual(res.verdict, "registered_unverified")

    def test_externally_verified_security_feature_unlocks_likely_authentic_at_level_c(self) -> None:
        dos = _augmentin_dossier(approved_views=())  # Level C
        engine = VerificationEngine(dossiers=[dos], greenbook=None)
        res = engine.verify(
            ScanInput(
                nafdac_number="04-1928",
                ocr_text="Augmentin 625 mg GSK",
                verified_features=["scratch_pin"],  # externally validated PIN!
                mfg_date="2025-06",
                expiry_date="2027-06",
                scan_date="2026-11-24",
            )
        )
        self.assertEqual(res.reference_level, "C")
        self.assertEqual(res.verdict, "likely_authentic")
        self.assertEqual(res.ml_infra_verdict, "Consistent with genuine")

    def test_not_observed_is_not_absent_but_explicitly_checked_missing_is_suspicious(self) -> None:
        dos = _augmentin_dossier(approved_views=())
        engine = VerificationEngine(dossiers=[dos], greenbook=None)

        # Not checked -> unavailable, NOT suspicious
        res_unchecked = engine.verify(
            ScanInput(
                nafdac_number="04-1928",
                ocr_text="Augmentin 625 mg GSK",
                mfg_date="2025-06",
                expiry_date="2027-06",
                scan_date="2026-11-24",
            )
        )
        sec_sig = next(s for s in res_unchecked.signals if s.name == "security_features")
        self.assertEqual(sec_sig.status, "unavailable")
        self.assertIsNone(sec_sig.hard_negative)
        self.assertEqual(res_unchecked.verdict, "registered_unverified")

        # Explicitly checked and still absent -> suspicious!
        res_missing = engine.verify(
            ScanInput(
                nafdac_number="04-1928",
                ocr_text="Augmentin 625 mg GSK",
                features_checked=["scratch_pin"],
                observed_security_features=[],
                scan_date="2026-11-24",
            )
        )
        self.assertEqual(res_missing.verdict, "suspicious")

    def test_hard_negatives_fire_at_any_coverage_recalls_gtin_status_shelf_life_and_ocr(self) -> None:
        dos = _augmentin_dossier(approved_views=())
        engine = VerificationEngine(dossiers=[dos, _coartem_level_c_dossier()], greenbook=None)

        # 1. Compromised batch at Level C -> likely_counterfeit
        res_batch = engine.verify(
            ScanInput(nafdac_number="04-1928", batch_number="562626")
        )
        self.assertEqual(res_batch.verdict, "likely_counterfeit")
        self.assertEqual(len(res_batch.counterfeit_tell_hits), 1)
        self.assertEqual(res_batch.counterfeit_tell_hits[0].source_kind, "nafdac_derived")

        # 2. Invalid GTIN check digit -> likely_counterfeit
        res_bad_gtin = engine.verify(
            ScanInput(nafdac_number="04-1928", gtin="5012345678909")
        )
        self.assertEqual(res_bad_gtin.verdict, "likely_counterfeit")

        # 3. GTIN belonging to Augmentin scanned on Coartem -> likely_counterfeit
        res_wrong_gtin = engine.verify(
            ScanInput(nafdac_number="04-3275", gtin="5012345678900")
        )
        self.assertEqual(res_wrong_gtin.verdict, "likely_counterfeit")

        # 4. Impossible SmPC shelf-life gap (60 months vs 24 months SmPC) -> suspicious
        res_shelf = engine.verify(
            ScanInput(
                nafdac_number="04-1928",
                mfg_date="2025-01",
                expiry_date="2030-01",
                scan_date="2026-11-24",
            )
        )
        self.assertEqual(res_shelf.verdict, "suspicious")

        # 5. OCR confidence gate: low confidence mismatch != hard negative; high confidence mismatch -> suspicious
        res_low_ocr = engine.verify(
            ScanInput(
                nafdac_number="04-3275",
                ocr_text="Coartem 80/480 mg tablets",
                ocr_confidence=0.60,
            )
        )
        spec_low = next(s for s in res_low_ocr.signals if s.name == "spec_ocr")
        self.assertIsNone(spec_low.hard_negative)

        res_high_ocr = engine.verify(
            ScanInput(
                nafdac_number="04-3275",
                ocr_text="Coartem 80/480 mg tablets",
                ocr_confidence=0.92,
            )
        )
        self.assertEqual(res_high_ocr.verdict, "suspicious")

        # 6. Severe visual anomaly -> suspicious
        engine_vis = VerificationEngine(
            dossiers=[_augmentin_dossier(approved_views=("front_box", "back_box"))],
            greenbook=None,
        )
        res_anom = engine_vis.verify(
            ScanInput(
                nafdac_number="04-1928",
                visual_match=VisualMatchInput(
                    similarity_score=0.32,
                    anomalies=[VisualAnomaly(region="logo", description="Misaligned GSK print", severity="high")],
                ),
            )
        )
        self.assertEqual(res_anom.verdict, "suspicious")

    def test_expired_vs_revoked_status_and_unregistered_product(self) -> None:
        dos_expired = _coartem_level_c_dossier()
        dos_expired["registration_status"] = "Expired"
        res_exp = VerificationEngine(dossiers=[dos_expired], greenbook=None).verify(
            ScanInput(nafdac_number="04-3275")
        )
        self.assertEqual(res_exp.verdict, "suspicious")

        dos_revoked = _coartem_level_c_dossier()
        dos_revoked["registration_status"] = "Revoked"
        res_rev = VerificationEngine(dossiers=[dos_revoked], greenbook=None).verify(
            ScanInput(nafdac_number="04-3275")
        )
        self.assertEqual(res_rev.verdict, "likely_counterfeit")

        # Unregistered drug not in Greenbook at all
        with tempfile.TemporaryDirectory() as tmp:
            gb = GreenbookStore(Path(tmp) / "gb.db")
            gb.init_schema()
            res_unreg = VerificationEngine(dossiers=[], greenbook=gb).verify(
                ScanInput(product_name_hint="FakeMalariaX 500mg", nafdac_number="Z9-9999")
            )
            self.assertTrue(res_unreg.unregistered_product)
            self.assertEqual(res_unreg.verdict, "suspicious")
            self.assertTrue(res_unreg.recommend_discovery)

    def test_ml_infra_verdict_mapping(self) -> None:
        self.assertEqual(to_ml_infra_verdict("authentic"), "Consistent with genuine")
        self.assertEqual(to_ml_infra_verdict("likely_authentic"), "Consistent with genuine")
        self.assertEqual(to_ml_infra_verdict("suspicious"), "Suspicious")
        self.assertEqual(to_ml_infra_verdict("likely_counterfeit"), "Suspicious")
        self.assertEqual(to_ml_infra_verdict("registered_unverified"), "Cannot verify")
        self.assertEqual(to_ml_infra_verdict("unknown"), "Cannot verify")


if __name__ == "__main__":
    unittest.main()
