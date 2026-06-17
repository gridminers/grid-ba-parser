from decimal import Decimal

from app.normalization import normalize_date, normalize_value, parse_german_decimal


def test_parse_german_decimal_with_currency_symbol():
    assert parse_german_decimal("3.012,11 EUR") == Decimal("3012.11")
    assert parse_german_decimal("2,800.00 EUR") == Decimal("2800.00")


def test_normalize_date_common_german_formats():
    assert normalize_date("01/04/2024") == "2024-04-01"
    assert normalize_date("30.04.24") == "2024-04-30"


def test_normalize_value_classifies_identifier_and_currency():
    assert normalize_value("PSP-Element", "2H.02.1224.104.012") == (
        "identifier",
        "2H.02.1224.104.012",
    )
    assert normalize_value("Materialkosten", "3.012,11 EUR") == ("currency", "3012.11")
