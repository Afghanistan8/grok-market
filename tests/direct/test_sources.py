"""Source readers: HTTP classification and window reconstruction."""

import pytest

from conftest import (
    HOUR,
    assert_reverts,
    binance_body,
    binance_simple,
    coingecko_body,
    coingecko_simple,
    day_index,
    day_string,
    day_string_us,
    nasdaq_body,
    scaled,
    stockanalysis_body,
    window,
)

DAY_STR = "2026-03-10"
WIN_START, WIN_END = window(DAY_STR)
IDX = day_index(DAY_STR)


# ---------------------------------------------------------------------------
# HTTP classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 408, 425])
def test_retryable_statuses_are_transient(gm, status):
    with pytest.raises(Exception) as excinfo:
        gm.classify_response(status, b"{}")
    assert_reverts(excinfo, "TRANSIENT:")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 451])
def test_permanent_statuses_are_external(gm, status):
    with pytest.raises(Exception) as excinfo:
        gm.classify_response(status, b"{}")
    assert_reverts(excinfo, "EXTERNAL:")


def test_empty_body_is_transient(gm):
    with pytest.raises(Exception) as excinfo:
        gm.classify_response(200, b"")
    assert_reverts(excinfo, "TRANSIENT:", "empty body")
    with pytest.raises(Exception) as excinfo:
        gm.classify_response(200, None)
    assert_reverts(excinfo, "TRANSIENT:")


def test_oversized_body_is_external(gm):
    oversized = b"x" * (gm.MAX_SOURCE_BYTES + 1)
    with pytest.raises(Exception) as excinfo:
        gm.classify_response(200, oversized)
    assert_reverts(excinfo, "EXTERNAL:", "exceeds")


def test_body_at_the_size_limit_is_accepted(gm):
    body = b"x" * gm.MAX_SOURCE_BYTES
    assert gm.classify_response(200, body) == "x" * gm.MAX_SOURCE_BYTES


def test_non_utf8_body_is_external(gm):
    with pytest.raises(Exception) as excinfo:
        gm.classify_response(200, b"\xff\xfe\x00bad")
    assert_reverts(excinfo, "EXTERNAL:")


@pytest.mark.parametrize(
    "reader",
    ["coingecko_window", "binance_window", "stockanalysis_day", "nasdaq_day"],
)
def test_malformed_json_is_external(gm, reader):
    fn = getattr(gm, reader)
    args = (WIN_START, WIN_END) if "window" in reader else (IDX,)
    with pytest.raises(Exception) as excinfo:
        fn("not json at all", *args)
    assert_reverts(excinfo, "EXTERNAL:")


# ---------------------------------------------------------------------------
# CoinGecko
# ---------------------------------------------------------------------------


def test_coingecko_takes_first_and_last_in_window_sample(gm):
    hourly = ["100.0"] + ["555.0"] * 22 + ["110.0"]
    body = coingecko_body(WIN_START, hourly)
    assert gm.coingecko_window(body, WIN_START, WIN_END) == (scaled("100.0"), scaled("110.0"))


def test_coingecko_ignores_samples_outside_the_window(gm):
    """The request pads by an hour each side; padding must not become open/close."""
    entries = []
    entries.append("[%d,%s]" % ((WIN_START - HOUR) * 1000, "1.0"))  # before
    for i in range(24):
        entries.append("[%d,%s]" % ((WIN_START + i * HOUR) * 1000, "100.0" if i == 0 else "110.0"))
    entries.append("[%d,%s]" % (WIN_END * 1000, "999.0"))  # at the exclusive end
    entries.append("[%d,%s]" % ((WIN_END + HOUR) * 1000, "999.0"))  # after
    body = '{"prices":[' + ",".join(entries) + "]}"
    assert gm.coingecko_window(body, WIN_START, WIN_END) == (scaled("100.0"), scaled("110.0"))


def test_coingecko_is_order_independent(gm):
    """Open and close are chosen by timestamp, not by array position."""
    hourly = ["100.0"] + ["555.0"] * 22 + ["110.0"]
    forward = coingecko_body(WIN_START, hourly)
    import json

    reversed_items = list(reversed(json.loads(forward)["prices"]))
    body = '{"prices":[' + ",".join("[%d,%s]" % (t, p) for t, p in reversed_items) + "]}"
    assert gm.coingecko_window(body, WIN_START, WIN_END) == gm.coingecko_window(
        forward, WIN_START, WIN_END
    )


def test_coingecko_missing_opening_hour_is_external(gm):
    # First sample lands three hours into the day.
    entries = [
        "[%d,%s]" % ((WIN_START + (i + 3) * HOUR) * 1000, "100.0") for i in range(20)
    ]
    body = '{"prices":[' + ",".join(entries) + "]}"
    with pytest.raises(Exception) as excinfo:
        gm.coingecko_window(body, WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:", "opening hour")


def test_coingecko_missing_closing_hours_is_external(gm):
    entries = ["[%d,%s]" % ((WIN_START + i * HOUR) * 1000, "100.0") for i in range(10)]
    body = '{"prices":[' + ",".join(entries) + "]}"
    with pytest.raises(Exception) as excinfo:
        gm.coingecko_window(body, WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:", "closing hour")


def test_coingecko_no_samples_in_window_is_external(gm):
    body = '{"prices":[[%d,1.0]]}' % ((WIN_START - 10 * HOUR) * 1000)
    with pytest.raises(Exception) as excinfo:
        gm.coingecko_window(body, WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:")


def test_coingecko_empty_prices_is_external(gm):
    with pytest.raises(Exception) as excinfo:
        gm.coingecko_window('{"prices":[]}', WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:", "no prices")


def test_coingecko_rejects_a_non_positive_price(gm):
    hourly = ["0"] + ["1.0"] * 22 + ["110.0"]
    with pytest.raises(Exception) as excinfo:
        gm.coingecko_window(coingecko_body(WIN_START, hourly), WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:")


# ---------------------------------------------------------------------------
# Binance
# ---------------------------------------------------------------------------


def test_binance_uses_first_open_and_last_close(gm):
    body = binance_simple(WIN_START, "100.0", "110.0")
    assert gm.binance_window(body, WIN_START, WIN_END) == (scaled("100.0"), scaled("110.0"))


def test_binance_requires_exactly_24_klines(gm):
    short = binance_body(WIN_START, [("1.0", "1.0")] * 23)
    with pytest.raises(Exception) as excinfo:
        gm.binance_window(short, WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:", "23 of 24")


def test_binance_rejects_a_window_that_starts_late(gm):
    body = binance_body(WIN_START + HOUR, [("1.0", "1.0")] * 24)
    with pytest.raises(Exception) as excinfo:
        gm.binance_window(body, WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:", "does not start")


def test_binance_daily_bars_would_not_align_to_gmt_plus_one(gm):
    """A UTC-aligned day is one hour off, which the start check catches."""
    utc_day_start = WIN_START + HOUR
    body = binance_body(utc_day_start, [("1.0", "1.0")] * 24)
    with pytest.raises(Exception) as excinfo:
        gm.binance_window(body, WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:")


def test_binance_rejects_non_positive_prices(gm):
    body = binance_body(WIN_START, [("0", "1.0")] + [("1.0", "1.0")] * 23)
    with pytest.raises(Exception) as excinfo:
        gm.binance_window(body, WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:")


def test_binance_payload_must_be_a_list(gm):
    with pytest.raises(Exception) as excinfo:
        gm.binance_window('{"klines":[]}', WIN_START, WIN_END)
    assert_reverts(excinfo, "EXTERNAL:", "not a list")


# ---------------------------------------------------------------------------
# Stock feeds
# ---------------------------------------------------------------------------


def test_stockanalysis_selects_the_target_day(gm):
    body = stockanalysis_body(
        [
            (day_string(IDX + 1), "1.0", "2.0"),
            (day_string(IDX), "100.0", "110.0"),
            (day_string(IDX - 1), "3.0", "4.0"),
        ]
    )
    assert gm.stockanalysis_day(body, IDX) == (scaled("100.0"), scaled("110.0"))


def test_stockanalysis_missing_session_is_external(gm):
    body = stockanalysis_body([(day_string(IDX - 3), "1.0", "2.0")])
    with pytest.raises(Exception) as excinfo:
        gm.stockanalysis_day(body, IDX)
    assert_reverts(excinfo, "EXTERNAL:", "no session dated")


def test_nasdaq_selects_the_target_day_and_strips_money_formatting(gm):
    body = nasdaq_body(
        [
            (day_string_us(IDX + 1), "1.0", "2.0"),
            (day_string_us(IDX), "1,100.50", "1,210.25"),
        ]
    )
    assert gm.nasdaq_day(body, IDX) == (scaled("1100.50"), scaled("1210.25"))


def test_nasdaq_missing_session_is_external(gm):
    body = nasdaq_body([(day_string_us(IDX - 3), "1.0", "2.0")])
    with pytest.raises(Exception) as excinfo:
        gm.nasdaq_day(body, IDX)
    assert_reverts(excinfo, "EXTERNAL:", "no session dated")


def test_nasdaq_error_envelope_is_external(gm):
    with pytest.raises(Exception) as excinfo:
        gm.nasdaq_day('{"data":null,"message":null,"status":{"rCode":400}}', IDX)
    assert_reverts(excinfo, "EXTERNAL:", "no data")


def test_a_weekend_looks_the_same_to_both_stock_feeds(gm):
    """Neither feed invents an overnight print for a non trading day."""
    saturday = day_index("2026-03-14")
    sa = stockanalysis_body([(day_string(saturday - 1), "1.0", "2.0")])
    nq = nasdaq_body([(day_string_us(saturday - 1), "1.0", "2.0")])
    for reader, body in ((gm.stockanalysis_day, sa), (gm.nasdaq_day, nq)):
        with pytest.raises(Exception) as excinfo:
            reader(body, saturday)
        assert_reverts(excinfo, "EXTERNAL:", "no session dated")


# ---------------------------------------------------------------------------
# Byte-different payloads must normalise to identical numbers
# ---------------------------------------------------------------------------


def test_coingecko_formatting_differences_do_not_change_the_result(gm):
    tight = coingecko_simple(WIN_START, "100.0", "110.0")
    padded = coingecko_simple(WIN_START, "100.00000000", "110.000")
    assert tight != padded
    assert gm.coingecko_window(tight, WIN_START, WIN_END) == gm.coingecko_window(
        padded, WIN_START, WIN_END
    )


def test_binance_trailing_zeros_do_not_change_the_result(gm):
    a = binance_simple(WIN_START, "100.00000000", "110.00000000")
    b = binance_simple(WIN_START, "100.0", "110.0")
    assert a != b
    assert gm.binance_window(a, WIN_START, WIN_END) == gm.binance_window(b, WIN_START, WIN_END)


def test_stock_feeds_agree_despite_different_encodings(gm):
    sa = stockanalysis_body([(day_string(IDX), "497.965", "493.78")])
    nq = nasdaq_body([(day_string_us(IDX), "497.965", "493.78")])
    assert gm.stockanalysis_day(sa, IDX) == gm.nasdaq_day(nq, IDX)
