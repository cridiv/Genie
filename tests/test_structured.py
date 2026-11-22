"""Offline unit tests for pharma JSON-LD, identifier pre-extraction, and candidate images."""
from __future__ import annotations

import unittest

from lxml import html as lxml_html

from scraper.extract.reader import reader_document
from scraper.extract.structured import (
    extract_gtins,
    extract_images,
    extract_nafdac_numbers,
    extract_product,
    is_valid_gtin,
)

PRODUCT_HTML = """
<!doctype html>
<html>
<head>
  <title>Augmentin 625mg Tablets - MedPlus Pharmacy</title>
  <meta property="og:image" content="/assets/augmentin-og-pack.jpg" />
  <meta property="twitter:image" content="https://medplus.example/images/site-logo.png" />
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@graph": [
      {"@type": "Organization", "name": "MedPlus"},
      {
        "@type": "Product",
        "name": "Augmentin 625mg Film-Coated Tablets x14",
        "brand": {"@type": "Brand", "name": "Augmentin"},
        "manufacturer": {"@type": "Organization", "name": "GlaxoSmithKline"},
        "sku": "AUG-625-14",
        "mpn": "GSK-625",
        "gtin13": "5000456051231",
        "description": "Broad-spectrum antibiotic containing amoxicillin and clavulanic acid.",
        "image": [
          {"@type": "ImageObject", "url": "https://cdn.medplus.example/augmentin-625-front.jpg"},
          "https://cdn.medplus.example/augmentin-625-back.jpg"
        ],
        "offers": {
          "@type": "Offer",
          "price": "18500",
          "priceCurrency": "NGN",
          "availability": "https://schema.org/InStock"
        }
      }
    ]
  }
  </script>
</head>
<body>
  <header>
    <img src="/img/pharmacy-header.jpg" width="600" height="400" alt="Pharmacy Storefront" />
  </header>
  <nav>
    <img src="/img/nav-promo.jpg" width="400" height="400" alt="Promo" />
  </nav>
  <main>
    <h1>Augmentin 625mg Film-Coated Tablets</h1>
    <p>Augmentin 625mg is manufactured by GlaxoSmithKline for bacterial infections.</p>
    <p>NAFDAC Reg. No.: 04-1234. Packaging updated in 04-2025 with security hologram.</p>
    <p>EAN-13: 5000456051231. Hotline: 0800123456789.</p>
    <img src="/img/company-logo.png" width="300" height="300" alt="MedPlus Logo" />
    <img src="/img/icon-check.svg" width="300" height="300" alt="Verified" />
    <img src="/img/tiny-thumb.jpg" width="80" height="80" alt="Small thumb" />
    <img src="/img/wide-promo.jpg" width="1200" height="200" alt="Promo strip" />
    <img data-src="/img/augmentin-blister.webp" width="800" height="600" alt="Augmentin 625mg blister pack" />
  </main>
  <footer>
    <img src="/img/footer-cert.jpg" width="500" height="500" alt="Footer Badge" />
  </footer>
</body>
</html>
"""

DRUG_HTML = """
<!doctype html>
<html>
<head>
  <title>Coartem 20/120mg - Pharma Reference</title>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "https://schema.org/Drug",
    "name": "Coartem 20mg/120mg Tablets",
    "nonProprietaryName": "Artemether / Lumefantrine",
    "activeIngredient": ["Artemether 20mg", "Lumefantrine 120mg"],
    "dosageForm": "Tablet",
    "manufacturer": {"@type": "Organization", "name": "Novartis"},
    "image": "https://pharma.example/coartem-box.jpg"
  }
  </script>
</head>
<body>
  <main>
    <h1>Coartem 20mg/120mg Dispersible Tablets</h1>
    <p>Coartem is an antimalarial combination therapy containing artemether and lumefantrine.</p>
    <p>Approved with registration code A4-5678L for distribution in Nigeria.</p>
  </main>
</body>
</html>
"""


class TestStructuredPharma(unittest.TestCase):
    def test_product_jsonld_extracts_pharma_fields_and_images(self) -> None:
        prod = extract_product(PRODUCT_HTML)
        self.assertIsNotNone(prod)
        assert prod is not None
        self.assertEqual(prod["entityType"], "Product")
        self.assertEqual(prod["name"], "Augmentin 625mg Film-Coated Tablets x14")
        self.assertEqual(prod["brand"], "Augmentin")
        self.assertEqual(prod["manufacturer"], "GlaxoSmithKline")
        self.assertEqual(prod["sku"], "AUG-625-14")
        self.assertEqual(prod["mpn"], "GSK-625")
        self.assertEqual(prod["gtin"], ["5000456051231"])
        self.assertEqual(prod["price"], "18500")
        self.assertEqual(prod["priceCurrency"], "NGN")
        self.assertEqual(prod["availability"], "InStock")
        self.assertEqual(
            prod["images"],
            [
                "https://cdn.medplus.example/augmentin-625-front.jpg",
                "https://cdn.medplus.example/augmentin-625-back.jpg",
            ],
        )

    def test_drug_jsonld_extracts_drug_fields(self) -> None:
        drug = extract_product(DRUG_HTML)
        self.assertIsNotNone(drug)
        assert drug is not None
        self.assertEqual(drug["entityType"], "Drug")
        self.assertEqual(drug["name"], "Coartem 20mg/120mg Tablets")
        self.assertEqual(drug["nonProprietaryName"], "Artemether / Lumefantrine")
        self.assertEqual(drug["activeIngredient"], ["Artemether 20mg", "Lumefantrine 120mg"])
        self.assertEqual(drug["dosageForm"], "Tablet")
        self.assertEqual(drug["manufacturer"], "Novartis")
        self.assertEqual(drug["images"], ["https://pharma.example/coartem-box.jpg"])

    def test_gtin_check_digit_validation(self) -> None:
        # Valid GTIN-13, GTIN-12 (UPC), GTIN-8, GTIN-14
        self.assertTrue(is_valid_gtin("5000456051231"))
        self.assertTrue(is_valid_gtin("036000291452"))
        self.assertTrue(is_valid_gtin("96385074"))
        self.assertTrue(is_valid_gtin("10012345678902"))
        # Invalid check digit / wrong length / all zeros
        self.assertFalse(is_valid_gtin("5000456051239"))
        self.assertFalse(is_valid_gtin("0800123456789"))
        self.assertFalse(is_valid_gtin("00000000"))
        self.assertFalse(is_valid_gtin("12345"))

    def test_nafdac_extraction_ignores_dates_and_normalizes(self) -> None:
        text = (
            "NAFDAC Reg. No.: 04–1234. Updated 04-2025. "
            "Also registered as B4-9876L, A4-100160 and NAFDAC No: a4-0042."
        )
        nums = extract_nafdac_numbers(text)
        self.assertEqual(nums, ["04-1234", "A4-0042", "B4-9876L", "A4-100160"])
        self.assertNotIn("04-2025", nums)

    def test_gtin_text_extraction_filters_invalid(self) -> None:
        text = "EAN-13: 5000456051231, Fake Barcode: 5000456051239, UPC: 036000291452"
        self.assertEqual(extract_gtins(text), ["5000456051231", "036000291452"])

    def test_image_ranking_and_junk_filtering(self) -> None:
        tree = lxml_html.fromstring(PRODUCT_HTML)
        prod = extract_product(PRODUCT_HTML)
        meta = {
            "og:image": "/assets/augmentin-og-pack.jpg",
            "twitter:image": "https://medplus.example/images/site-logo.png",
        }
        imgs = extract_images(tree, url="https://medplus.example/p/augmentin", product=prod, meta=meta)
        urls = [i["url"] for i in imgs]
        sources = [i["source"] for i in imgs]

        self.assertEqual(
            urls,
            [
                "https://cdn.medplus.example/augmentin-625-front.jpg",
                "https://cdn.medplus.example/augmentin-625-back.jpg",
                "https://medplus.example/assets/augmentin-og-pack.jpg",
                "https://medplus.example/img/augmentin-blister.webp",
            ],
        )
        self.assertEqual(sources, ["jsonld", "jsonld", "og", "img"])
        self.assertEqual(imgs[-1]["alt"], "Augmentin 625mg blister pack")
        self.assertEqual(imgs[-1]["width"], 800)
        self.assertEqual(imgs[-1]["height"], 600)

    def test_reader_document_end_to_end(self) -> None:
        doc = reader_document(PRODUCT_HTML, url="https://medplus.example/p/augmentin", fmt="text")
        self.assertIn("product", doc)
        self.assertEqual(doc["product"]["manufacturer"], "GlaxoSmithKline")
        self.assertIn("images", doc)
        self.assertEqual(len(doc["images"]), 4)
        self.assertIn("identifiers", doc)
        self.assertEqual(doc["identifiers"]["nafdac_numbers"], ["04-1234"])
        self.assertEqual(doc["identifiers"]["gtins"], ["5000456051231"])

        drug_doc = reader_document(DRUG_HTML, url="https://pharma.example/drugs/coartem", fmt="text")
        self.assertEqual(drug_doc["product"]["entityType"], "Drug")
        self.assertEqual(drug_doc["identifiers"]["nafdac_numbers"], ["A4-5678L"])
        self.assertEqual(drug_doc["images"][0]["url"], "https://pharma.example/coartem-box.jpg")


if __name__ == "__main__":
    unittest.main()
