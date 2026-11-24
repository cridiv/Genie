"""Offline unit tests for Phase A: curated trusted_sources registry, allowlisted images, and promote script."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from discovery.models import DiscoveredSource, DiscoveryBundle, DiscoverySeed
from discovery.planner import build_trusted_image_queries
from discovery.trust import classify_url
from intelligence.images import collect_candidate_image_urls
from registry.trusted_sources import TrustedSourceStore
from scripts.promote_reference import promote_reference_image


class TestTrustedSources(unittest.TestCase):
    def test_seed_defaults_is_idempotent_and_enforces_verified_vs_provisional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustedSourceStore(Path(tmp) / "genie.db")
            first_count = store.seed_defaults()
            second_count = store.seed_defaults()

            self.assertGreater(first_count, 10)
            self.assertEqual(second_count, 0)

            # Verified Nigerian pharmacies & manufacturers pass
            hp = store.is_verified_image_source("https://healthplusnigeria.com/products/coartem")
            self.assertIsNotNone(hp)
            self.assertEqual(hp["domain"], "healthplusnigeria.com")
            self.assertEqual(hp["source_type"], "pharmacy")
            self.assertIn("superintendent_pharmacist_named", hp["criteria_met"])

            self.assertIsNotNone(store.is_verified_image_source("https://www.medplusnigeria.com/p/aug"))
            self.assertIsNotNone(store.is_verified_image_source("https://drugstoc.com/item/123"))
            self.assertIsNotNone(store.is_verified_image_source("https://shop.novartis.com/coartem"))
            self.assertIsNotNone(store.is_verified_image_source("https://www.gsk.com/en-ng/augmentin"))

            # Provisional aggregators / unverified pharmacies are rejected for reference images
            self.assertIsNone(store.is_verified_image_source("https://gomed.ng/product/coartem"))
            self.assertIsNone(store.is_verified_image_source("https://medecify.com/product/augmentin"))
            self.assertIsNone(store.is_verified_image_source("https://onehealthng.com/p/coartem"))

            # Unknown / B2B / regulator domains are rejected as packaging image sources
            self.assertIsNone(store.is_verified_image_source("https://www.indiamart.com/proddetail/coartem"))
            self.assertIsNone(store.is_verified_image_source("https://nafdac.gov.ng/alerts/123"))

    def test_get_verified_image_domains_includes_ng_pharmacies_and_matched_manufacturer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustedSourceStore(Path(tmp) / "genie.db")
            store.ensure_seeded()
            domains = store.get_verified_image_domains(
                country="NG",
                manufacturer_hint="Novartis Nigeria Limited",
            )
            self.assertIn("healthplusnigeria.com", domains)
            self.assertIn("medplusnigeria.com", domains)
            self.assertIn("drugstoc.com", domains)
            self.assertIn("novartis.com", domains)
            self.assertNotIn("gomed.ng", domains)
            self.assertNotIn("medecify.com", domains)
            self.assertNotIn("gsk.com", domains)

    def test_b2b_marketplaces_are_blocked_tier_zero(self) -> None:
        for url in (
            "https://www.indiamart.com/proddetail/coartem-tablets-20-120mg-24741413033.html",
            "https://www.alibaba.com/product-detail/coartem_123.html",
            "https://made-in-china.com/item/123",
            "https://tradeindia.com/products/coartem",
        ):
            tier, label = classify_url(url)
            self.assertEqual((tier, label), (0, "blocked"))

    def test_build_trusted_image_queries_caps_at_five_domains_per_query(self) -> None:
        seed = DiscoverySeed(product_name="Coartem 20/120 Tablets", manufacturer="Novartis Nigeria Limited")
        domains = [
            "healthplusnigeria.com",
            "medplusnigeria.com",
            "drugstoc.com",
            "novartis.com",
            "emzor.com",
            "fidson.com",
            "gsk.com",
        ]
        queries = build_trusted_image_queries(seed, trusted_domains=domains, max_domains_per_query=5)
        self.assertEqual(len(queries), 2)
        self.assertTrue(queries[0].startswith("Coartem -dispersible -syrup ("))
        self.assertNotIn("20/120", queries[0])
        self.assertNotIn("pack box", queries[0])
        self.assertNotIn("Novartis", queries[0])
        self.assertIn("site:healthplusnigeria.com", queries[0])
        self.assertIn("site:emzor.com", queries[0])
        self.assertNotIn("site:fidson.com", queries[0])
        self.assertIn("site:fidson.com", queries[1])
        self.assertIn("site:gsk.com", queries[1])

    def test_collect_candidate_images_trusted_only_drops_provisional_and_untrusted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustedSourceStore(Path(tmp) / "genie.db")
            store.ensure_seeded()

            bundle = DiscoveryBundle(
                seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
                enriched_seed=DiscoverySeed(product_name="Coartem 20/120 Tablets"),
                sources=[
                    DiscoveredSource(
                        url="https://medecify.com/product/coartem",
                        canonical_url="https://medecify.com/product/coartem",
                        domain="medecify.com",
                        trust_tier=3,
                        trust_label="general_web",
                        angles=["pharma_reference"],
                        title="Coartem",
                        content="Coartem",
                        stage="static",
                        images=[{"url": "https://medecify.com/coartem.jpg", "source": "jsonld"}],
                    ),
                    DiscoveredSource(
                        url="https://healthplusnigeria.com/products/coartem-20-120",
                        canonical_url="https://healthplusnigeria.com/products/coartem-20-120",
                        domain="healthplusnigeria.com",
                        trust_tier=2,
                        trust_label="vetted_pharma",
                        angles=["pharma_reference"],
                        title="Coartem",
                        content="Coartem",
                        stage="static",
                        images=[{"url": "https://healthplusnigeria.com/coartem-front.jpg", "source": "jsonld"}],
                    ),
                ],
                image_candidates=[
                    {
                        "url": "https://5.imimg.com/coartem.png",
                        "source_page_url": "https://www.indiamart.com/proddetail/coartem.html",
                        "source_trust_tier": 3,
                        "source": "image_search",
                    },
                    {
                        "url": "https://gomed.ng/coartem.webp",
                        "source_page_url": "https://gomed.ng/product/coartem",
                        "source_trust_tier": 3,
                        "source": "image_search",
                    },
                    {
                        "url": "https://medplusnigeria.com/media/coartem.jpg",
                        "source_page_url": "https://medplusnigeria.com/p/coartem",
                        "source_trust_tier": 2,
                        "source": "image_search",
                    },
                ],
            )

            cands = collect_candidate_image_urls(bundle, trusted_store=store, trusted_only=True)
            self.assertEqual(
                [c["url"] for c in cands],
                [
                    "https://healthplusnigeria.com/coartem-front.jpg",
                    "https://medplusnigeria.com/media/coartem.jpg",
                ],
            )
            self.assertEqual(cands[0]["captured_from_domain"], "healthplusnigeria.com")
            self.assertEqual(cands[0]["captured_from_type"], "pharmacy")
            self.assertEqual(cands[1]["captured_from_domain"], "medplusnigeria.com")

    def test_promote_reference_image_updates_status_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p_json = Path(tmp) / "product.json"
            p_json.write_text(
                json.dumps(
                    {
                        "brand_name": "Augmentin 625 mg",
                        "packaging_versions": [
                            {
                                "edition_id": "edition_1",
                                "status": "staging",
                                "images": [
                                    {
                                        "image_id": "0c0d49be72950182",
                                        "view_type": "front_box",
                                        "status": "staging",
                                        "market_verified": False,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            promoted = promote_reference_image(p_json, "0c0d49be72950182", approved_by="Pharm. Ada")
            self.assertEqual(promoted["status"], "approved")
            self.assertEqual(promoted["approved_by"], "Pharm. Ada")
            self.assertTrue(promoted["market_verified"])
            self.assertTrue(promoted["approved_at"])

            reloaded = json.loads(p_json.read_text(encoding="utf-8"))
            self.assertEqual(reloaded["packaging_versions"][0]["status"], "approved")
            self.assertEqual(reloaded["packaging_versions"][0]["images"][0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
