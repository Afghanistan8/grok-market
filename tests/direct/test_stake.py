"""take_position: stake bounds, top ups and side locking."""

import pytest

from conftest import GEN, assert_reverts, mock_agree, warp, window

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


def wallet(address):
    return "0x" + bytes(address).hex()


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", [0, 1, GEN, 2 * GEN - 1])
def test_first_stake_below_two_gen_is_rejected(open_a, vm, accounts, amount):
    market, market_id = open_a
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", amount)
    assert_reverts(excinfo, "EXPECTED:", "at least 2 GEN")


@pytest.mark.parametrize("amount", [6 * GEN + 1, 7 * GEN, 100 * GEN])
def test_first_stake_above_six_gen_is_rejected(open_a, vm, accounts, amount):
    market, market_id = open_a
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", amount)
    assert_reverts(excinfo, "EXPECTED:", "exceed 6 GEN")


@pytest.mark.parametrize("amount", [2 * GEN, 3 * GEN, 6 * GEN])
def test_stakes_inside_the_band_are_accepted(open_a, vm, accounts, amount):
    market, market_id = open_a
    total = stake(market, vm, accounts["bob"], market_id, "UP", amount)
    assert int(total) == amount
    assert market.get_market(market_id)["pools"]["UP"] == str(amount)


def test_the_exact_boundaries_are_inclusive(open_a, vm, accounts):
    market, market_id = open_a
    assert int(stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)) == 2 * GEN
    assert int(stake(market, vm, accounts["carol"], market_id, "DOWN", 6 * GEN)) == 6 * GEN


# ---------------------------------------------------------------------------
# Top ups
# ---------------------------------------------------------------------------


def test_a_top_up_adds_to_the_same_side(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    total = stake(market, vm, accounts["bob"], market_id, "UP", GEN)
    assert int(total) == 3 * GEN
    assert market.get_position(market_id, wallet(accounts["bob"]))["stake"] == str(3 * GEN)
    assert market.get_market(market_id)["pools"]["UP"] == str(3 * GEN)


def test_a_small_top_up_is_allowed_once_the_minimum_is_met(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    total = stake(market, vm, accounts["bob"], market_id, "UP", 1)
    assert int(total) == 2 * GEN + 1


def test_a_top_up_past_six_gen_is_rejected(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 5 * GEN)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:", "exceed 6 GEN")
    # The rejected top up left nothing behind.
    assert market.get_position(market_id, wallet(accounts["bob"]))["stake"] == str(5 * GEN)
    assert market.get_market(market_id)["pools"]["UP"] == str(5 * GEN)


def test_a_top_up_reaching_exactly_six_gen_is_allowed(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 5 * GEN)
    assert int(stake(market, vm, accounts["bob"], market_id, "UP", GEN)) == 6 * GEN


def test_a_zero_value_top_up_is_rejected(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", 0)
    assert_reverts(excinfo, "EXPECTED:", "must send value")


# ---------------------------------------------------------------------------
# Sides
# ---------------------------------------------------------------------------


def test_switching_sides_is_rejected(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "DOWN", 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:", "cannot switch sides")
    assert market.get_position(market_id, wallet(accounts["bob"]))["side"] == "UP"


@pytest.mark.parametrize("side", ["", "up", "BTC", "MAYBE", "UPP"])
def test_kind_a_only_accepts_up_or_down(open_a, vm, accounts, side):
    market, market_id = open_a
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, side, 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:", "UP or DOWN")


@pytest.mark.parametrize("side", ["UP", "DOWN", "", "AAPL", "btc"])
def test_kind_b_only_accepts_catalog_assets(open_b, vm, accounts, side):
    market, market_id = open_b
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, side, 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:", "asset in this category")


@pytest.mark.parametrize("side", ["BTC", "ETH", "SOL", "XRP"])
def test_kind_b_accepts_every_catalog_asset(open_b, vm, accounts, side):
    market, market_id = open_b
    stake(market, vm, accounts["bob"], market_id, side, 2 * GEN)
    assert market.get_market(market_id)["pools"][side] == str(2 * GEN)


# ---------------------------------------------------------------------------
# Phase gating
# ---------------------------------------------------------------------------


def test_staking_after_the_cutoff_is_rejected(open_a, vm, accounts):
    market, market_id = open_a
    warp(vm, WIN_START + 1)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:", "closed for new positions")


def test_staking_at_the_exact_cutoff_is_rejected(open_a, vm, accounts):
    market, market_id = open_a
    warp(vm, WIN_START)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:")


def test_staking_one_second_before_the_cutoff_is_allowed(open_a, vm, accounts):
    market, market_id = open_a
    warp(vm, WIN_START - 1)
    assert int(stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)) == 2 * GEN


def test_staking_on_a_resolved_market_is_rejected(open_a, vm, accounts):
    market, market_id = open_a
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("100.0", "110.0")})
    warp(vm, WIN_END + 60)
    market.resolve_market(market_id)
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["carol"], market_id, "UP", 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:")


def test_staking_on_an_unknown_market_is_rejected(market, vm, accounts):
    with pytest.raises(Exception) as excinfo:
        stake(market, vm, accounts["bob"], 999, "UP", 2 * GEN)
    assert_reverts(excinfo, "EXPECTED:", "unknown market")


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
