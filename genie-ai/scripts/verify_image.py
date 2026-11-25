#!/usr/bin/env python3
"""Verify a real drug packaging photo directly from the CLI.

Usage:
  cd /Users/Cridiv/Documents/Genie/genie-ai
  PYTHONPATH=. .venv/bin/python scripts/verify_image.py /path/to/drug_photo.jpg
  PYTHONPATH=. .venv/bin/python scripts/verify_image.py data/products/augmentin_625_mg/images/0c0d49be72950182.jpg
  PYTHONPATH=. .venv/bin/python scripts/verify_image.py /path/to/photo.jpg --no-discover --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orchestrator import GenieOrchestrator
from verification.image_scan import infer_mime_type, load_local_dotenv, verify_image_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GENIE AI verification on a real drug photo.")
    parser.add_argument("image", help="Path to a JPEG, PNG, or WebP photo of a medicine pack")
    parser.add_argument(
        "--no-visual",
        action="store_true",
        help="Skip Vision-LLM visual comparison against approved reference images",
    )
    parser.add_argument(
        "--no-discover",
        action="store_true",
        help="Do not enqueue background discovery if the product is Level C / unregistered",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print the full raw JSON response",
    )
    args = parser.parse_args()

    img_path = Path(args.image).expanduser().resolve()
    if not img_path.is_file():
        print(f"Error: file not found: {img_path}", file=sys.stderr)
        return 1

    load_local_dotenv()
    mime_type = infer_mime_type(img_path.name)
    image_bytes = img_path.read_bytes()

    orch = GenieOrchestrator()
    try:
        resp = verify_image_bytes(
            image_bytes,
            mime_type,
            orchestrator=orch,
            compare_visual=not args.no_visual,
            auto_discover=not args.no_discover,
        )
    finally:
        orch.shutdown(wait=False)

    if args.as_json:
        print(json.dumps(resp.model_dump(mode="json"), indent=2))
        return 0

    ext = resp.extracted_scan
    ver = resp.verification.result
    print(f"\n=== GENIE AI Live Photo Verification ({img_path.name}) ===")
    print(f"Scan ID           : {resp.scan_id or '-'}")
    print(f"Saved JSON        : {resp.scan_json_path or '-'}")
    print(f"Vision Model      : {resp.vision_model}")
    print(f"Extracted Product : {ext.product_name_hint or '-'}")
    print(f"Extracted NAFDAC  : {ext.nafdac_number or '-'}")
    print(f"Batch / MFG / EXP : {ext.batch_number or '-'} | {ext.mfg_date or '-'} | {ext.expiry_date or '-'}")
    print(f"GTIN              : {ext.gtin or '-'}")
    print(f"Security Features : {', '.join(ext.observed_security_features) or '-'}")
    print(f"Visual Compared   : {resp.visual_comparison_used} ({len(resp.reference_images_compared)} ref image(s))")
    print("-" * 60)
    print(f"VERDICT           : {ver.verdict}  (ml_infra: {ver.ml_infra_verdict})")
    print(f"Confidence / Cov  : {ver.confidence:.3f} / {ver.coverage:.0%}  (Reference Level {ver.reference_level})")
    if ver.matched_product:
        mp = ver.matched_product
        print(f"Matched Product   : {mp.get('brand_name')} [{mp.get('nafdac_number')}] — {mp.get('manufacturer')}")
    print(f"Summary           : {ver.summary}")
    print(f"Orchestrator Time : {resp.verification.execution_time_ms} ms")
    if resp.verification.discovery_job_id:
        print(f"Discovery Job     : {resp.verification.discovery_job_id} ({resp.verification.discovery_job_status})")

    print("\nSignals:")
    for sig in ver.signals:
        flag = f" [HARD NEG: {sig.hard_negative}]" if sig.hard_negative else ""
        print(f"  - {sig.name:18s} | {sig.status:14s} | {sig.direction:8s} | w={sig.weight:.2f}/{sig.max_weight:.2f}{flag} — {sig.summary}")

    if ver.limitations:
        print("\nLimitations:")
        for lim in ver.limitations:
            print(f"  * {lim}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
