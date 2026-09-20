"""The canonical consensus payload and its post-consensus re-validation.

``parse_agreed`` runs in deterministic code after ``strict_eq`` returns. It is
the last gate before anything is written to storage, so it re-derives every
verdict from the prices in the payload rather than trusting them.
"""

import pytest

from conftest import assert_reverts, day_index, scaled

DAY_STR = "2026-03-10"
IDX = day_index(DAY_STR)
CRYPTO = ("BTC", "ETH", "SOL", "XRP")


def s(text):
    return scaled(text)


def kind_a_payload(gm, a=("100.0", "110.0"), b=("100.0", "110.0"), asset="BTC"):
    return gm.build_payload(
        "A", "CRYPTO", asset, IDX, (asset,), [s(a[0])], [s(a[1])], [s(b[0])], [s(b[1])]
    )


def kind_b_payload(gm, a_closes, b_closes):
    opens = [s("100.0")] * 4
    return gm.build_payload(
        "B",
        "CRYPTO",
        "",
        IDX,
        CRYPTO,
        opens,
        [s(c) for c in a_closes],
        list(opens),
        [s(c) for c in b_closes],
    )


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_payload_has_the_documented_shape(gm):
    payload = kind_a_payload(gm)
    fields = payload.split("|")
    assert len(fields) == gm.PAYLOAD_FIELDS == 12
    assert fields[0] == "v1"
    assert fields[1] == "A"
    assert fields[2] == "CRYPTO"
    assert fields[3] == "BTC"
    assert fields[4] == "coingecko"
    assert fields[5] == "binance"
    assert fields[6] == str(IDX)
    assert fields[7] == "BTC:%d:%d" % (s("100.0"), s("110.0"))
    assert fields[8] == "UP"
    assert fields[10] == "UP"
    assert fields[11] == "UP"


def test_kind_b_payload_carries_every_asset_from_both_sources(gm):
    payload = kind_b_payload(gm, ["101", "105", "99", "102"], ["101", "106", "99", "102"])
    fields = payload.split("|")
    assert fields[1] == "B"
    assert fields[3] == ""
    assert len(fields[7].split(",")) == 4
    assert len(fields[9].split(",")) == 4
    for i, symbol in enumerate(CRYPTO):
        assert fields[7].split(",")[i].startswith(symbol + ":")
        assert fields[9].split(",")[i].startswith(symbol + ":")
    assert fields[11] == "ETH"


def test_payload_contains_every_persisted_field(gm):
    """Nothing is stored that was not inside the agreed string."""
    payload = kind_a_payload(gm)
    agreed = gm.parse_agreed(payload, "A", "CRYPTO", "BTC", IDX)
    for value in (
        agreed["a_verdict"],
        agreed["b_verdict"],
        agreed["final"],
        agreed["source_a"],
        agreed["source_b"],
    ):
        assert str(value) in payload
    assert str(agreed["a_opens"][0]) in payload
    assert str(agreed["b_closes"][0]) in payload


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------


def test_round_trip_kind_a(gm):
    payload = kind_a_payload(gm)
    agreed = gm.parse_agreed(payload, "A", "CRYPTO", "BTC", IDX)
    assert agreed["final"] == "UP"
    assert agreed["a_opens"] == [s("100.0")]
    assert agreed["b_closes"] == [s("110.0")]


def test_round_trip_kind_b(gm):
    payload = kind_b_payload(gm, ["101", "105", "99", "102"], ["101", "105", "99", "102"])
    agreed = gm.parse_agreed(payload, "B", "CRYPTO", "", IDX)
    assert agreed["final"] == "ETH"
    assert len(agreed["a_opens"]) == 4


def test_disagreement_round_trips_as_inconclusive(gm):
    payload = kind_a_payload(gm, a=("100", "110"), b=("100", "90"))
    agreed = gm.parse_agreed(payload, "A", "CRYPTO", "BTC", IDX)
    assert agreed["a_verdict"] == "UP"
    assert agreed["b_verdict"] == "DOWN"
    assert agreed["final"] == "INCONCLUSIVE"


def test_kind_b_different_winners_are_inconclusive(gm):
    payload = kind_b_payload(gm, ["101", "105", "99", "102"], ["101", "102", "99", "108"])
    agreed = gm.parse_agreed(payload, "B", "CRYPTO", "", IDX)
    assert agreed["a_verdict"] == "ETH"
    assert agreed["b_verdict"] == "XRP"
    assert agreed["final"] == "INCONCLUSIVE"


def test_kind_b_tie_on_one_source_is_inconclusive(gm):
    payload = kind_b_payload(gm, ["105", "105", "99", "102"], ["101", "105", "99", "102"])
    agreed = gm.parse_agreed(payload, "B", "CRYPTO", "", IDX)
    assert agreed["a_verdict"] == "TIE"
    assert agreed["final"] == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Binding: the payload must belong to the market being resolved
# ---------------------------------------------------------------------------


def test_payload_from_another_kind_is_rejected(gm):
    payload = kind_a_payload(gm)
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed(payload, "B", "CRYPTO", "", IDX)
    assert_reverts(excinfo, "INVARIANT:", "kind")


def test_payload_from_another_category_is_rejected(gm):
    payload = kind_a_payload(gm)
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed(payload, "A", "STOCKS", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:")


def test_payload_for_another_asset_is_rejected(gm):
    payload = kind_a_payload(gm, asset="BTC")
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed(payload, "A", "CRYPTO", "ETH", IDX)
    assert_reverts(excinfo, "INVARIANT:", "asset")


def test_payload_for_another_day_is_rejected(gm):
    payload = kind_a_payload(gm)
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed(payload, "A", "CRYPTO", "BTC", IDX + 1)
    assert_reverts(excinfo, "INVARIANT:", "day")


def test_swapped_source_names_are_rejected(gm):
    fields = kind_a_payload(gm).split("|")
    fields[4], fields[5] = fields[5], fields[4]
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:", "sources")


def test_unknown_version_is_rejected(gm):
    fields = kind_a_payload(gm).split("|")
    fields[0] = "v2"
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:", "version")


@pytest.mark.parametrize("count", [0, 1, 11, 13, 20])
def test_wrong_field_count_is_rejected(gm, count):
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(["x"] * count), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:", "field count")


# ---------------------------------------------------------------------------
# Tamper resistance: a verdict must follow from its own prices
# ---------------------------------------------------------------------------


def test_source_a_verdict_contradicting_its_prices_is_rejected(gm):
    fields = kind_a_payload(gm).split("|")
    fields[8] = "DOWN"  # prices say UP
    fields[11] = "INCONCLUSIVE"
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:", "source A verdict")


def test_source_b_verdict_contradicting_its_prices_is_rejected(gm):
    fields = kind_a_payload(gm).split("|")
    fields[10] = "DOWN"
    fields[11] = "INCONCLUSIVE"
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:", "source B verdict")


def test_final_contradicting_the_two_verdicts_is_rejected(gm):
    fields = kind_a_payload(gm, a=("100", "110"), b=("100", "90")).split("|")
    assert fields[11] == "INCONCLUSIVE"
    fields[11] = "UP"  # claim a settlement the sources did not support
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:", "final result")


def test_a_forged_single_source_settlement_is_rejected(gm):
    """Blanking one source and keeping a directional final must not pass."""
    fields = kind_a_payload(gm).split("|")
    fields[10] = ""
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:")


def test_missing_series_entry_is_rejected(gm):
    fields = kind_b_payload(gm, ["101"] * 4, ["101"] * 4).split("|")
    fields[7] = ",".join(fields[7].split(",")[:3])
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "B", "CRYPTO", "", IDX)
    assert_reverts(excinfo, "INVARIANT:", "entry count")


def test_series_symbol_outside_the_catalog_is_rejected(gm):
    fields = kind_b_payload(gm, ["101", "105", "99", "102"], ["101", "105", "99", "102"]).split("|")
    entries = fields[7].split(",")
    entries[1] = entries[1].replace("ETH:", "DOGE:")
    fields[7] = ",".join(entries)
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "B", "CRYPTO", "", IDX)
    assert_reverts(excinfo, "INVARIANT:", "symbol")


def test_series_symbols_out_of_catalog_order_are_rejected(gm):
    fields = kind_b_payload(gm, ["101", "105", "99", "102"], ["101", "105", "99", "102"]).split("|")
    entries = fields[7].split(",")
    entries[0], entries[1] = entries[1], entries[0]
    fields[7] = ",".join(entries)
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "B", "CRYPTO", "", IDX)
    assert_reverts(excinfo, "INVARIANT:", "symbol")


@pytest.mark.parametrize("price", ["0", "-5", "12.5", "abc", ""])
def test_non_positive_or_non_integer_prices_are_rejected(gm, price):
    fields = kind_a_payload(gm).split("|")
    fields[7] = "BTC:%s:%d" % (price, s("110.0"))
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:")


def test_malformed_series_entry_is_rejected(gm):
    fields = kind_a_payload(gm).split("|")
    fields[7] = "BTC:100"
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "A", "CRYPTO", "BTC", IDX)
    assert_reverts(excinfo, "INVARIANT:", "malformed")


def test_a_winner_outside_the_catalog_cannot_settle(gm):
    payload = kind_b_payload(gm, ["101", "105", "99", "102"], ["101", "105", "99", "102"])
    fields = payload.split("|")
    fields[8] = "DOGE"
    fields[10] = "DOGE"
    fields[11] = "DOGE"
    with pytest.raises(Exception) as excinfo:
        gm.parse_agreed("|".join(fields), "B", "CRYPTO", "", IDX)
    assert_reverts(excinfo, "INVARIANT:")
