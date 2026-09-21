"""Leader and validator convergence over live-looking web data.

``gl.eq_principle.strict_eq`` agrees when the leader's return value and the
validator's return value are equal. Both sides run the same function against
their *own* HTTP responses, so the question that decides consensus is: do two
byte-different bodies normalise to the same payload string?

These tests answer that directly. A VM snapshot is taken before resolution, the
market is resolved against one set of responses, the state is rolled back, and
the same market is resolved again against different bytes. If the two agreed
payloads are identical, ``strict_eq`` agrees on chain.

(``vm.run_validator`` is not used here: direct mode stubs out ``gl.vm.spawn_sandbox``,
which is how ``strict_eq`` re-runs the function inside its validator.)
"""

import pytest

from conftest import (
    GEN,
    HOUR,
    assert_reverts,
    binance_body,
    binance_simple,
    coinbase_body,
    coinbase_simple,
    day_index,
    day_string,
    day_string_us,
    mock_crypto,
    nasdaq_body,
    stockanalysis_body,
    warp,
    window,
)

DAY_STR = "2026-03-10"
WIN_START, WIN_END = window(DAY_STR)
IDX = day_index(DAY_STR)


def open_market(market, vm, accounts, kind="A", category="CRYPTO", asset="BTC"):
    warp(vm, WIN_START - 3 * 86400)
    market_id = market.create_market(kind, category, asset, DAY_STR)
    vm.sender = accounts["bob"]
    vm.value = 3 * GEN
    market.take_position(market_id, "UP" if kind == "A" else asset or "BTC")
    vm.value = 0
    return market_id


def leader_view(vm, open_price="100.0", close_price="110.0"):
    """What the leader fetched: tidy, exactly formatted numbers."""
    vm.clear_mocks()
    vm.mock_web(
        r"products/BTC-USD/candles",
        {"method": "GET", "status": 200, "body": coinbase_simple(WIN_START, open_price, close_price)},
    )
    vm.mock_web(
        r"symbol=BTCUSDT&",
        {"method": "GET", "status": 200, "body": binance_simple(WIN_START, open_price, close_price)},
    )


def validator_view(vm, open_price="100.0", close_price="110.0"):
    """What a validator fetched moments later: different bytes, same numbers.

    Trailing zeros differ, every intermediate candle differs, and Coinbase's
    rows arrive oldest first instead of newest first.
    """
    vm.clear_mocks()
    cb_bars = (
        [(open_price + "000", "7.25")]
        + [("%d.5" % (500 + i), "%d.25" % (600 + i)) for i in range(22)]
        + [("8.5", close_price + "00")]
    )
    bn_bars = (
        [(open_price + "0", "7.25")]
        + [("%d.5" % (300 + i), "%d.25" % (400 + i)) for i in range(22)]
        + [("9.5", close_price + "000")]
    )
    vm.mock_web(
        r"products/BTC-USD/candles",
        {"method": "GET", "status": 200, "body": coinbase_body(WIN_START, cb_bars, newest_first=False)},
    )
    vm.mock_web(
        r"symbol=BTCUSDT&",
        {"method": "GET", "status": 200, "body": binance_body(WIN_START, bn_bars)},
    )


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


def resolve_payload(market, vm, market_id, apply_mocks):
    """Resolve once against one node's view of the web, then roll the state back.

    Returns the payload string that ``strict_eq`` would have compared.
    """
    snapshot = vm.snapshot()
    apply_mocks(vm)
    market.resolve_market(market_id)
    payload = market.get_settlement_evidence(market_id)["payload"]
    vm.revert(snapshot)
    return payload


def test_byte_different_bodies_normalise_to_the_same_payload(market, vm, accounts):
    market_id = open_market(market, vm, accounts)
    warp(vm, WIN_END + 60)

    leader_bytes = coinbase_simple(WIN_START, "100.0", "110.0")
    validator_bytes = coinbase_body(
        WIN_START,
        [("100.0000", "7.25")] + [("%d.5" % (500 + i), "1.0") for i in range(22)] + [("8.5", "110.000")],
        newest_first=False,
    )
    assert leader_bytes != validator_bytes, "the two nodes must see different bytes"

    as_leader = resolve_payload(market, vm, market_id, lambda v: leader_view(v))
    as_validator = resolve_payload(market, vm, market_id, lambda v: validator_view(v))

    assert as_leader == as_validator
    assert as_leader.endswith("|UP")


def test_a_node_that_saw_different_prices_produces_a_different_payload(market, vm, accounts):
    market_id = open_market(market, vm, accounts)
    warp(vm, WIN_END + 60)

    as_leader = resolve_payload(market, vm, market_id, lambda v: leader_view(v))
    as_validator = resolve_payload(
        market, vm, market_id, lambda v: validator_view(v, close_price="115.0")
    )
    assert as_leader != as_validator


def test_rollback_leaves_the_market_resolvable_again(market, vm, accounts):
    """Guards the snapshot helper itself: a reverted resolve must not stick."""
    market_id = open_market(market, vm, accounts)
    warp(vm, WIN_END + 60)
    resolve_payload(market, vm, market_id, lambda v: leader_view(v))
    assert market.get_market(market_id)["state"] == "UNRESOLVED"

    leader_view(vm)
    assert market.resolve_market(market_id) == "UP"


def test_the_agreed_payload_is_exactly_what_gets_stored(market, vm, accounts):
    market_id = open_market(market, vm, accounts)
    leader_view(vm)
    warp(vm, WIN_END + 60)
    market.resolve_market(market_id)

    evidence = market.get_settlement_evidence(market_id)
    fields = evidence["payload"].split("|")
    assert len(fields) == 12
    assert fields[8] == evidence["a_verdict"]
    assert fields[10] == evidence["b_verdict"]
    assert fields[11] == evidence["final_result"]
    # Every displayed price comes back out of the agreed string.
    assert str(evidence["rows"][0]["a_open"]) in fields[7]
    assert str(evidence["rows"][0]["b_close"]) in fields[9]


# ---------------------------------------------------------------------------
# Transient and external failures leave the market retryable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status,prefix", [(429, "TRANSIENT:"), (503, "TRANSIENT:"), (403, "EXTERNAL:")])
def test_a_failing_source_reverts_and_writes_nothing(market, vm, accounts, status, prefix):
    market_id = open_market(market, vm, accounts)
    vm.clear_mocks()
    vm.mock_web(r"products/BTC-USD/candles", {"method": "GET", "status": status, "body": "{}"})
    vm.mock_web(
        r"symbol=BTCUSDT&",
        {"method": "GET", "status": 200, "body": binance_simple(WIN_START, "100.0", "110.0")},
    )
    warp(vm, WIN_END + 60)

    with pytest.raises(Exception) as excinfo:
        market.resolve_market(market_id)
    assert_reverts(excinfo, prefix)

    after = market.get_market(market_id)
    assert after["state"] == "UNRESOLVED"
    assert after["result"] == ""
    assert after["phase"] == "READY_TO_SETTLE"
    assert market.get_settlement_evidence(market_id)["found"] is False


def test_an_incomplete_window_reverts_external_and_stays_retryable(market, vm, accounts):
    market_id = open_market(market, vm, accounts)
    vm.clear_mocks()
    vm.mock_web(
        r"products/BTC-USD/candles",
        {"method": "GET", "status": 200, "body": coinbase_simple(WIN_START, "100.0", "110.0")},
    )
    # Binance is missing the final hour of the day.
    vm.mock_web(
        r"symbol=BTCUSDT&",
        {"method": "GET", "status": 200, "body": binance_body(WIN_START, [("1.0", "1.0")] * 23)},
    )
    warp(vm, WIN_END + 60)

    with pytest.raises(Exception) as excinfo:
        market.resolve_market(market_id)
    assert_reverts(excinfo, "EXTERNAL:", "23 of 24")
    assert market.get_market(market_id)["phase"] == "READY_TO_SETTLE"

    # A later retry, once the feed has caught up, settles normally.
    leader_view(vm)
    assert market.resolve_market(market_id) == "UP"
    assert market.get_market(market_id)["state"] == "SETTLED"


def test_resolution_is_retryable_by_anyone(market, vm, accounts):
    market_id = open_market(market, vm, accounts)
    vm.clear_mocks()
    vm.mock_web(r"products/BTC-USD/candles", {"method": "GET", "status": 429, "body": ""})
    vm.mock_web(r"symbol=BTCUSDT&", {"method": "GET", "status": 429, "body": ""})
    warp(vm, WIN_END + 60)
    with pytest.raises(Exception):
        market.resolve_market(market_id)

    leader_view(vm)
    vm.sender = accounts["dave"]  # a wallet with no position and no privileges
    assert market.resolve_market(market_id) == "UP"


# ---------------------------------------------------------------------------
# Kind B across two sources
# ---------------------------------------------------------------------------


def mock_relative(vm, a_closes, b_closes):
    vm.clear_mocks()
    for symbol, a_close, b_close in zip(("BTC", "ETH", "SOL", "XRP"), a_closes, b_closes):
        mock_crypto(vm, symbol, DAY_STR, "100.0", a_close, "100.0", b_close)


def test_kind_b_settles_when_both_sources_pick_the_same_winner(market, vm, accounts):
    warp(vm, WIN_START - 3 * 86400)
    market_id = market.create_market("B", "CRYPTO", "", DAY_STR)
    vm.sender = accounts["bob"]
    vm.value = 3 * GEN
    market.take_position(market_id, "ETH")
    vm.value = 0

    mock_relative(vm, ["101", "105", "99", "102"], ["101", "106", "98", "103"])
    warp(vm, WIN_END + 60)
    assert market.resolve_market(market_id) == "ETH"

    evidence = market.get_settlement_evidence(market_id)
    assert evidence["a_verdict"] == "ETH"
    assert evidence["b_verdict"] == "ETH"
    assert len(evidence["rows"]) == 4
    assert market.get_claimable(market_id, "0x" + bytes(accounts["bob"]).hex())["claimable"] == str(
        3 * GEN
    )


def test_kind_b_different_winners_refund_everyone(market, vm, accounts):
    warp(vm, WIN_START - 3 * 86400)
    market_id = market.create_market("B", "CRYPTO", "", DAY_STR)
    vm.sender = accounts["bob"]
    vm.value = 3 * GEN
    market.take_position(market_id, "ETH")
    vm.value = 0

    mock_relative(vm, ["101", "105", "99", "102"], ["101", "102", "99", "108"])
    warp(vm, WIN_END + 60)
    assert market.resolve_market(market_id) == "INCONCLUSIVE"
    assert market.get_market(market_id)["refund_all"] is True


def test_kind_b_tie_on_one_source_refunds_everyone(market, vm, accounts):
    warp(vm, WIN_START - 3 * 86400)
    market_id = market.create_market("B", "CRYPTO", "", DAY_STR)
    vm.sender = accounts["bob"]
    vm.value = 3 * GEN
    market.take_position(market_id, "BTC")
    vm.value = 0

    # Coinbase sees BTC and ETH dead level at the top.
    mock_relative(vm, ["105", "105", "99", "102"], ["106", "105", "99", "102"])
    warp(vm, WIN_END + 60)
    assert market.resolve_market(market_id) == "INCONCLUSIVE"
    assert market.get_settlement_evidence(market_id)["a_verdict"] == "TIE"


# ---------------------------------------------------------------------------
# Stocks
# ---------------------------------------------------------------------------


def test_stock_market_settles_from_two_independent_daily_feeds(market, vm, accounts):
    warp(vm, WIN_START - 3 * 86400)
    market_id = market.create_market("A", "STOCKS", "MSFT", DAY_STR)
    vm.sender = accounts["bob"]
    vm.value = 2 * GEN
    market.take_position(market_id, "DOWN")
    vm.value = 0

    vm.clear_mocks()
    vm.mock_web(
        r"/s/msft/history",
        {
            "method": "GET",
            "status": 200,
            "body": stockanalysis_body([(day_string(IDX), "497.965", "493.78")]),
        },
    )
    vm.mock_web(
        r"quote/MSFT/historical",
        {
            "method": "GET",
            "status": 200,
            "body": nasdaq_body([(day_string_us(IDX), "497.965", "493.78")]),
        },
    )
    warp(vm, WIN_END + 60)
    assert market.resolve_market(market_id) == "DOWN"


def test_a_closed_session_reverts_external_and_never_invents_a_print(market, vm, accounts):
    warp(vm, WIN_START - 3 * 86400)
    market_id = market.create_market("A", "STOCKS", "AAPL", DAY_STR)
    vm.clear_mocks()
    # Both feeds simply have no row for the target day.
    vm.mock_web(
        r"/s/aapl/history",
        {
            "method": "GET",
            "status": 200,
            "body": stockanalysis_body([(day_string(IDX - 3), "100.0", "101.0")]),
        },
    )
    vm.mock_web(
        r"quote/AAPL/historical",
        {
            "method": "GET",
            "status": 200,
            "body": nasdaq_body([(day_string_us(IDX - 3), "100.0", "101.0")]),
        },
    )
    warp(vm, WIN_END + 60)

    with pytest.raises(Exception) as excinfo:
        market.resolve_market(market_id)
    assert_reverts(excinfo, "EXTERNAL:", "no session dated")
    assert market.get_market(market_id)["state"] == "UNRESOLVED"
