"""GS1 Digital Link URI parser with domain security sandboxing."""
from urllib.parse import parse_qs, urlparse
from typing import Any, Dict

from genie.barcode.gtin import normalize_to_gtin14, validate_gtin_check_digit


def parse_digital_link_url(url: str, allowed_domains: list[str] | None = None) -> Dict[str, Any]:
    """
    Parses URLs like https://example.com/01/06151234567893/10/AB1234?17=271231
    and validates the domain against authorized manufacturer lists.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    domain_trusted = True
    if allowed_domains:
        domain_trusted = any(domain == d or domain.endswith("." + d) for d in allowed_domains)

    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    extracted: Dict[str, str] = {}

    idx = 0
    while idx < len(path_parts) - 1:
        ai = path_parts[idx]
        val = path_parts[idx + 1]
        extracted[ai] = val
        idx += 2

    query_params = parse_qs(parsed.query)
    for q_ai, vals in query_params.items():
        if vals:
            extracted[q_ai] = vals[0]

    gtin = extracted.get("01")
    gtin_valid = validate_gtin_check_digit(gtin) if gtin else False

    return {
        "url": url,
        "domain": domain,
        "domain_trusted": domain_trusted,
        "gtin": normalize_to_gtin14(gtin) if gtin and gtin_valid else gtin,
        "batch": extracted.get("10"),
        "expiry": extracted.get("17"),
        "serial": extracted.get("21"),
        "raw_attributes": extracted,
        "gtin_valid": gtin_valid,
    }
