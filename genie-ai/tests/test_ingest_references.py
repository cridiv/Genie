"""Offline unit tests for curated reference ingestion (`scripts/ingest_references.py`)."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from registry.trusted_sources import TrustedSourceStore
from scripts.ingest_references import (
    fetch_review_images_for_product,
    ingest_from_review_folder,
    ingest_product_references,
)


def _make_jpeg(size=(420, 420), color=(220, 180, 40)) -> bytes:
    img = Image.new("RGB", size, color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 30, size[0] - 30, size[1] - 30], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestIngestReferences(unittest.TestCase):
    def test_ingest_local_photo_is_idempotent_and_approves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            photo = tmp_path / "coartem_front.jpg"
            photo.write_bytes(_make_jpeg())

            entry = {
                "slug": "coartem_20_120_tablets",
                "product_name": "Coartem 20/120 Tablets",
                "nafdac_number": "04-3275",
                "sources": [
                    {
                        "local_path": str(photo),
                        "view_type": "front_box",
                        "pack_size_variant": "24 tablets",
                        "edition_id": "edition_ng_1",
                        "has_local_regulatory_markers": True,
                        "notes": "Direct phone photo of Nigerian retail pack",
                    }
                ],
            }

            r1 = ingest_product_references(
                entry,
                products_dir=tmp_path / "products",
                approve_by="Pharm. Ada",
            )
            self.assertEqual(r1["added"], 1)
            self.assertEqual(r1["errors"], [])

            # Second run is idempotent by SHA-256
            r2 = ingest_product_references(
                entry,
                products_dir=tmp_path / "products",
                approve_by="Pharm. Ada",
            )
            self.assertEqual(r2["added"], 0)
            self.assertEqual(r2["skipped_duplicate"], 1)

            data = json.loads((tmp_path / "products" / "coartem_20_120_tablets" / "product.json").read_text())
            self.assertEqual(len(data["packaging_versions"]), 1)
            ver = data["packaging_versions"][0]
            self.assertEqual(ver["status"], "approved")
            img = ver["images"][0]
            self.assertEqual(img["status"], "approved")
            self.assertEqual(img["approved_by"], "Pharm. Ada")
            self.assertEqual(img["captured_from_domain"], "direct_capture")
            self.assertTrue(img["market_verified"])

    def test_ingest_page_url_enforces_trusted_sources_and_extracts_top_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = TrustedSourceStore(tmp_path / "genie.db")
            store.ensure_seeded()

            jpeg = _make_jpeg(color=(40, 140, 90))

            def fake_extract(urls, **_kwargs):
                return {
                    "results": [
                        {
                            "url": urls[0],
                            "images": [{"url": "https://cdn.healthplusnigeria.com/coartem.jpg", "source": "jsonld"}],
                        }
                    ],
                    "failed": [],
                }

            entry = {
                "slug": "coartem_20_120_tablets",
                "product_name": "Coartem 20/120 Tablets",
                "nafdac_number": "04-3275",
                "sources": [
                    {
                        "page_url": "https://healthplusnigeria.com/products/coartem-20mg-120mg-x24",
                        "view_type": "front_box",
                        "pack_size_variant": "24 tablets",
                    },
                    {
                        "page_url": "https://www.indiamart.com/proddetail/coartem-24741413033.html",
                        "view_type": "front_box",
                    },
                ],
            }

            res = ingest_product_references(
                entry,
                products_dir=tmp_path / "products",
                trusted_store=store,
                extract_fn=fake_extract,
                downloader=lambda _u: (jpeg, "image/jpeg"),
            )
            self.assertEqual(res["added"], 1)
            self.assertEqual(len(res["errors"]), 1)
            self.assertIn("not a verified trusted_source", res["errors"][0])

            data = json.loads((tmp_path / "products" / "coartem_20_120_tablets" / "product.json").read_text())
            img = data["packaging_versions"][0]["images"][0]
            self.assertEqual(img["captured_from_domain"], "healthplusnigeria.com")
            self.assertEqual(img["captured_from_type"], "pharmacy")
            self.assertEqual(img["status"], "staging")

    def test_fetch_review_then_manual_delete_then_ingest_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = TrustedSourceStore(tmp_path / "genie.db")
            store.ensure_seeded()

            img1 = _make_jpeg(size=(400, 400), color=(220, 40, 40))
            img2 = Image.new("RGB", (420, 420), color=(25, 90, 210))
            d2 = ImageDraw.Draw(img2)
            d2.polygon([(0, 0), (420, 0), (0, 420)], fill=(240, 220, 40))
            buf2 = io.BytesIO()
            img2.save(buf2, format="JPEG")
            img2_bytes = buf2.getvalue()

            payloads = {
                "https://healthplusnigeria.com/coartem-1.jpg": (img1, "image/jpeg"),
                "https://medplusnig.com/coartem-2.jpg": (img2_bytes, "image/jpeg"),
            }
            hits = [
                {
                    "url": "https://healthplusnigeria.com/coartem-1.jpg",
                    "source_page_url": "https://healthplusnigeria.com/products/coartem",
                    "title": "Coartem 20/120",
                },
                {
                    "url": "https://medplusnig.com/coartem-2.jpg",
                    "source_page_url": "https://medplusnig.com/products/coartem",
                    "title": "Coartem 20/120",
                },
            ]
            entry = {
                "slug": "coartem_20_120_tablets",
                "product_name": "Coartem 20/120 Tablets",
                "nafdac_number": "04-3275",
            }
            fetched = fetch_review_images_for_product(
                entry,
                review_dir=tmp_path / "review",
                trusted_store=store,
                search_images_fn=lambda *_a, **_k: hits,
                downloader=lambda u: payloads[u],
            )
            self.assertEqual(fetched["saved"], 2)

            review_folder = tmp_path / "review" / "coartem_20_120_tablets"
            jpgs = sorted(p for p in review_folder.iterdir() if p.suffix == ".jpg")
            self.assertEqual(len(jpgs), 2)
            # Simulate user manually deleting the second image after inspection
            jpgs[1].unlink()

            ingested = ingest_from_review_folder(
                entry,
                review_dir=tmp_path / "review",
                products_dir=tmp_path / "products",
                approve_by="Cridiv",
            )
            self.assertEqual(ingested["added"], 1)
            data = json.loads((tmp_path / "products" / "coartem_20_120_tablets" / "product.json").read_text())
            self.assertEqual(len(data["packaging_versions"][0]["images"]), 1)
            self.assertEqual(data["packaging_versions"][0]["images"][0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
