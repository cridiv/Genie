"""Offline unit tests for the NAFDAC Greenbook SQLite + FTS5 mirror."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from registry.greenbook import GreenbookStore, normalize_row

SAMPLE_RAW_ROWS = [
    {
        "product_id": 2,
        "product_name": "AG Spironolactone##",
        "strength": "25 mg",
        "NAFDAC": "A4-100160",
        "approval_date": "2021-12-17",
        "expiry_date": "2026-12-16",
        "smpc": "https://admin.greenbook.nafdac.gov.ng/uploadImage/smpc_files/spiro.pdf",
        "product_description": "Film Coated Tablet",
        "pack_size": "1 x 500&#039;s (in a jar)",
        "status": "Active",
        "composition": "Each tablet contains: Spironolactone BP 25 mg",
        "atc": "C03DA01",
        "ingredient": {"ingredient_name": "Spironolactone", "synonym": ""},
        "form": {"name": "Tablet"},
        "applicant": {"name": "AnnyGod Pharmaceutical Company Ltd"},
        "route": {"name": "Oral"},
        "product_category": {"name": "Drugs"},
    },
    {
        "product_id": 3,
        "product_name": "Artheget EZ*#",
        "strength": "80 mg; 480 mg",
        "NAFDAC": "A4–6238 ",
        "approval_date": "2021-12-02",
        "expiry_date": "2026-12-01",
        "smpc": "https://admin.greenbook.nafdac.gov.ng/uploadImage/smpc_files/artheget.pdf",
        "product_description": "Yellow colored oblong tablet",
        "pack_size": "2 x 3&#039;s (in Alu-Alu blisters)",
        "status": "Active",
        "composition": "Artemether 80 mg, Lumefantrine 480 mg",
        "atc": "P01BF01",
        "ingredient_name": "Artemether; Lumefantrine",
        "form_name": "Tablet",
        "applicant_name": "Getz Pharma Nigeria Limited",
        "route_name": "Oral",
        "category_name": "Drugs",
    },
    {
        "product_id": 10,
        "product_name": "Augmentin 625mg",
        "strength": "500 mg; 125 mg",
        "NAFDAC": "04-1234",
        "approval_date": "2020-01-10",
        "expiry_date": "2025-01-09",
        "smpc": "not-a-url",
        "product_description": "White oval film-coated tablet",
        "pack_size": "2 x 7&#039;s",
        "status": "Active",
        "composition": "Amoxicillin 500 mg, Clavulanic Acid 125 mg",
        "ingredient_name": "Amoxicillin; Clavulanic Acid",
        "form_name": "Tablet",
        "applicant_name": "GlaxoSmithKline Consumer Nigeria Plc",
        "route_name": "Oral",
        "category_name": "Drugs",
    },
]


class TestGreenbookStore(unittest.TestCase):
    def test_normalize_row_cleans_markers_entities_and_urls(self) -> None:
        row2 = normalize_row(SAMPLE_RAW_ROWS[1])
        self.assertEqual(row2["product_name"], "Artheget EZ")
        self.assertEqual(row2["nafdac_number"], "A4-6238")
        self.assertEqual(row2["pack_size"], "2 x 3's (in Alu-Alu blisters)")
        self.assertEqual(row2["detail_url"], "https://greenbook.nafdac.gov.ng/products/details/3")
        self.assertTrue(row2["smpc_url"].startswith("https://"))

        row3 = normalize_row(SAMPLE_RAW_ROWS[2])
        self.assertEqual(row3["smpc_url"], "")

    def test_upsert_lookup_and_fts_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = GreenbookStore(Path(tmp) / "greenbook.db")
            inserted = store.upsert_rows(SAMPLE_RAW_ROWS)
            self.assertEqual(inserted, 3)
            # Idempotent upsert
            store.upsert_rows(SAMPLE_RAW_ROWS)
            self.assertEqual(store.count(), 3)

            # Normalized NAFDAC lookup (lowercase + em-dash)
            by_code = store.lookup_by_nafdac("a4–6238")
            self.assertEqual(len(by_code), 1)
            self.assertEqual(by_code[0]["product_name"], "Artheget EZ")

            # FTS search by brand name
            by_brand = store.search("Augmentin")
            self.assertEqual(len(by_brand), 1)
            self.assertEqual(by_brand[0]["nafdac_number"], "04-1234")

            # FTS search by active ingredient
            by_ing = store.search("Artemether Lumefantrine")
            self.assertEqual(len(by_ing), 1)
            self.assertEqual(by_ing[0]["product_id"], 3)

            # Search directly by NAFDAC code via search()
            by_nrn = store.search("A4-100160")
            self.assertEqual(len(by_nrn), 1)
            self.assertEqual(by_nrn[0]["product_name"], "AG Spironolactone")

    def test_sync_from_remote_paginates_with_mock_fetcher(self) -> None:
        pages = {
            0: {"recordsTotal": 3, "data": SAMPLE_RAW_ROWS[:2]},
            2: {"recordsTotal": 3, "data": SAMPLE_RAW_ROWS[2:]},
        }
        calls: list[tuple[int, int]] = []

        def fake_fetcher(start: int, length: int) -> dict:
            calls.append((start, length))
            return pages.get(start, {"recordsTotal": 3, "data": []})

        with tempfile.TemporaryDirectory() as tmp:
            store = GreenbookStore(Path(tmp) / "greenbook.db")
            summary = store.sync_from_remote(batch_size=2, delay_s=0.0, fetcher=fake_fetcher)
            self.assertEqual(calls, [(0, 2), (2, 2)])
            self.assertEqual(summary["fetched"], 3)
            self.assertEqual(summary["records_stored"], 3)
            self.assertEqual(store.count(), 3)
            self.assertEqual(store.metadata()["records_stored"], "3")
            self.assertEqual(store.search("Spironolactone")[0]["nafdac_number"], "A4-100160")


if __name__ == "__main__":
    unittest.main()
