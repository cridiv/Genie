"""Multi-decoder ensemble for 1D barcodes and 2D GS1 DataMatrix / QR codes."""
from typing import Any, Dict, Optional
import numpy as np
from PIL import Image

from genie.barcode.digital_link import parse_digital_link_url
from genie.barcode.enhance import enhance_barcode_crop
from genie.barcode.gs1_parser import GS1PayloadParser
from genie.barcode.gtin import normalize_to_gtin14, validate_gtin_check_digit


class MultiDecoder:
    """Ensemble decoder evaluating zxing-cpp, pyzbar, and pylibdmtx."""

    @classmethod
    def decode(cls, image_np: np.ndarray) -> Optional[Dict[str, Any]]:
        variants = enhance_barcode_crop(image_np)

        # 1. Try zxing-cpp
        try:
            import zxingcpp
            for var in variants:
                results = zxingcpp.read_barcodes(var)
                if results:
                    r = results[0]
                    return cls._format_result(r.text, str(r.format), raw_bytes=r.bytes)
        except ImportError:
            pass

        # 2. Try pyzbar fallback
        try:
            from pyzbar import pyzbar
            for var in variants:
                barcodes = pyzbar.decode(var)
                if barcodes:
                    b = barcodes[0]
                    return cls._format_result(b.data.decode("utf-8", errors="ignore"), b.type)
        except ImportError:
            pass

        # 3. Try pylibdmtx fallback for DataMatrix
        try:
            from pylibdmtx import pylibdmtx
            for var in variants:
                dms = pylibdmtx.decode(var)
                if dms:
                    d = dms[0]
                    return cls._format_result(d.data.decode("utf-8", errors="ignore"), "DataMatrix")
        except ImportError:
            pass

        return None

    @classmethod
    def _format_result(cls, text: str, symbology: str, raw_bytes: bytes | None = None) -> Dict[str, Any]:
        text_clean = text.strip()

        # Check for GS1 Digital Link URL
        if text_clean.startswith("http://") or text_clean.startswith("https://"):
            dl = parse_digital_link_url(text_clean)
            return {
                "raw_text": text_clean,
                "symbology": "GS1_DIGITAL_LINK",
                "parsed": dl,
                "gtin": dl.get("gtin"),
                "batch": dl.get("batch"),
                "expiry": dl.get("expiry"),
            }

        # Check for Bracketed GS1
        if "(" in text_clean and ")" in text_clean:
            parsed = GS1PayloadParser.parse_bracketed_string(text_clean)
            return {
                "raw_text": text_clean,
                "symbology": symbology,
                "parsed": parsed,
                "gtin": parsed.get("gtin"),
                "batch": parsed.get("batch"),
                "expiry": parsed.get("expiry"),
            }

        # Check for Linear GTIN/EAN/UPC
        digits = "".join(c for c in text_clean if c.isdigit())
        if len(digits) in (8, 12, 13, 14) and validate_gtin_check_digit(digits):
            return {
                "raw_text": text_clean,
                "symbology": symbology,
                "gtin": normalize_to_gtin14(digits),
                "check_digit_valid": True,
            }

        return {
            "raw_text": text_clean,
            "symbology": symbology,
            "gtin": None,
            "parsed": None,
        }
