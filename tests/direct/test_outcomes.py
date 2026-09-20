"""Per-source verdict math and the two-source combination rule."""

import pytest

from conftest import assert_reverts, scaled


def s(text):
    return scaled(text)


# ---------------------------------------------------------------------------
# Kind A: direction
# ---------------------------------------------------------------------------


def test_a_rising_day_is_up(gm):
    assert gm.direction_of(s("100.0"), s("110.0")) == "UP"


def test_a_falling_day_is_down(gm):
    assert gm.direction_of(s("110.0"), s("100.0")) == "DOWN"


def test_a_flat_day_is_down(gm):
    """There is no third outcome, so an exactly flat close resolves DOWN."""
    assert gm.direction_of(s("100.0"), s("100.0")) == "DOWN"


def test_the_smallest_possible_rise_is_up(gm):
    assert gm.direction_of(100 * 10**8, 100 * 10**8 + 1) == "UP"
    assert gm.direction_of(100 * 10**8, 100 * 10**8 - 1) == "DOWN"


# ---------------------------------------------------------------------------
# Kind B: relative return
# ---------------------------------------------------------------------------


def test_return_in_basis_points(gm):
    assert gm.return_bps(s("100.0"), s("110.0")) == 1000  # +10%
    assert gm.return_bps(s("100.0"), s("90.0")) == -1000
    assert gm.return_bps(s("100.0"), s("100.0")) == 0
    assert gm.return_bps(s("100.0"), s("101.0")) == 100  # +1%


def test_return_is_scale_free(gm):
    """The same percentage move gives the same bps at any price level."""
    assert gm.return_bps(s("1.0"), s("1.1")) == gm.return_bps(s("80000.0"), s("88000.0"))


def test_return_floors_toward_negative_infinity(gm):
    """Integer floor division is deterministic on both signs."""
    assert gm.return_bps(s("3.0"), s("3.0001")) == 0
    assert gm.return_bps(s("3.0"), s("2.9999")) == -1


def test_return_on_a_non_positive_open_is_external(gm):
    with pytest.raises(Exception) as excinfo:
        gm.return_bps(0, s("100.0"))
    assert_reverts(excinfo, "EXTERNAL:")


SYMBOLS = ("BTC", "ETH", "SOL", "XRP")


def test_strictly_greatest_return_wins(gm):
    opens = [s("100"), s("100"), s("100"), s("100")]
    closes = [s("101"), s("105"), s("99"), s("102")]
    assert gm.winner_of(SYMBOLS, opens, closes) == "ETH"


def test_winner_is_about_percentage_not_absolute_price(gm):
    opens = [s("80000"), s("100")]
    closes = [s("80800"), s("102")]  # +1% vs +2%
    assert gm.winner_of(("BTC", "ETH"), opens, closes) == "ETH"


def test_all_negative_returns_still_produce_a_winner(gm):
    opens = [s("100")] * 4
    closes = [s("95"), s("90"), s("99"), s("80")]
    assert gm.winner_of(SYMBOLS, opens, closes) == "SOL"


def test_a_tie_for_first_makes_the_source_tie(gm):
    opens = [s("100"), s("100"), s("100"), s("100")]
    closes = [s("105"), s("105"), s("99"), s("102")]
    assert gm.winner_of(SYMBOLS, opens, closes) == "TIE"


def test_a_tie_below_first_place_does_not_matter(gm):
    opens = [s("100")] * 4
    closes = [s("110"), s("105"), s("105"), s("102")]
    assert gm.winner_of(SYMBOLS, opens, closes) == "BTC"


def test_all_four_tied_is_a_tie(gm):
    opens = [s("100")] * 4
    closes = [s("100")] * 4
    assert gm.winner_of(SYMBOLS, opens, closes) == "TIE"


def test_ties_are_decided_on_bps_not_raw_prices(gm):
    """Different prices, identical percentage move, so the source ties."""
    opens = [s("100"), s("200"), s("50"), s("400")]
    closes = [s("110"), s("220"), s("50"), s("400")]
    assert gm.winner_of(SYMBOLS, opens, closes) == "TIE"


# ---------------------------------------------------------------------------
# Combining two independent sources
# ---------------------------------------------------------------------------


def test_matching_verdicts_settle(gm):
    assert gm.combine("UP", "UP") == "UP"
    assert gm.combine("DOWN", "DOWN") == "DOWN"
    assert gm.combine("BTC", "BTC") == "BTC"


def test_opposing_verdicts_are_inconclusive(gm):
    assert gm.combine("UP", "DOWN") == "INCONCLUSIVE"
    assert gm.combine("DOWN", "UP") == "INCONCLUSIVE"
    assert gm.combine("BTC", "ETH") == "INCONCLUSIVE"


def test_a_tie_on_either_source_can_never_produce_a_winner(gm):
    assert gm.combine("TIE", "BTC") == "INCONCLUSIVE"
    assert gm.combine("BTC", "TIE") == "INCONCLUSIVE"
    assert gm.combine("TIE", "TIE") == "INCONCLUSIVE"


def test_an_empty_verdict_can_never_settle(gm):
    assert gm.combine("", "UP") == "INCONCLUSIVE"
    assert gm.combine("UP", "") == "INCONCLUSIVE"
    assert gm.combine("", "") == "INCONCLUSIVE"


def test_a_single_source_is_never_sufficient(gm):
    """The whole point: one source alone cannot carry an outcome."""
    for verdict in ("UP", "DOWN", "BTC", "ETH", "SOL", "XRP"):
        assert gm.combine(verdict, "") == "INCONCLUSIVE"
        assert gm.combine("", verdict) == "INCONCLUSIVE"
        assert gm.combine(verdict, "INCONCLUSIVE") == "INCONCLUSIVE"
