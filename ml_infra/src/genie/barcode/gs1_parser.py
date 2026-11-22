"""GS1 Application Identifier (AI) parsing for GS1 DataMatrix and GS1-128."""
import re
from typing import Any, Dict, Optional

from genie.barcode.gtin import normalize_to_gtin14, validate_gtin_check_digit


class GS1PayloadParser:
    """Parses GS1 element strings into typed Application Identifier dictionaries."""

    # Fixed length AIs: AI -> length of value
    FIXED_LENGTH_AIS = {
        "00": 18,  # SSCC
        "01": 14,  # GTIN
        "02": 14,  # Content GTIN
        "11": 6,   # Production date (YYMMDD)
        "12": 6,   # Due date (YYMMDD)
        "13": 6,   # Packaging date (YYMMDD)
        "15": 6,   # Best before date (YYMMDD)
        "17": 6,   # Expiration date (YYMMDD)
        "20": 2,   # Internal variant
    }

    # Variable length AIs: AI -> max length
    VARIABLE_LENGTH_AIS = {
        "10": 20,  # Batch or lot number
        "21": 20,  # Serial number
        "30": 8,   # Count of items
        "37": 8,   # Number of units
        "240": 30, # Additional product ID
    }

    @classmethod
    def parse_bracketed_string(cls, payload: str) -> Dict[str, Any]:
        """Parses bracketed AI strings like (01)06151234567893(17)271231(10)AB1234(21)98765."""
        pattern = re.compile(r"\((\d{2,4})\)([^()]+)")
        matches = pattern.findall(payload)
        result: Dict[str, Any] = {}
        for ai, val in matches:
            result[ai] = val.strip()
        return cls._normalize_parsed_dict(result)

    @classmethod
    def parse_fnc1_string(cls, raw: str) -> Dict[str, Any]:
        """Parses unbracketed GS1 element strings delimited by FNC1 (ASCII 29 / \x1d)."""
        result: Dict[str, Any] = {}
        fnc1 = "\x1d"
        segments = raw.split(fnc1)

        for segment in segments:
            idx = 0
            while idx < len(segment):
                # Try 2-digit AI
                ai2 = segment[idx : idx + 2]
                if ai2 in cls.FIXED_LENGTH_AIS:
                    length = cls.FIXED_LENGTH_AIS[ai2]
                    result[ai2] = segment[idx + 2 : idx + 2 + length]
                    idx += 2 + length
                    continue
                elif ai2 in cls.VARIABLE_LENGTH_AIS:
                    # In FNC1 stream, variable length takes remainder of segment
                    result[ai2] = segment[idx + 2 :]
                    break

                # Try 3-digit AI
                ai3 = segment[idx : idx + 3]
                if ai3 in cls.VARIABLE_LENGTH_AIS:
                    result[ai3] = segment[idx + 3 :]
                    break

                idx += 1

        return cls._normalize_parsed_dict(result)

    @classmethod
    def _normalize_parsed_dict(cls, data: Dict[str, str]) -> Dict[str, Any]:
        gtin = data.get("01")
        expiry = data.get("17")
        batch = data.get("10")
        serial = data.get("21")
        prod_date = data.get("11")

        formatted_expiry = None
        if expiry and len(expiry) == 6:
            yy = int(expiry[0:2])
            mm = expiry[2:4]
            dd = expiry[4:6]
            year = 2000 + yy if yy < 70 else 1900 + yy
            if dd == "00":
                dd = "28"  # End of month placeholder
            formatted_expiry = f"{year}-{mm}-{dd}"

        gtin_valid = validate_gtin_check_digit(gtin) if gtin else False

        return {
            "gtin": normalize_to_gtin14(gtin) if gtin and gtin_valid else gtin,
            "expiry": formatted_expiry,
            "raw_expiry": expiry,
            "batch": batch,
            "serial": serial,
            "production_date": prod_date,
            "raw_ais": data,
            "checks": {
                "gtin_checkdigit": gtin_valid,
                "has_batch": bool(batch),
                "has_expiry": bool(formatted_expiry),
            },
        }
