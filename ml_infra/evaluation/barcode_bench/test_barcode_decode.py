"""Barcode and GS1 evaluation benchmark."""
from genie.barcode.gtin import calculate_gs1_check_digit, validate_gtin_check_digit


def test_gtin_check_digit_benchmark():
    assert validate_gtin_check_digit("06151234567893") is True
    assert validate_gtin_check_digit("06151234567894") is False
