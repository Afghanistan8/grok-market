"""take_position: stake bounds, top ups, side locking and refunds.

GEN attached to a call is credited to the contract even when the call reverts
(observed on studionet: a rejected stake's value stayed in the contract with
no position to claim it by). So a rejected stake that carries value must
refund it in the same transaction instead of reverting. Every rejection test
here checks that the exact amount goes back to the sender and nothing else
changes.
"""

import pytest

from conftest import GEN, assert_reverts, mock_agree, record_transfers, warp, window

DAY_STR = "2026-03-10"
WIN_START, WIN_END = window(DAY_STR)


@pytest.fixture
def open_a(market, vm):
    warp(vm, WIN_START - 5 * 86400)
    return market, market.create_market("A", "CRYPTO", "BTC", DAY_STR)


@pytest.fixture
def open_b(market, vm):
    warp(vm, WIN_START - 5 * 86400)
    return market, market.create_market("B", "CRYPTO", "", DAY_STR)


def stake(market, vm, who, market_id, side, amount):
    vm.sender = who
    vm.value = amount
    try:
        return market.take_position(market_id, side)
    finally:
        vm.value = 0


def staked_total(result: str) -> int:
    assert result.startswith("STAKED:"), result
    return int(result.split(":", 1)[1])


def wallet(address):
    return "0x" + bytes(address).hex()


def assert_refunded(market, vm, who, market_id, side, amount, reason):
    """The stake is refunded in full and leaves no trace in the market."""
    before = market.get_market(market_id) if market.get_market(market_id)["found"] else None
    sent = record_transfers(vm)
    result = stake(market, vm, who, market_id, side, amount)
    vm._gl_call_hook = None

    assert result.startswith("REFUNDED:"), result
    assert reason in result, result
    assert len(sent) == 1
    assert sent[0]["value"] == amount
    assert sent[0]["address"].as_bytes == bytes(who)
    if before is not None:
        after = market.get_market(market_id)
        assert after["pools"] == before["pools"]
        assert after["total_pool"] == before["total_pool"]
        assert after["position_count"] == before["position_count"]
    return result


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", [1, GEN, 2 * GEN - 1])
def test_first_stake_below_two_gen_is_refunded(open_a, vm, accounts, amount):
    market, market_id = open_a
    assert_refunded(market, vm, accounts["bob"], market_id, "UP", amount, "at least 2 GEN")
    assert market.get_position(market_id, wallet(accounts["bob"]))["found"] is False


def test_a_zero_value_first_stake_reverts(open_a, vm, accounts):
    """No value attached means nothing to trap, so a plain revert is fine."""
    market, market_id = open_a
    sent = record_transfers(vm)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", 0)
    assert_reverts(excinfo, "EXPECTED:", "at least 2 GEN")
    assert sent == []


@pytest.mark.parametrize("amount", [6 * GEN + 1, 7 * GEN, 100 * GEN])
def test_first_stake_above_six_gen_is_refunded(open_a, vm, accounts, amount):
    market, market_id = open_a
    assert_refunded(market, vm, accounts["bob"], market_id, "UP", amount, "exceed 6 GEN")


@pytest.mark.parametrize("amount", [2 * GEN, 3 * GEN, 6 * GEN])
def test_stakes_inside_the_band_are_accepted(open_a, vm, accounts, amount):
    market, market_id = open_a
    sent = record_transfers(vm)
    result = stake(market, vm, accounts["bob"], market_id, "UP", amount)
    assert staked_total(result) == amount
    assert sent == []  # an accepted stake never sends anything back
    assert market.get_market(market_id)["pools"]["UP"] == str(amount)


def test_the_exact_boundaries_are_inclusive(open_a, vm, accounts):
    market, market_id = open_a
    assert staked_total(stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)) == 2 * GEN
    assert staked_total(stake(market, vm, accounts["carol"], market_id, "DOWN", 6 * GEN)) == 6 * GEN


# ---------------------------------------------------------------------------
# Top ups
# ---------------------------------------------------------------------------


def test_a_top_up_adds_to_the_same_side(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    total = staked_total(stake(market, vm, accounts["bob"], market_id, "UP", GEN))
    assert total == 3 * GEN
    assert market.get_position(market_id, wallet(accounts["bob"]))["stake"] == str(3 * GEN)
    assert market.get_market(market_id)["pools"]["UP"] == str(3 * GEN)


def test_a_small_top_up_is_allowed_once_the_minimum_is_met(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    assert staked_total(stake(market, vm, accounts["bob"], market_id, "UP", 1)) == 2 * GEN + 1


def test_a_top_up_past_six_gen_is_refunded(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 5 * GEN)
    assert_refunded(market, vm, accounts["bob"], market_id, "UP", 2 * GEN, "exceed 6 GEN")
    assert market.get_position(market_id, wallet(accounts["bob"]))["stake"] == str(5 * GEN)


def test_a_top_up_reaching_exactly_six_gen_is_allowed(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 5 * GEN)
    assert staked_total(stake(market, vm, accounts["bob"], market_id, "UP", GEN)) == 6 * GEN


def test_a_zero_value_top_up_reverts(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", 0)
    assert_reverts(excinfo, "EXPECTED:", "must send value")


# ---------------------------------------------------------------------------
# Sides
# ---------------------------------------------------------------------------


def test_switching_sides_is_refunded(open_a, vm, accounts):
    """The exact case that trapped 2 GEN on studionet before this fix."""
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    assert_refunded(market, vm, accounts["bob"], market_id, "DOWN", 2 * GEN, "cannot switch sides")
    assert market.get_position(market_id, wallet(accounts["bob"]))["side"] == "UP"


@pytest.mark.parametrize("side", ["", "up", "BTC", "MAYBE", "UPP"])
def test_kind_a_only_accepts_up_or_down(open_a, vm, accounts, side):
    market, market_id = open_a
    assert_refunded(market, vm, accounts["bob"], market_id, side, 2 * GEN, "UP or DOWN")


@pytest.mark.parametrize("side", ["UP", "DOWN", "", "AAPL", "btc"])
def test_kind_b_only_accepts_catalog_assets(open_b, vm, accounts, side):
    market, market_id = open_b
    assert_refunded(market, vm, accounts["bob"], market_id, side, 2 * GEN, "asset in this category")


@pytest.mark.parametrize("side", ["BTC", "ETH", "SOL", "XRP"])
def test_kind_b_accepts_every_catalog_asset(open_b, vm, accounts, side):
    market, market_id = open_b
    stake(market, vm, accounts["bob"], market_id, side, 2 * GEN)
    assert market.get_market(market_id)["pools"][side] == str(2 * GEN)


# ---------------------------------------------------------------------------
# Phase gating
# ---------------------------------------------------------------------------


def test_staking_after_the_cutoff_is_refunded(open_a, vm, accounts):
    """A stake sent just before the cutoff but processed after it gets its GEN back."""
    market, market_id = open_a
    warp(vm, WIN_START + 1)
    assert_refunded(market, vm, accounts["bob"], market_id, "UP", 2 * GEN, "closed for new positions")


def test_staking_at_the_exact_cutoff_is_refunded(open_a, vm, accounts):
    market, market_id = open_a
    warp(vm, WIN_START)
    assert_refunded(market, vm, accounts["bob"], market_id, "UP", 2 * GEN, "closed")


def test_staking_one_second_before_the_cutoff_is_allowed(open_a, vm, accounts):
    market, market_id = open_a
    warp(vm, WIN_START - 1)
    assert staked_total(stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)) == 2 * GEN


def test_staking_on_a_resolved_market_is_refunded(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("100.0", "110.0")})
    warp(vm, WIN_END + 60)
    market.resolve_market(market_id)
    assert_refunded(market, vm, accounts["carol"], market_id, "UP", 2 * GEN, "already resolved")


def test_staking_on_an_unknown_market_is_refunded(market, vm, accounts):
    assert_refunded(market, vm, accounts["bob"], 999, "UP", 2 * GEN, "unknown market")


def test_a_refund_is_recorded_in_the_activity_feed(open_a, vm, accounts):
    market, market_id = open_a
    assert_refunded(market, vm, accounts["bob"], market_id, "DOWN", 7 * GEN, "exceed 6 GEN")
    latest = market.get_activity(0, 10)["items"][0]
    assert latest["kind"] == "REFUND"
    assert latest["amount"] == str(7 * GEN)
    assert "exceed 6 GEN" in latest["detail"]


# ---------------------------------------------------------------------------
# Accounting across wallets
# ---------------------------------------------------------------------------


def test_pools_accumulate_across_wallets(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    stake(market, vm, accounts["carol"], market_id, "UP", 3 * GEN)
    stake(market, vm, accounts["dave"], market_id, "DOWN", 6 * GEN)

    m = market.get_market(market_id)
    assert m["pools"]["UP"] == str(5 * GEN)
    assert m["pools"]["DOWN"] == str(6 * GEN)
    assert m["total_pool"] == str(11 * GEN)
    assert m["position_count"] == 3
    assert m["leading"] == "DOWN"


def test_a_level_book_has_no_leader(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 3 * GEN)
    stake(market, vm, accounts["carol"], market_id, "DOWN", 3 * GEN)
    assert market.get_market(market_id)["leading"] == ""


def test_each_wallet_holds_one_position_per_market(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    assert market.get_market(market_id)["position_count"] == 1


def test_positions_are_listed_for_the_market(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    stake(market, vm, accounts["carol"], market_id, "DOWN", 3 * GEN)
    listing = market.get_market_positions(market_id, 0, 50)
    assert listing["total"] == 2
    owners = {row["owner"] for row in listing["items"]}
    assert owners == {wallet(accounts["bob"]), wallet(accounts["carol"])}


def test_staking_writes_an_activity_record(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    latest = market.get_activity(0, 10)["items"][0]
    assert latest["kind"] == "STAKE"
    assert latest["detail"] == "UP"
    assert latest["amount"] == str(2 * GEN)
