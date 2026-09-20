"""Exact decimal -> 1e8 integer conversion.

Settlement never constructs a float, so this parser is the only path from a
feed's number text to a stored price.
"""

from decimal import Decimal

import pytest

from conftest import assert_reverts


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0", 0),
        ("1", 10**8),
        ("1.0", 10**8),
        ("100.00", 100 * 10**8),
        ("0.00000001", 1),
        ("80494.31000000", 8049431000000),
        ("497.965", 49796500000),
        ("2619.7188", 261971880000),
        ("1.3982", 139820000),
    ],
)
def test_known_values(gm, text, expected):
    assert gm.dec_to_scaled(text) == expected


@pytest.mark.parametrize(
    "text",
    ["0.1", "1.5", "123.456", "80494.31", "0.00000001", "999999.99999999", "1e-8", "2.5E3"],
)
def test_matches_decimal_module(gm, text):
    """Cross check against Python's exact Decimal arithmetic."""
    expected = int(Decimal(text) * Decimal(10) ** 8)
    assert gm.dec_to_scaled(text) == expected


def test_money_strings_from_the_stock_feeds(gm):
    assert gm.dec_to_scaled("$497.965") == 49796500000
    assert gm.dec_to_scaled("$1,234.50") == 123450000000
    assert gm.dec_to_scaled("$1,234,567.89") == 123456789000000


def test_integers_scale_without_a_decimal_point(gm):
    assert gm.dec_to_scaled(100) == 100 * 10**8
    assert gm.dec_to_scaled("100") == 100 * 10**8


def test_scientific_notation(gm):
    assert gm.dec_to_scaled("1e2") == 100 * 10**8
    assert gm.dec_to_scaled("1E2") == 100 * 10**8
    assert gm.dec_to_scaled("1.5e3") == 1500 * 10**8
    assert gm.dec_to_scaled("1e-2") == 10**6
    assert gm.dec_to_scaled("5e-9") == 0  # below the scale, truncates to zero


def test_truncation_is_toward_zero(gm):
    # A ninth decimal digit is dropped, never rounded up.
    assert gm.dec_to_scaled("1.999999999") == 199999999
    assert gm.dec_to_scaled("0.000000019") == 1
    assert gm.dec_to_scaled("-1.999999999") == -199999999


def test_signs(gm):
    assert gm.dec_to_scaled("-1.5") == -150000000
    assert gm.dec_to_scaled("+1.5") == 150000000


def test_leading_and_trailing_whitespace(gm):
    assert gm.dec_to_scaled("  100.00  ") == 100 * 10**8


def test_bare_fraction_and_bare_point(gm):
    assert gm.dec_to_scaled(".5") == 50000000
    assert gm.dec_to_scaled("5.") == 5 * 10**8


@pytest.mark.parametrize(
    "bad", ["", "abc", "1.2.3", "1,2.3.4", "--1", "1e", "1e1.5", "12a", "1.2e+x", "nan", "Infinity"]
)
def test_malformed_numbers_are_external_errors(gm, bad):
    with pytest.raises(Exception) as excinfo:
        gm.dec_to_scaled(bad)
    assert_reverts(excinfo, "EXTERNAL:")


@pytest.mark.parametrize("bad", [None, True, False, [], {}, 1.5])
def test_non_string_non_int_values_are_rejected(gm, bad):
    with pytest.raises(Exception) as excinfo:
        gm.dec_to_scaled(bad)
    assert_reverts(excinfo, "EXTERNAL:")


def test_a_float_never_reaches_the_parser_from_json(gm):
    """json.loads with parse_float=str hands the parser the original text."""
    import json

    raw = '{"p": 0.1}'
    as_float = json.loads(raw)["p"]
    as_text = json.loads(raw, parse_float=str)["p"]
    assert isinstance(as_float, float)
    assert as_text == "0.1"
    # 0.1 is not exactly representable in binary; the text form is exact.
    assert gm.dec_to_scaled(as_text) == 10**7
