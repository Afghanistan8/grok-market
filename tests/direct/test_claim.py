"""Payout math and claim safety."""

import pytest

from conftest import (
    GEN,
    assert_reverts,
    fail_transfers,
    mock_agree,
    mock_crypto,
    record_transfers,
    warp,
    window,
)

DAY_STR = "2026-03-10"
WIN_START, WIN_END = window(DAY_STR)


def wallet(address):
    return "0x" + bytes(address).hex()


def stake(market, vm, who, market_id, side, amount):
    vm.sender = who
    vm.value = amount
    try:
        market.take_position(market_id, side)
    finally:
        vm.value = 0


def build(market, vm, accounts, stakes, kind="A", asset="BTC"):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market(kind, "CRYPTO", asset if kind == "A" else "", DAY_STR)
    for name, side, amount in stakes:
        stake(market, vm, accounts[name], market_id, side, amount)
    return market_id


def settle_up(market, vm, market_id, asset="BTC"):
    mock_agree(vm, "CRYPTO", DAY_STR, {asset: ("100.0", "110.0")})
    warp(vm, WIN_END + 60)
    return market.resolve_market(market_id)


# ---------------------------------------------------------------------------
# Directional payouts
# ---------------------------------------------------------------------------


def test_the_winning_side_splits_the_whole_pool(market, vm, accounts):
    market_id = build(
        market,
        vm,
        accounts,
        [("bob", "UP", 2 * GEN), ("carol", "UP", 3 * GEN), ("dave", "DOWN", 6 * GEN)],
    )
    assert settle_up(market, vm, market_id) == "UP"

    # Pool is 11 GEN, winning side holds 5 GEN.
    assert market.get_claimable(market_id, wallet(accounts["bob"]))["claimable"] == str(
        2 * 11 * GEN // 5
    )
    assert market.get_claimable(market_id, wallet(accounts["carol"]))["claimable"] == str(
        3 * 11 * GEN // 5
    )
    assert market.get_claimable(market_id, wallet(accounts["dave"]))["claimable"] == "0"


def test_payouts_never_exceed_the_pool(market, vm, accounts):
    market_id = build(
        market,
        vm,
        accounts,
        [("bob", "UP", 2 * GEN + 1), ("carol", "UP", 3 * GEN), ("dave", "DOWN", 2 * GEN)],
    )
    settle_up(market, vm, market_id)

    total = int(market.get_market(market_id)["total_pool"])
    paid = sum(
        int(market.get_claimable(market_id, wallet(accounts[name]))["claimable"])
        for name in ("bob", "carol", "dave")
    )
    assert paid <= total
    # Floor division may strand a few wei of dust in the contract.
    assert total - paid < 2


def test_the_losing_side_is_paid_nothing(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 2 * GEN)])
    settle_up(market, vm, market_id)
    claim = market.get_claimable(market_id, wallet(accounts["carol"]))
    assert claim["claimable"] == "0"
    assert claim["reason"] == "lost"


def test_a_sole_winner_takes_everything(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 6 * GEN)])
    settle_up(market, vm, market_id)
    assert market.get_claimable(market_id, wallet(accounts["bob"]))["claimable"] == str(8 * GEN)


def test_nobody_on_the_winning_side_refunds_everyone(market, vm, accounts):
    """An UP result with an empty UP pool cannot pay anyone, so stakes go back."""
    market_id = build(market, vm, accounts, [("bob", "DOWN", 2 * GEN), ("carol", "DOWN", 3 * GEN)])
    assert settle_up(market, vm, market_id) == "UP"

    m = market.get_market(market_id)
    assert m["state"] == "SETTLED"
    assert m["result"] == "UP"
    assert m["refund_all"] is True
    assert market.get_claimable(market_id, wallet(accounts["bob"]))["claimable"] == str(2 * GEN)
    assert market.get_claimable(market_id, wallet(accounts["carol"]))["claimable"] == str(3 * GEN)


# ---------------------------------------------------------------------------
# Refund paths
# ---------------------------------------------------------------------------


def test_inconclusive_refunds_every_stake(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    mock_crypto(vm, "BTC", DAY_STR, "100.0", "110.0", "100.0", "90.0")
    warp(vm, WIN_END + 60)
    assert market.resolve_market(market_id) == "INCONCLUSIVE"

    for name, amount in (("bob", 2 * GEN), ("carol", 4 * GEN)):
        claim = market.get_claimable(market_id, wallet(accounts[name]))
        assert claim["claimable"] == str(amount)
        assert claim["reason"] == "refund"


def test_terminal_refund_stores_zeros_and_never_fetches(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    vm.clear_mocks()  # no source is reachable at all
    warp(vm, WIN_END + 5 * 86400)
    assert market.resolve_market(market_id) == "INCONCLUSIVE"

    evidence = market.get_settlement_evidence(market_id)
    assert evidence["terminal_refund"] is True
    assert evidence["rows"] == []
    assert evidence["payload"] == ""
    assert evidence["a_verdict"] == ""
    assert evidence["b_verdict"] == ""
    assert evidence["final_result"] == "INCONCLUSIVE"

    m = market.get_market(market_id)
    assert m["refund_all"] is True
    assert market.get_claimable(market_id, wallet(accounts["bob"]))["claimable"] == str(2 * GEN)


def test_terminal_refund_is_not_available_early(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN)])
    vm.clear_mocks()
    warp(vm, WIN_END + 5 * 86400 - 1)
    with pytest.raises(Exception):
        market.resolve_market(market_id)
    assert market.get_market(market_id)["state"] == "UNRESOLVED"


# ---------------------------------------------------------------------------
# Claim mechanics
# ---------------------------------------------------------------------------


def test_claim_transfers_the_payout(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    settle_up(market, vm, market_id)

    sent = record_transfers(vm)
    vm.sender = accounts["bob"]
    paid = market.claim(market_id)

    assert int(paid) == 6 * GEN
    assert len(sent) == 1
    assert sent[0]["value"] == 6 * GEN
    assert sent[0]["address"].as_bytes == bytes(accounts["bob"])
    assert market.get_market(market_id)["paid_out"] == str(6 * GEN)


def test_a_losing_claim_transfers_nothing(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    settle_up(market, vm, market_id)

    sent = record_transfers(vm)
    vm.sender = accounts["carol"]
    assert int(market.claim(market_id)) == 0
    assert sent == []
    assert market.get_position(market_id, wallet(accounts["carol"]))["claimed"] is True


def test_claiming_twice_is_rejected(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    settle_up(market, vm, market_id)
    vm.sender = accounts["bob"]
    market.claim(market_id)
    with pytest.raises(Exception) as excinfo:
        market.claim(market_id)
    assert_reverts(excinfo, "EXPECTED:", "already claimed")


def test_only_the_owner_can_claim(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    settle_up(market, vm, market_id)
    vm.sender = accounts["dave"]  # holds no position
    with pytest.raises(Exception) as excinfo:
        market.claim(market_id)
    assert_reverts(excinfo, "EXPECTED:", "no position")


def test_claiming_before_resolution_is_rejected(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN)])
    vm.sender = accounts["bob"]
    with pytest.raises(Exception) as excinfo:
        market.claim(market_id)
    assert_reverts(excinfo, "EXPECTED:", "not resolved")


def test_a_failed_transfer_leaves_the_position_claimable(market, vm, accounts):
    """Value moves before the flag flips, so a rejected send rolls everything back."""
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    settle_up(market, vm, market_id)

    fail_transfers(vm)
    vm.sender = accounts["bob"]
    with pytest.raises(Exception):
        market.claim(market_id)

    assert market.get_position(market_id, wallet(accounts["bob"]))["claimed"] is False
    assert market.get_claimable(market_id, wallet(accounts["bob"]))["claimable"] == str(6 * GEN)
    assert market.get_market(market_id)["paid_out"] == "0"

    # Once the recipient accepts again, the same claim succeeds.
    vm._gl_call_hook = None
    sent = record_transfers(vm)
    assert int(market.claim(market_id)) == 6 * GEN
    assert sent[0]["value"] == 6 * GEN


def test_claim_writes_an_activity_record(market, vm, accounts):
    market_id = build(market, vm, accounts, [("bob", "UP", 2 * GEN), ("carol", "DOWN", 4 * GEN)])
    settle_up(market, vm, market_id)
    vm.sender = accounts["bob"]
    market.claim(market_id)
    latest = market.get_activity(0, 10)["items"][0]
    assert latest["kind"] == "CLAIM"
    assert latest["amount"] == str(6 * GEN)


# ---------------------------------------------------------------------------
# Kind B payouts
# ---------------------------------------------------------------------------


def test_kind_b_winner_takes_the_pool(market, vm, accounts):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("B", "CRYPTO", "", DAY_STR)
    stake(market, vm, accounts["bob"], market_id, "ETH", 2 * GEN)
    stake(market, vm, accounts["carol"], market_id, "BTC", 3 * GEN)
    stake(market, vm, accounts["dave"], market_id, "ETH", 2 * GEN)

    for symbol, close in (("BTC", "101"), ("ETH", "105"), ("SOL", "99"), ("XRP", "102")):
        mock_crypto(vm, symbol, DAY_STR, "100.0", close, "100.0", close)
    warp(vm, WIN_END + 60)
    assert market.resolve_market(market_id) == "ETH"

    # ETH pool is 4 GEN out of a 7 GEN book.
    assert market.get_claimable(market_id, wallet(accounts["bob"]))["claimable"] == str(
        2 * 7 * GEN // 4
    )
    assert market.get_claimable(market_id, wallet(accounts["dave"]))["claimable"] == str(
        2 * 7 * GEN // 4
    )
    assert market.get_claimable(market_id, wallet(accounts["carol"]))["claimable"] == "0"


def test_kind_b_with_no_backers_on_the_winner_refunds(market, vm, accounts):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("B", "CRYPTO", "", DAY_STR)
    stake(market, vm, accounts["bob"], market_id, "BTC", 2 * GEN)

    for symbol, close in (("BTC", "101"), ("ETH", "105"), ("SOL", "99"), ("XRP", "102")):
        mock_crypto(vm, symbol, DAY_STR, "100.0", close, "100.0", close)
    warp(vm, WIN_END + 60)
    assert market.resolve_market(market_id) == "ETH"
    assert market.get_claimable(market_id, wallet(accounts["bob"]))["claimable"] == str(2 * GEN)
