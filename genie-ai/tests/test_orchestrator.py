"""Offline unit tests for the Concurrent Orchestrator, SQLite Job Queue, and FastAPI layer."""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from discovery.models import DiscoverySeed
from orchestrator import GenieOrchestrator, JobStore
from registry.greenbook import GreenbookStore
from verification import MockCVAdapter, ScanInput


class TestOrchestratorAndJobs(unittest.TestCase):
    def test_job_store_deduplicates_concurrent_submissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "genie.db")
            seed = DiscoverySeed(product_name="Kesartem 80/480mg Tablets", nafdac_number="C4-0143")

            def _submit(_i: int):
                return store.enqueue_or_get_active(seed)

            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(_submit, range(12)))

            job_ids = {job["job_id"] for job, _dedup in results}
            dedup_flags = [dedup for _job, dedup in results]
            self.assertEqual(len(job_ids), 1)
            self.assertEqual(dedup_flags.count(False), 1)
            self.assertEqual(dedup_flags.count(True), 11)

    def test_orchestrator_verifies_fast_and_runs_async_discovery_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gb = GreenbookStore(tmp_path / "gb.db")
            gb.init_schema()
            gb.upsert_rows(
                [
                    {
                        "product_id": 101,
                        "nafdac_number": "C4-0143",
                        "product_name": "Kesartem Tablets",
                        "raw_product_name": "Kesartem Tablets",
                        "ingredient_name": "Artemether; Lumefantrine",
                        "ingredient_synonym": "",
                        "category_name": "Drugs",
                        "form_name": "Tablet",
                        "route_name": "Oral",
                        "strength": "80 mg; 480 mg",
                        "applicant_name": "Kessington Global Synergy Ltd",
                        "approval_date": "",
                        "expiry_date": "",
                        "status": "Active",
                        "product_description": "",
                        "pack_size": "1 x 6's",
                        "composition": "",
                        "smpc_url": "",
                        "atc_code": "",
                        "detail_url": "https://greenbook.nafdac.gov.ng/products/details/101",
                        "updated_at": "",
                        "synced_at": "2026-11-24T00:00:00Z",
                    }
                ]
            )

            release_worker = threading.Event()
            worker_calls = []

            def fake_discovery(seed: DiscoverySeed) -> dict:
                worker_calls.append(seed.to_dict())
                release_worker.wait(timeout=2.0)
                return {"slug": "kesartem_tablets", "dossier_status": "approved", "reference_level": "C"}

            orch = GenieOrchestrator(
                products_dir=tmp_path / "products",
                genie_db_path=tmp_path / "genie.db",
                greenbook=gb,
                load_default_greenbook=False,
                discovery_worker_fn=fake_discovery,
            )
            try:
                # 1. Greenbook-only product verifies IMMEDIATELY (does not block on fake_discovery!)
                t0 = time.perf_counter()
                resp1 = orch.verify_scan(
                    ScanInput(
                        nafdac_number="C4-0143",
                        ocr_text="Kesartem 80/480 mg Tablets Kessington",
                        mfg_date="2026-01",
                        expiry_date="2028-01",
                        scan_date="2026-11-24",
                    )
                )
                elapsed = time.perf_counter() - t0
                self.assertLess(elapsed, 0.5)
                self.assertEqual(resp1.result.verdict, "registered_unverified")
                self.assertIsNotNone(resp1.discovery_job_id)
                self.assertFalse(resp1.discovery_deduplicated)

                # 2. Second scan of same product while job is active deduplicates to SAME job_id
                resp2 = orch.verify_scan(ScanInput(nafdac_number="C4-0143"))
                self.assertEqual(resp2.discovery_job_id, resp1.discovery_job_id)
                self.assertTrue(resp2.discovery_deduplicated)

                # 3. Release background worker and verify completion recorded in SQLite
                release_worker.set()
                final_job = orch.job_runner.wait_for(resp1.discovery_job_id, timeout=3.0)
                self.assertEqual(final_job["status"], "completed")
                self.assertEqual(final_job["result"]["slug"], "kesartem_tablets")
                self.assertEqual(len(worker_calls), 1)
            finally:
                orch.shutdown(wait=True)

    def test_orchestrator_runs_cv_adapter_for_approved_dossier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dossier = {
                "_slug": "augmentin_625_mg",
                "brand_name": "Augmentin 625 mg",
                "strength": "500 mg; 125 mg",
                "dosage_form": "Tablet",
                "manufacturer": "GlaxoSmithKline Consumer Nigeria PLC (GSK)",
                "nafdac_number": "04-1928",
                "registration_status": "Active",
                "shelf_life_months": 24,
                "packaging_versions": [
                    {
                        "edition_id": "edition_1",
                        "is_primary": True,
                        "status": "approved",
                        "images": [
                            {"image_id": "a", "view_type": "front_box", "status": "approved"},
                            {"image_id": "b", "view_type": "back_box", "status": "approved"},
                        ],
                    }
                ],
            }
            orch = GenieOrchestrator(
                products_dir=tmp_path / "products",
                genie_db_path=tmp_path / "genie.db",
                greenbook=None,
                load_default_greenbook=False,
                dossiers=[dossier],
                cv_adapter=MockCVAdapter(),
            )
            try:
                resp = orch.verify_scan(
                    ScanInput(
                        nafdac_number="04-1928",
                        ocr_text="Augmentin 625 mg GSK",
                        mfg_date="2025-06",
                        expiry_date="2027-06",
                        scan_date="2026-11-24",
                    )
                )
                self.assertEqual(resp.result.verdict, "authentic")
                self.assertEqual(resp.result.reference_level, "A")
                self.assertIsNone(resp.discovery_job_id)
                health = orch.health()
                self.assertEqual(health["status"], "ok")
                self.assertEqual(health["cached_products"], 1)
            finally:
                orch.shutdown(wait=True)

    def test_fastapi_endpoints_when_fastapi_installed(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: PLC0415
            from api.main import create_app  # noqa: PLC0415
        except ImportError:
            self.skipTest("fastapi not installed in current venv")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            orch = GenieOrchestrator(
                products_dir=tmp_path / "products",
                genie_db_path=tmp_path / "genie.db",
                greenbook=None,
                load_default_greenbook=False,
                dossiers=[],
                discovery_worker_fn=lambda s: {"slug": "test", "brand_name": s.product_name},
            )
            try:
                client = TestClient(create_app(orch))
                r_health = client.get("/v1/health")
                self.assertEqual(r_health.status_code, 200)
                self.assertEqual(r_health.json()["status"], "ok")

                r_verify = client.post(
                    "/v1/verify",
                    json={"product_name_hint": "UnknownDrugX", "nafdac_number": "Z9-9999"},
                )
                self.assertEqual(r_verify.status_code, 200)
                body = r_verify.json()
                self.assertEqual(body["result"]["verdict"], "suspicious")
                self.assertTrue(body["result"]["unregistered_product"])
                self.assertIsNotNone(body["discovery_job_id"])

                job_id = body["discovery_job_id"]
                orch.job_runner.wait_for(job_id, timeout=3.0)
                r_job = client.get(f"/v1/jobs/{job_id}")
                self.assertEqual(r_job.status_code, 200)
                self.assertEqual(r_job.json()["status"], "completed")
            finally:
                orch.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
