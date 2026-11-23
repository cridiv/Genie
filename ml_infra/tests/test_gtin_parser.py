"""Unit tests for GTIN check digit calculation and normalization."""
try:
    import pytest
except ImportError:
    pytest = None

from genie.barcode.gtin import (
    calculate_gs1_check_digit,
    inspect_gs1_prefix,
    normalize_to_gtin14,
    validate_gtin_check_digit,
)


def test_calculate_gs1_check_digit():
    # Coartem test vector (13-digit body without check digit)
    body = "0615123456789"
    check = calculate_gs1_check_digit(body)
    assert check == 3


def test_validate_gtin_check_digit():
    assert validate_gtin_check_digit("06151234567893") is True
    assert validate_gtin_check_digit("06151234567890") is False
    assert validate_gtin_check_digit("invalid") is False


def test_normalize_to_gtin14():
    # 13-digit EAN normalized to 14 digits
    assert normalize_to_gtin14("6151234567893") == "06151234567893"

    error_raised = False
    try:
        normalize_to_gtin14("1234567890123")
    except ValueError:
        error_raised = True
    assert error_raised is True


def test_inspect_gs1_prefix():
    prefix, hint = inspect_gs1_prefix("06151234567893")
    assert prefix == "615"
    assert hint == "GS1 Nigeria"
