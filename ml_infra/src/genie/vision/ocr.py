"""Packaging text extraction and regulatory NAFDAC / batch OCR parsing."""
import re
from typing import Any, Dict, List
import numpy as np


class PackagingOCR:
    """Executes OCR and parses regulatory markings, batch numbers, and expiry dates."""

    NAFDAC_REGEXES = [
        re.compile(r"\b([A-B]\d-\d{4,6})\b", re.IGNORECASE),
        re.compile(r"\b(\d{2}-\d{4,6})\b"),
        re.compile(r"\bNAFDAC\s*(?:REG(?:\.|\s*NO)?[:\s]*)?([A-B0-9-]+)\b", re.IGNORECASE),
    ]

    BATCH_REGEXES = [
        re.compile(r"\b(?:BATCH|LOT|B\.NO|L\.NO)[:\s]*([A-Z0-9]+)\b", re.IGNORECASE),
    ]

    EXPIRY_REGEXES = [
        re.compile(r"\b(?:EXP|EXPIRY|EXP\.DATE)[:\s]*([0-9]{2}[/-][0-9]{2,4})\b", re.IGNORECASE),
        re.compile(r"\b(?:EXP|EXPIRY)[:\s]*([A-Z]{3,4}\.?\s*[0-9]{4})\b", re.IGNORECASE),
    ]

    def extract_text(self, image_np: np.ndarray) -> Dict[str, Any]:
        """Extracts text lines and parses key fields."""
        lines: List[str] = []

        # PaddleOCR or docTR integration
        try:
            from paddleocr import PaddleOCR
            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            results = ocr.ocr(image_np, cls=True)
            if results and results[0]:
                for line in results[0]:
                    text = line[1][0]
                    lines.append(text)
        except Exception:
            pass

        full_text = " ".join(lines)
        nafdac_found = None
        for pattern in self.NAFDAC_REGEXES:
            match = pattern.search(full_text)
            if match:
                nafdac_found = match.group(1).strip()
                break

        batch_found = None
        for pattern in self.BATCH_REGEXES:
            match = pattern.search(full_text)
            if match:
                batch_found = match.group(1).strip()
                break

        expiry_found = None
        for pattern in self.EXPIRY_REGEXES:
            match = pattern.search(full_text)
            if match:
                expiry_found = match.group(1).strip()
                break

        return {
            "raw_text_lines": lines,
            "full_text": full_text,
            "nafdac_number": nafdac_found,
            "batch_number": batch_found,
            "expiry_date": expiry_found,
        }
