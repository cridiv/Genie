"""Offline unit tests for Step 2 Multi-Angle Discovery & Domain Trust Tiering."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discovery import (
    DiscoverySeed,
    build_queries,
    canonicalize_url,
    classify_url,
    discover,
    enrich_seed_from_greenbook,
    rank_and_select,
)
from registry.greenbook import GreenbookStore


class TestTrustAndRanking(unittest.TestCase):
    def test_canonicalize_url_strips_tracking_www_fragment_and_slash(self) -> None:
        url = "HTTPS://WWW.MedPlusNigeria.com/products/augmentin/?utm_source=ddg&b=2&fbclid=xyz&a=1#details"
        self.assertEqual(
            canonicalize_url(url),
            "https://medplusnigeria.com/products/augmentin?a=1&b=2",
        )

    def test_classify_url_tiers_and_dynamic_manufacturer(self) -> None:
        self.assertEqual(classify_url("https://jiji.ng/item/augmentin-fake"), (0, "blocked"))
        self.assertEqual(classify_url("https://www.instagram.com/p/123"), (0, "blocked"))
        self.assertEqual(classify_url("https://nafdac.gov.ng/public-alert/1"), (1, "regulatory"))
        self.assertEqual(classify_url("https://www.gsk.com/en-gb/products/augmentin"), (1, "official_manufacturer"))
        # Dynamic manufacturer match: "Getz" matches getzpharma.com, while generic "pharma" does NOT match randompharma.com
        self.assertEqual(
            classify_url("https://getzpharma.com/product/artheget", manufacturer_hint="Getz Pharma Nigeria Limited"),
            (1, "official_manufacturer"),
        )
        self.assertEqual(
            classify_url("https://randompharma.com/product/artheget", manufacturer_hint="Getz Pharma Nigeria Limited"),
            (3, "general_web"),
        )
        self.assertEqual(classify_url("https://medplusnigeria.com/p/augmentin"), (2, "vetted_pharma"))
        self.assertEqual(classify_url("https://somehealthblog.ng/augmentin"), (3, "general_web"))

    def test_rank_and_select_dedups_filters_and_enforces_diversity(self) -> None:
        hits = [
            {"url": "https://jiji.ng/listing/1", "title": "Cheap drugs", "angle": "pharma_reference"},
            {"url": "https://someblog.com/a?utm_source=x", "title": "Blog A", "angle": "packaging_alerts"},
            {"url": "https://www.someblog.com/a/", "title": "Blog A dup", "angle": "pharma_reference"},
            {"url": "https://medplusnigeria.com/p/1", "title": "MedPlus 1", "angle": "pharma_reference"},
            {"url": "https://medplusnigeria.com/p/2", "title": "MedPlus 2", "angle": "pharma_reference"},
            {"url": "https://medplusnigeria.com/p/3", "title": "MedPlus 3", "angle": "pharma_reference"},
            {"url": "https://nafdac.gov.ng/alert-1", "title": "NAFDAC Alert", "angle": "regulatory_alerts"},
            {"url": "https://gsk.com/augmentin.pdf", "title": "GSK Leaflet", "angle": "manufacturer"},
        ]
        ranked = rank_and_select(hits, manufacturer_hint="GlaxoSmithKline", max_urls=5, max_per_domain=2)
        domains = [c.domain for c in ranked]
        self.assertNotIn("jiji.ng", domains)
        self.assertEqual(domains.count("medplusnigeria.com"), 2)
        # Tier 1 regulatory + manufacturer come first
        self.assertEqual(ranked[0].trust_tier, 1)
        self.assertEqual(ranked[1].trust_tier, 1)
        # Dedup merged both angles onto someblog.com/a
        blog = [c for c in ranked if c.domain == "someblog.com"]
        self.assertEqual(len(blog), 1)
        self.assertEqual(set(blog[0].angles), {"packaging_alerts", "pharma_reference"})


class TestPlannerAndDiscovery(unittest.TestCase):
    def test_enrich_and_build_queries(self) -> None:
        seed = DiscoverySeed(nafdac_number="A4-6238")
        enriched = enrich_seed_from_greenbook(
            seed,
            [
                {
                    "product_name": "Artheget EZ",
                    "strength": "80 mg; 480 mg",
                    "applicant_name": "Getz Pharma Nigeria Limited",
                    "nafdac_number": "A4-6238",
                }
            ],
        )
        self.assertEqual(enriched.product_name, "Artheget EZ 80 mg; 480 mg")
        self.assertEqual(enriched.manufacturer, "Getz Pharma Nigeria Limited")
        self.assertEqual(enriched.nafdac_number, "A4-6238")

        queries = build_queries(enriched)
        angles = [q.angle for q in queries]
        self.assertEqual(
            angles,
            ["regulatory_alerts", "manufacturer", "pharma_reference", "packaging_alerts", "identifier_exact"],
        )
        self.assertEqual(queries[0].include_domains, ["nafdac.gov.ng"])
        self.assertIn("Getz", queries[1].query)

    def test_discover_end_to_end_with_greenbook_and_mocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = GreenbookStore(Path(tmp) / "greenbook.db")
            store.upsert_rows(
                [
                    {
                        "product_id": 3,
                        "product_name": "Artheget EZ##",
                        "strength": "80 mg; 480 mg",
                        "NAFDAC": "A4-6238",
                        "status": "Active",
                        "smpc": "https://admin.greenbook.nafdac.gov.ng/smpc/artheget.pdf",
                        "applicant": {"name": "Getz Pharma Nigeria Limited"},
                        "ingredient": {"ingredient_name": "Artemether; Lumefantrine"},
                        "form": {"name": "Tablet"},
                    }
                ]
            )

            def fake_search(query: str, **kwargs):
                if kwargs.get("include_domains") == ["nafdac.gov.ng"]:
                    return {"results": [{"url": "https://nafdac.gov.ng/alerts/artheget", "title": "NAFDAC"}], "error": None}
                if "SmPC" in query:
                    return {
                        "results": [
                            {"url": "https://getzpharma.com/products/artheget-ez", "title": "Getz"},
                            {"url": "https://jiji.ng/fake-artheget", "title": "Blocked"},
                        ],
                        "error": None,
                    }
                return {
                    "results": [{"url": "https://medplusnigeria.com/p/artheget-ez", "title": "MedPlus"}],
                    "error": None,
                }

            def fake_extract(urls, **kwargs):
                results = []
                failed = []
                for u in urls:
                    if "alerts" in u:
                        failed.append({"url": u, "error": "HTTP 404", "reason": "not_found"})
                    else:
                        results.append(
                            {
                                "url": u,
                                "title": f"Title for {u}",
                                "content": "Artheget EZ NAFDAC Reg. No.: A4-6238",
                                "stage": "static",
                                "images": [{"url": "https://getzpharma.com/box.jpg", "source": "jsonld"}],
                                "identifiers": {"nafdac_numbers": ["A4-6238"], "gtins": []},
                            }
                        )
                return {"results": results, "failed": failed, "status": {}}

            bundle = discover(
                DiscoverySeed(product_name="Artheget EZ"),
                greenbook=store,
                max_urls=4,
                search_fn=fake_search,
                extract_fn=fake_extract,
            )

            self.assertEqual(len(bundle.greenbook_matches), 1)
            self.assertEqual(bundle.enriched_seed.nafdac_number, "A4-6238")
            self.assertEqual(bundle.enriched_seed.manufacturer, "Getz Pharma Nigeria Limited")
            self.assertEqual(bundle.stats["pages_extracted"], 3)
            self.assertEqual(bundle.stats["pages_failed"], 1)

            urls = [s.url for s in bundle.sources]
            self.assertIn("https://admin.greenbook.nafdac.gov.ng/smpc/artheget.pdf", urls)
            self.assertIn("https://getzpharma.com/products/artheget-ez", urls)
            self.assertIn("https://medplusnigeria.com/p/artheget-ez", urls)
            self.assertFalse(any("jiji.ng" in u for u in urls))
            # SmPC PDF is Tier 1 regulatory and comes first
            self.assertTrue(bundle.sources[0].is_smpc_pdf)
            self.assertEqual(bundle.sources[0].trust_tier, 1)


if __name__ == "__main__":
    unittest.main()
