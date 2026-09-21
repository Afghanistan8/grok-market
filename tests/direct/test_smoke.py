"""First pass over the whole lifecycle: create, stake, resolve, claim."""

from conftest import GEN, mock_agree, mock_crypto, scaled, warp, window

DAY_STR = "2026-03-10"


def test_contract_deploys_with_empty_board(market):
    stats = market.get_stats()
    assert stats["markets"] == 0
    assert stats["open_pool"] == "0"


def test_supported_universe_is_the_locked_catalog(market):
    u = market.get_supported_universe()
    cats = {c["id"]: c for c in u["categories"]}
    assert cats["CRYPTO"]["assets"] == ["BTC", "ETH", "SOL", "XRP"]
    assert cats["STOCKS"]["assets"] == ["AAPL", "MSFT", "NVDA", "TSLA"]
    assert cats["CRYPTO"]["source_a"] == "coinbase"
    assert cats["CRYPTO"]["source_b"] == "binance"
    assert cats["STOCKS"]["source_a"] == "stockanalysis"
    assert cats["STOCKS"]["source_b"] == "nasdaq"
    assert u["min_stake"] == str(2 * GEN)
    assert u["max_stake"] == str(6 * GEN)


def test_create_market_sets_the_gmt_plus_one_window(market, vm):
    warp(vm, window(DAY_STR)[0] - 5 * 86400)
    mid = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    m = market.get_market(mid)
    win_start, win_end = window(DAY_STR)
    assert m["found"] is True
    assert m["cutoff_at"] == win_start
    assert m["settles_at"] == win_end
    assert m["terminal_refund_at"] == win_end + 5 * 86400
    assert m["phase"] == "OPEN"
    assert m["target_day"] == DAY_STR


def test_stake_updates_pools_and_position(market, vm, accounts):
    win_start, _ = window(DAY_STR)
    warp(vm, win_start - 5 * 86400)
    mid = market.create_market("A", "CRYPTO", "BTC", DAY_STR)

    vm.sender = accounts["bob"]
    vm.value = 3 * GEN
    market.take_position(mid, "UP")
    vm.value = 0

    m = market.get_market(mid)
    assert m["pools"]["UP"] == str(3 * GEN)
    assert m["pools"]["DOWN"] == "0"
    assert m["total_pool"] == str(3 * GEN)
    assert m["leading"] == "UP"

    pos = market.get_position(mid, "0x" + bytes(accounts["bob"]).hex())
    assert pos["found"] is True
    assert pos["side"] == "UP"
    assert pos["stake"] == str(3 * GEN)


def test_full_kind_a_lifecycle_pays_the_winning_side(market, vm, accounts):
    win_start, win_end = window(DAY_STR)
    warp(vm, win_start - 5 * 86400)
    mid = market.create_market("A", "CRYPTO", "BTC", DAY_STR)

    vm.sender = accounts["bob"]
    vm.value = 3 * GEN
    market.take_position(mid, "UP")

    vm.sender = accounts["carol"]
    vm.value = 2 * GEN
    market.take_position(mid, "DOWN")
    vm.value = 0

    # Both feeds independently see a rising day.
    mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("100.00", "110.00")})
    warp(vm, win_end + 60)
    result = market.resolve_market(mid)
    assert result == "UP"

    m = market.get_market(mid)
    assert m["state"] == "SETTLED"
    assert m["phase"] == "SETTLED_UP"

    ev = market.get_settlement_evidence(mid)
    assert ev["a_verdict"] == "UP"
    assert ev["b_verdict"] == "UP"
    assert ev["final_result"] == "UP"
    assert ev["rows"][0]["a_open"] == scaled("100.00")
    assert ev["rows"][0]["b_close"] == scaled("110.00")

    # Winner takes the whole 5 GEN pool, loser gets nothing.
    bob = "0x" + bytes(accounts["bob"]).hex()
    carol = "0x" + bytes(accounts["carol"]).hex()
    assert market.get_claimable(mid, bob)["claimable"] == str(5 * GEN)
    assert market.get_claimable(mid, carol)["claimable"] == "0"

    vm.sender = accounts["bob"]
    paid = market.claim(mid)
    assert int(paid) == 5 * GEN
    assert market.get_claimable(mid, bob)["reason"] == "already claimed"


def test_disagreeing_sources_refund_everyone(market, vm, accounts):
    win_start, win_end = window(DAY_STR)
    warp(vm, win_start - 5 * 86400)
    mid = market.create_market("A", "CRYPTO", "ETH", DAY_STR)

    vm.sender = accounts["bob"]
    vm.value = 3 * GEN
    market.take_position(mid, "UP")
    vm.value = 0

    # Coinbase sees a rise, Binance sees a fall.
    mock_crypto(vm, "ETH", DAY_STR, "100.00", "110.00", "100.00", "90.00")
    warp(vm, win_end + 60)
    assert market.resolve_market(mid) == "INCONCLUSIVE"

    m = market.get_market(mid)
    assert m["state"] == "INCONCLUSIVE"
    assert m["refund_all"] is True

    bob = "0x" + bytes(accounts["bob"]).hex()
    assert market.get_claimable(mid, bob)["claimable"] == str(3 * GEN)
