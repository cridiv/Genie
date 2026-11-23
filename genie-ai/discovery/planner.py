"""Seed enrichment from local Greenbook and multi-angle query expansion."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .models import DiscoverySeed, SearchQuery

_CORP_SUFFIX_RE = re.compile(
    r"\b(?:limited|ltd|plc|inc|corp|nigeria|company|pharmaceuticals?|pharma)\b",
    re.IGNORECASE,
)


def enrich_seed_from_greenbook(seed: DiscoverySeed, matches: List[Dict]) -> DiscoverySeed:
    """Fill missing seed fields from the top local Greenbook match without overwriting inputs."""
    if not matches:
        return seed
    top = matches[0]

    product_name = seed.product_name
    if not product_name:
        name = str(top.get("product_name") or "").strip()
        strength = str(top.get("strength") or "").strip()
        if name and strength and strength.lower() not in name.lower():
            product_name = f"{name} {strength}"
        elif name:
            product_name = name

    manufacturer = seed.manufacturer or (str(top.get("applicant_name") or "").strip() or None)
    nafdac_number = seed.nafdac_number or (str(top.get("nafdac_number") or "").strip() or None)

    return DiscoverySeed(
        product_name=product_name,
        manufacturer=manufacturer,
        nafdac_number=nafdac_number,
        gtin=seed.gtin,
        country=seed.country,
    )


def _short_manufacturer(manufacturer: Optional[str]) -> str:
    if not manufacturer:
        return ""
    stripped = _CORP_SUFFIX_RE.sub("", manufacturer)
    cleaned = " ".join(stripped.split())
    return cleaned or " ".join(manufacturer.split())


def build_queries(seed: DiscoverySeed, *, has_smpc_pdf: bool = False) -> List[SearchQuery]:
    """Build targeted multi-angle search queries from an enriched DiscoverySeed."""
    name = (seed.product_name or "").strip()
    nafdac = (seed.nafdac_number or "").strip()
    gtin = (seed.gtin or "").strip()
    subject = name or nafdac or gtin
    mfr = _short_manufacturer(seed.manufacturer)

    queries: List[SearchQuery] = []

    # 1. Regulatory alerts & recalls on NAFDAC
    if name:
        queries.append(
            SearchQuery(
                angle="regulatory_alerts",
                query=f'"{name}" NAFDAC recall OR alert OR counterfeit',
                include_domains=["nafdac.gov.ng"],
            )
        )
    elif nafdac:
        queries.append(
            SearchQuery(
                angle="regulatory_alerts",
                query=f'"{nafdac}" NAFDAC',
                include_domains=["nafdac.gov.ng"],
            )
        )

    # 2. Official manufacturer page / packaging / SmPC
    if has_smpc_pdf:
        mfr_query = (
            f'"{subject}" {mfr} packaging OR pack OR tablets'
            if mfr
            else f'"{subject}" official manufacturer packaging OR pack'
        )
    else:
        mfr_query = (
            f'"{subject}" {mfr} official leaflet OR SmPC OR packaging'
            if mfr
            else f'"{subject}" official manufacturer leaflet OR SmPC OR packaging'
        )
    queries.append(SearchQuery(angle="manufacturer", query=mfr_query))

    # 3. Nigerian pharmacies & product pages (high yield for packaging photos & JSON-LD)
    queries.append(
        SearchQuery(
            angle="pharma_reference",
            query=f'"{subject}" pharmacy Nigeria price OR pack OR tablets',
        )
    )

    # 4. Packaging updates / counterfeit alerts specifically mentioning the product
    queries.append(
        SearchQuery(
            angle="packaging_alerts",
            query=f'"{subject}" "new pack" OR "fake" OR "counterfeit" Nigeria',
        )
    )

    # 5. Exact identifier lookup when NAFDAC number or GTIN is known
    if gtin and nafdac:
        id_query = f'"{nafdac}" OR "{gtin}" Nigeria'
    elif nafdac:
        id_query = f'"{nafdac}" NAFDAC'
    elif gtin:
        id_query = f'"{gtin}"'
    else:
        id_query = ""
    if id_query:
        queries.append(SearchQuery(angle="identifier_exact", query=id_query))

    return queries


def build_image_query(seed: DiscoverySeed) -> str:
    """Build a focused query for direct product packaging image search."""
    name = (seed.product_name or "").strip()
    nafdac = (seed.nafdac_number or "").strip()
    gtin = (seed.gtin or "").strip()
    subject = name or nafdac or gtin
    mfr = _short_manufacturer(seed.manufacturer)
    mfr_token = mfr.split()[0] if mfr else ""
    if mfr_token and mfr_token.lower() not in subject.lower():
        return f"{subject} {mfr_token} pack box"
    return f"{subject} medicine pack box"
