"""Calendar and GMT+1 window math.

Every assertion is cross checked against Python's own ``datetime``, which is a
genuinely independent implementation of the same calendar.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from conftest import DAY, GMT_PLUS_ONE, assert_reverts

EPOCH = date(1970, 1, 1)


def test_leap_years_follow_the_gregorian_rule(gm):
    assert gm._is_leap(2024) is True
    assert gm._is_leap(2026) is False
    assert gm._is_leap(1900) is False  # divisible by 100 but not 400
    assert gm._is_leap(2000) is True  # divisible by 400
    assert gm._is_leap(2100) is False


@pytest.mark.parametrize(
    "day_str",
    [
        "1970-01-01",
        "1999-12-31",
        "2000-01-01",
        "2000-02-29",
        "2024-02-29",
        "2026-03-10",
        "2026-12-31",
        "2027-01-01",
        "2100-02-28",
        "2400-02-29",
    ],
)
def test_day_index_matches_python_datetime(gm, day_str):
    expected = (date.fromisoformat(day_str) - EPOCH).days
    assert gm.parse_day_string(day_str) == expected


@pytest.mark.parametrize(
    "day_str", ["1970-01-01", "2024-02-29", "2026-03-10", "2100-03-01", "2400-02-29"]
)
def test_day_index_round_trips(gm, day_str):
    index = gm.parse_day_string(day_str)
    assert gm.format_day(index) == day_str


def test_us_date_format_for_the_nasdaq_lookup(gm):
    index = gm.parse_day_string("2026-09-18")
    assert gm.format_day_us(index) == "09/18/2026"
    assert gm.format_day_us(gm.parse_day_string("2026-01-05")) == "01/05/2026"


def test_days_in_month_handles_february(gm):
    assert gm._days_in_month(2024, 2) == 29
    assert gm._days_in_month(2026, 2) == 28
    assert gm._days_in_month(2026, 4) == 30
    assert gm._days_in_month(2026, 12) == 31


@pytest.mark.parametrize(
    "bad",
    ["2026-13-01", "2026-02-30", "2026-00-10", "2026-3-10", "20260310", "", "2026-02-29"],
)
def test_bad_dates_are_rejected(gm, bad):
    with pytest.raises(Exception) as excinfo:
        gm.parse_day_string(bad)
    assert_reverts(excinfo, "EXPECTED:")


def test_window_is_the_gmt_plus_one_calendar_day(gm):
    index = gm.parse_day_string("2026-03-10")
    start, end = gm.window_for_day(index)

    # 2026-03-10 00:00 GMT+1 is 2026-03-09 23:00 UTC.
    expected_start = datetime(2026, 3, 9, 23, 0, 0, tzinfo=timezone.utc).timestamp()
    assert start == int(expected_start)
    assert end - start == DAY
    assert end == int(expected_start) + DAY


def test_window_never_shifts_for_daylight_saving(gm):
    """Europe moves its clocks on 2026-03-29. GMT+1 does not."""
    before = gm.window_for_day(gm.parse_day_string("2026-03-28"))
    across = gm.window_for_day(gm.parse_day_string("2026-03-29"))
    after = gm.window_for_day(gm.parse_day_string("2026-03-30"))
    assert across[0] - before[0] == DAY
    assert after[0] - across[0] == DAY
    assert all(w[1] - w[0] == DAY for w in (before, across, after))


def test_consecutive_windows_tile_without_gap_or_overlap(gm):
    index = gm.parse_day_string("2026-02-27")
    for _ in range(6):  # walks across the 2026 February/March boundary
        _, end = gm.window_for_day(index)
        next_start, _ = gm.window_for_day(index + 1)
        assert end == next_start
        index += 1


def test_leap_day_window_is_a_normal_day(gm):
    start, end = gm.window_for_day(gm.parse_day_string("2024-02-29"))
    assert end - start == DAY
    assert gm.format_day(gm.parse_day_string("2024-02-28") + 1) == "2024-02-29"
    assert gm.format_day(gm.parse_day_string("2024-02-29") + 1) == "2024-03-01"
    assert gm.format_day(gm.parse_day_string("2026-02-28") + 1) == "2026-03-01"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-03-10T00:00:00Z", datetime(2026, 3, 10, tzinfo=timezone.utc)),
        ("2026-03-10T12:34:56Z", datetime(2026, 3, 10, 12, 34, 56, tzinfo=timezone.utc)),
        ("2026-03-10 12:34:56Z", datetime(2026, 3, 10, 12, 34, 56, tzinfo=timezone.utc)),
        ("2026-03-10T12:34:56.789Z", datetime(2026, 3, 10, 12, 34, 56, tzinfo=timezone.utc)),
        ("2026-03-10T12:34:56+00:00", datetime(2026, 3, 10, 12, 34, 56, tzinfo=timezone.utc)),
        ("2026-03-10T13:34:56+01:00", datetime(2026, 3, 10, 12, 34, 56, tzinfo=timezone.utc)),
        ("2026-03-10T07:34:56-05:00", datetime(2026, 3, 10, 12, 34, 56, tzinfo=timezone.utc)),
        ("2024-02-29T23:59:59Z", datetime(2024, 2, 29, 23, 59, 59, tzinfo=timezone.utc)),
    ],
)
def test_iso_parsing_matches_datetime(gm, text, expected):
    assert gm.parse_iso_utc(text) == int(expected.timestamp())


@pytest.mark.parametrize(
    "bad", ["2026-03-10", "not-a-datetime-at-all", "2026-03-10X12:34:56Z", "2026-03-10T12:3456Z"]
)
def test_unparseable_datetimes_raise_invariant(gm, bad):
    with pytest.raises(Exception) as excinfo:
        gm.parse_iso_utc(bad)
    assert_reverts(excinfo, "INVARIANT:")


def test_offset_parsing_is_the_inverse_of_the_offset(gm):
    utc = gm.parse_iso_utc("2026-06-01T00:00:00Z")
    plus_one = gm.parse_iso_utc("2026-06-01T01:00:00+01:00")
    minus_one = gm.parse_iso_utc("2026-05-31T23:00:00-01:00")
    assert utc == plus_one == minus_one


def test_gmt_plus_one_offset_constant_is_one_hour(gm):
    assert gm.GMT_PLUS_ONE == GMT_PLUS_ONE == 3600
    assert gm.DAY == DAY == 86400
