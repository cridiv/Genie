"""Hardening tests: deterministic evidence gate, quarantine of hallucinations, SQLite WAL concurrency, and real-data verification."""
from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from discovery.models import DiscoveredSource, DiscoveryBundle, DiscoverySeed
from intelligence.schemas import (
    CandidateProductDossier,
    CounterfeitTell,
    EvidenceClaim,
)
from registry.greenbook import GreenbookStore, default_db_path
from registry.trusted_sources import TrustedSourceStore
from validation.evidence import validate_dossier_evidence
from verification import ScanInput, VerificationEngine
from verification.signals.batch_expiry import parse_pack_date

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestEvidenceGateAndHardening(unittest.TestCase):
    def _sample_bundle(self) -> DiscoveryBundle:
        return DiscoveryBundle(
            seed=DiscoverySeed(product_name="Augmentin 625 mg"),
            enriched_seed=DiscoverySeed(
                product_name="Augmentin 625 mg",
                manufacturer="GlaxoSmithKline Consumer Nigeria PLC (GSK)",
                nafdac_number="04-1928",
            ),
            greenbook_matches=[
                {
                    "product_id": 5617,
                    "product_name": "Augmentin 625 mg",
                    "nafdac_number": "04-1928",
                    "ingredient_name": "Amoxicillin; Clavulanic Acid",
                    "strength": "500 mg; 125 mg",
                    "form_name": "Tablet",
                    "applicant_name": "GlaxoSmithKline Consumer Nigeria PLC (GSK)",
                    "pack_size": "2 x 7's",
                    "status": "Active",
                    "detail_url": "https://greenbook.nafdac.gov.ng/products/details/5617",
                }
            ],
            sources=[
                DiscoveredSource(
                    url="https://nafdac.gov.ng/alert-42",
                    canonical_url="https://nafdac.gov.ng/alert-42",
                    domain="nafdac.gov.ng",
                    trust_tier=1,
                    trust_label="regulatory",
                    angles=["regulatory_alerts"],
                    title="NAFDAC Alert 42",
                    content="Public Alert No: 42 on suspected falsified Augmentin 625mg Batch No. 562626. Shelf life is 2 years.",
                    stage="static",
                )
            ],
        )

    def test_evidence_gate_approves_clean_tier1_dossier_with_smart_quotes(self) -> None:
        bundle = self._sample_bundle()
        dossier = CandidateProductDossier(
            seed=bundle.seed.to_dict(),
            enriched_seed=bundle.enriched_seed.to_dict(),
            brand_name="Augmentin 625 mg",
            manufacturer="GlaxoSmithKline Consumer Nigeria PLC (GSK)",
            nafdac_number="04-1928",
            shelf_life_months=24,  # grounded by "2 years" in source!
            known_counterfeit_tells=[
                CounterfeitTell(
                    tell_type="compromised_batch",
                    summary="Falsified Batch 562626",
                    affected_batches=["562626"],
                    source_url="https://nafdac.gov.ng/alert-42",
                    source_kind="nafdac_derived",
                )
            ],
            claims=[
                EvidenceClaim(
                    field_name="brand_name",
                    value="Augmentin 625 mg",
                    source_url="https://greenbook.nafdac.gov.ng/products/details/5617",
                    verbatim_quote="Product Name: Augmentin 625 mg",
                ),
                EvidenceClaim(
                    field_name="pack_size",
                    value="2 x 7's",
                    source_url="https://greenbook.nafdac.gov.ng/products/details/5617",
                    verbatim_quote="Pack Size: 2 x 7\u2019s",  # curly apostrophe should still match!
                ),
            ],
            model_used="mock",
        )
        updated, report = validate_dossier_evidence(bundle, dossier, sanitize=True)
        self.assertEqual(report.dossier_status, "approved")
        self.assertEqual(updated.dossier_status, "approved")
        self.assertEqual(report.matched_claims, 2)
        self.assertEqual(report.numeric_failures, [])
        self.assertEqual(updated.shelf_life_months, 24)
        self.assertEqual(updated.known_counterfeit_tells[0].affected_batches, ["562626"])

    def test_evidence_gate_quarantines_hallucinated_batches_gtin_and_shelf_life(self) -> None:
        bundle = self._sample_bundle()
        dossier = CandidateProductDossier(
            seed=bundle.seed.to_dict(),
            enriched_seed=bundle.enriched_seed.to_dict(),
            brand_name="Augmentin 625 mg",
            manufacturer="GlaxoSmithKline Consumer Nigeria PLC (GSK)",
            nafdac_number="04-1928",
            gtins=["5012345678900"],  # hallucinated, not in any source
            shelf_life_months=60,  # hallucinated, source says 2 years (24m)
            known_counterfeit_tells=[
                CounterfeitTell(
                    tell_type="compromised_batch",
                    summary="Hallucinated batch",
                    affected_batches=["FAKE999999"],  # hallucinated batch!
                    source_url="https://nafdac.gov.ng/alert-42",
                )
            ],
            claims=[
                EvidenceClaim(
                    field_name="nafdac_number",
                    value="04-1928",
                    source_url="https://greenbook.nafdac.gov.ng/products/details/5617",
                    verbatim_quote="NAFDAC Number: 04-1928",
                )
            ],
            model_used="mock",
        )
        sanitized, report = validate_dossier_evidence(bundle, dossier, sanitize=True)
        self.assertEqual(report.dossier_status, "staging")
        self.assertEqual(sanitized.gtins, [])
        self.assertIsNone(sanitized.shelf_life_months)
        self.assertEqual(sanitized.known_counterfeit_tells, [])
        self.assertGreaterEqual(len(report.quarantined_items), 3)

    def test_evidence_gate_flags_tier1_conflict_and_blocks_approval(self) -> None:
        bundle = self._sample_bundle()
        dossier = CandidateProductDossier(
            seed=bundle.seed.to_dict(),
            enriched_seed=bundle.enriched_seed.to_dict(),
            brand_name="Augmentin 625 mg",
            manufacturer="Completely Different Pharma Ltd",
            nafdac_number="04-9999",
            claims=[
                EvidenceClaim(
                    field_name="brand_name",
                    value="Augmentin 625 mg",
                    source_url="https://greenbook.nafdac.gov.ng/products/details/5617",
                    verbatim_quote="Augmentin 625 mg",
                )
            ],
            model_used="mock",
        )
        updated, report = validate_dossier_evidence(bundle, dossier, sanitize=True)
        self.assertEqual(updated.dossier_status, "staging")
        self.assertEqual(len(report.tier1_conflicts), 2)

    def test_date_parser_handles_mm_yy_dd_mm_yyyy_and_malformed_safely(self) -> None:
        self.assertEqual(parse_pack_date("06/27", end_of_month=True).isoformat(), "2027-06-30")
        self.assertEqual(parse_pack_date("15/03/2025").isoformat(), "2025-03-15")
        self.assertEqual(parse_pack_date("Apr 2024", end_of_month=True).isoformat(), "2024-04-30")
        self.assertIsNone(parse_pack_date("N/A"))
        self.assertIsNone(parse_pack_date("99/9999"))

    def test_sqlite_wal_concurrent_reads_and_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustedSourceStore(Path(tmp) / "genie.db")
            store.ensure_seeded()

            def _worker(idx: int) -> bool:
                if idx % 4 == 0:
                    store.upsert_source(
                        domain=f"pharm{idx}.ng",
                        name=f"Pharm {idx}",
                        source_type="pharmacy",
                        trust_status="provisional",
                    )
                res = store.is_verified_image_source("https://healthplusnigeria.com/products/coartem")
                return res is not None

            with ThreadPoolExecutor(max_workers=8) as pool:
                outcomes = list(pool.map(_worker, range(32)))
            self.assertTrue(all(outcomes))

    def test_real_local_greenbook_and_saved_dossiers_end_to_end(self) -> None:
        gb_path = default_db_path()
        if not gb_path.is_file():
            self.skipTest("Local data/greenbook.db not present")

        engine = VerificationEngine(products_dir=REPO_ROOT / "data" / "products")

        # 1. Kesartem C4-0143 resolved straight from 9,065-drug Greenbook (Level C, recommends discovery)
        res_kes = engine.verify(
            ScanInput(
                nafdac_number=" c4 - 0143 ",  # messy spacing & lowercase
                ocr_text="Kesartem 80/480 mg Tablets Kessington",
                mfg_date="01/26",
                expiry_date="01/28",
                scan_date="2026-11-24",
            )
        )
        self.assertFalse(res_kes.unregistered_product)
        self.assertTrue(res_kes.recommend_discovery)
        self.assertEqual(res_kes.reference_level, "C")
        self.assertEqual(res_kes.verdict, "registered_unverified")
        self.assertEqual(res_kes.matched_product["nafdac_number"], "C4-0143")

        # 2. Augmentin real saved dossier + compromised batch 562626 -> likely_counterfeit!
        aug_path = REPO_ROOT / "data" / "products" / "augmentin_625_mg" / "product.json"
        if aug_path.is_file():
            res_aug_fake = engine.verify(
                ScanInput(nafdac_number="04-1928", batch_number="562626")
            )
            self.assertEqual(res_aug_fake.verdict, "likely_counterfeit")
            self.assertGreaterEqual(len(res_aug_fake.counterfeit_tell_hits), 1)

        # 3. Concurrent multi-thread verification against real SQLite + JSON dossiers
        def _run_verify(code: str) -> str:
            return engine.verify(
                ScanInput(nafdac_number=code, ocr_text="Tablets", scan_date="2026-11-24")
            ).verdict

        with ThreadPoolExecutor(max_workers=6) as pool:
            verdicts = list(pool.map(_run_verify, ["04-1928", "04-3275", "C4-0143", "Z9-9999"] * 4))
        self.assertEqual(len(verdicts), 16)
        self.assertIn("suspicious", verdicts)  # Z9-9999 unregistered


if __name__ == "__main__":
    unittest.main()
