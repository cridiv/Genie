"""Tests for Abeokuta PCN-verified nearby pharmacy discovery (`registry/pharmacies.py`)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from registry.pharmacies import find_nearby_pharmacies, haversine_km
from registry.trusted_sources import TrustedSourceStore


class TestNearbyPharmacies(unittest.TestCase):
    def test_haversine_distance_sanity(self) -> None:
        # Oke-Ilewo to Idi-Aba (FMC), Abeokuta is ~4-5 km
        d = haversine_km(7.1422, 3.3375, 7.1469, 3.3792)
        self.assertGreater(d, 3.0)
        self.assertLess(d, 6.0)

    def test_serper_maps_results_match_abeokuta_pcn_registry_and_frontend_schema(self) -> None:
        mock_places = [
            {
                "title": "Unregistered Patent Medicine Shop",
                "address": "10 Lalubu Street, Oke-Ilewo, Abeokuta",
                "latitude": 7.1420,
                "longitude": 3.3374,
                "website": "https://unverifiedshop.example.com",
                "rating": 3.9,
                "ratingCount": 8,
                "placeId": "ChIJRandomAbeokuta1",
            },
            {
                "title": "Vanguard Pharmacy Oke-Ilewo",
                "address": "38 Lalubu Street, Oke-Ilewo, Abeokuta, Ogun State",
                "latitude": 7.1419,
                "longitude": 3.3372,
                "website": "https://www.vanguardpharmacy.com.ng/",
                "phoneNumber": "+234 803 717 9900",
                "rating": 4.6,
                "ratingCount": 140,
                "placeId": "ChIJVanguardAbk1",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            store = TrustedSourceStore(Path(tmp) / "genie.db")
            store.ensure_seeded()

            with patch("registry.pharmacies._fetch_serper_maps", return_value=mock_places):
                resp = find_nearby_pharmacies(
                    lat=7.1422,
                    lng=3.3375,
                    radius_km=20.0,
                    limit=12,
                    verified_only=False,
                    trusted_store=store,
                    serper_api_key="test-key",
                )

            self.assertEqual(resp.source, "serper_maps+pcn_abeokuta")
            self.assertGreaterEqual(resp.verifiedCount, 1)
            self.assertTrue(resp.pharmacies[0].verified)
            self.assertFalse(resp.pharmacies[0].stockConfirmed)
            self.assertIn("google.com/maps/dir/", resp.pharmacies[0].directionsUrl)
            self.assertIn("google.com/maps/search/", resp.pharmacies[0].googleMapsUrl)

            dumped = resp.pharmacies[0].model_dump()
            for key in (
                "id",
                "name",
                "address",
                "area",
                "distanceKm",
                "licenseId",
                "verified",
                "stockConfirmed",
                "latitude",
                "longitude",
                "googleMapsUrl",
                "directionsUrl",
            ):
                self.assertIn(key, dumped)

            unverified = [p for p in resp.pharmacies if not p.verified]
            self.assertEqual(len(unverified), 1)
            self.assertEqual(unverified[0].name, "Unregistered Patent Medicine Shop")
            self.assertEqual(unverified[0].licenseId, "Unverified listing")

    def test_default_location_is_abeokuta_with_verified_only_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustedSourceStore(Path(tmp) / "genie.db")
            store.ensure_seeded()
            resp = find_nearby_pharmacies(
                verified_only=True,
                trusted_store=store,
                use_live_serper=False,
            )
            self.assertEqual(resp.source, "curated_pcn_abeokuta")
            self.assertIn("Abeokuta", resp.queryLocation)
            self.assertGreaterEqual(resp.total, 5)
            self.assertTrue(all(p.verified for p in resp.pharmacies))
            self.assertTrue(all(not p.stockConfirmed for p in resp.pharmacies))
            self.assertTrue(any("Vanguard" in p.name for p in resp.pharmacies))
            self.assertTrue(any("MedPlus" in p.name for p in resp.pharmacies))


if __name__ == "__main__":
    unittest.main()
