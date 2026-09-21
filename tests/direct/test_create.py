"""create_market: catalogs, windows and uniqueness."""

import pytest

from conftest import assert_reverts, warp, window

DAY_STR = "2026-03-10"
WIN_START, WIN_END = window(DAY_STR)


@pytest.fixture
def before(market, vm):
    warp(vm, WIN_START - 10 * 86400)
    return market


def test_anyone_can_create_a_market(before, vm, accounts):
    vm.sender = accounts["dave"]
    market_id = before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    assert int(market_id) == 1
    assert before.get_market(market_id)["creator"] == "0x" + bytes(accounts["dave"]).hex()


def test_ids_increment(before):
    assert int(before.create_market("A", "CRYPTO", "BTC", DAY_STR)) == 1
    assert int(before.create_market("A", "CRYPTO", "ETH", DAY_STR)) == 2
    assert int(before.create_market("B", "CRYPTO", "", DAY_STR)) == 3


@pytest.mark.parametrize("kind", ["", "C", "a", "AB", "1"])
def test_unknown_kind_is_rejected(before, kind):
    with pytest.raises(Exception) as excinfo:
        before.create_market(kind, "CRYPTO", "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "kind must be")


@pytest.mark.parametrize("category", ["", "FOREX", "crypto", "STOCK"])
def test_unknown_category_is_rejected(before, category):
    with pytest.raises(Exception) as excinfo:
        before.create_market("A", category, "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "category must be")


@pytest.mark.parametrize("asset", ["", "DOGE", "btc", "AAPL"])
def test_asset_must_belong_to_the_category(before, asset):
    with pytest.raises(Exception) as excinfo:
        before.create_market("A", "CRYPTO", asset, DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "not in this category")


def test_stock_asset_cannot_be_used_in_crypto(before):
    with pytest.raises(Exception) as excinfo:
        before.create_market("A", "CRYPTO", "TSLA", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:")
    # ...and the same asset is fine in its own category.
    assert int(before.create_market("A", "STOCKS", "TSLA", DAY_STR)) == 1


def test_kind_b_covers_the_whole_category_so_asset_must_be_empty(before):
    with pytest.raises(Exception) as excinfo:
        before.create_market("B", "CRYPTO", "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "empty asset")
    assert int(before.create_market("B", "CRYPTO", "", DAY_STR)) == 1


def test_all_catalog_assets_are_creatable(before):
    created = 0
    for category, assets in (
        ("CRYPTO", ["BTC", "ETH", "SOL", "XRP"]),
        ("STOCKS", ["AAPL", "MSFT", "NVDA", "TSLA"]),
    ):
        for asset in assets:
            before.create_market("A", category, asset, DAY_STR)
            created += 1
    assert created == 8
    assert before.get_stats()["markets"] == 8


def test_a_day_already_in_progress_is_rejected(market, vm):
    warp(vm, WIN_START + 60)  # the candle is already running
    with pytest.raises(Exception) as excinfo:
        market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "start in the future")


def test_a_past_day_is_rejected(market, vm):
    warp(vm, WIN_END + 86400)
    with pytest.raises(Exception) as excinfo:
        market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "start in the future")


def test_the_exact_cutoff_instant_is_rejected(market, vm):
    warp(vm, WIN_START)
    with pytest.raises(Exception) as excinfo:
        market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:")


def test_one_second_before_the_cutoff_is_accepted(market, vm):
    warp(vm, WIN_START - 1)
    assert int(market.create_market("A", "CRYPTO", "BTC", DAY_STR)) == 1


def test_too_far_in_the_future_is_rejected(market, vm):
    warp(vm, WIN_START - 400 * 86400)
    with pytest.raises(Exception) as excinfo:
        market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "days ahead")


def test_within_the_forward_limit_is_accepted(market, vm):
    warp(vm, WIN_START - 366 * 86400)
    assert int(market.create_market("A", "CRYPTO", "BTC", DAY_STR)) == 1


def test_duplicate_kind_a_market_is_rejected(before):
    before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    with pytest.raises(Exception) as excinfo:
        before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "already exists")


def test_duplicate_kind_b_market_is_rejected(before):
    before.create_market("B", "CRYPTO", "", DAY_STR)
    with pytest.raises(Exception) as excinfo:
        before.create_market("B", "CRYPTO", "", DAY_STR)
    assert_reverts(excinfo, "EXPECTED:", "already exists")


def test_uniqueness_is_per_asset_per_day(before):
    before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    before.create_market("A", "CRYPTO", "ETH", DAY_STR)  # different asset
    before.create_market("A", "CRYPTO", "BTC", "2026-03-11")  # different day
    assert before.get_stats()["markets"] == 3


def test_kind_a_and_kind_b_do_not_collide(before):
    before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    before.create_market("B", "CRYPTO", "", DAY_STR)
    assert before.get_stats()["markets"] == 2


def test_kind_b_is_per_category(before):
    before.create_market("B", "CRYPTO", "", DAY_STR)
    before.create_market("B", "STOCKS", "", DAY_STR)
    assert before.get_stats()["markets"] == 2


def test_unique_key_lookup(before):
    market_id = before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    found = before.get_market_by_unique_key("A", "CRYPTO", "BTC", DAY_STR)
    assert found["exists"] is True
    assert found["market_id"] == int(market_id)

    missing = before.get_market_by_unique_key("A", "CRYPTO", "ETH", DAY_STR)
    assert missing["exists"] is False


def test_kind_b_unique_key_ignores_the_asset(before):
    before.create_market("B", "CRYPTO", "", DAY_STR)
    assert before.get_market_by_unique_key("B", "CRYPTO", "", DAY_STR)["exists"] is True
    assert before.get_market_by_unique_key("B", "CRYPTO", "BTC", DAY_STR)["exists"] is True


@pytest.mark.parametrize("bad_day", ["2026-02-30", "2026-13-01", "10-03-2026", "2026/03/10"])
def test_malformed_target_day_is_rejected(before, bad_day):
    with pytest.raises(Exception) as excinfo:
        before.create_market("A", "CRYPTO", "BTC", bad_day)
    assert_reverts(excinfo, "EXPECTED:")


def test_new_market_starts_empty_and_open(before):
    market_id = before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    m = before.get_market(market_id)
    assert m["state"] == "UNRESOLVED"
    assert m["phase"] == "OPEN"
    assert m["result"] == ""
    assert m["total_pool"] == "0"
    assert m["position_count"] == 0
    assert m["paid_out"] == "0"
    assert m["refund_all"] is False
    assert m["pools"] == {"UP": "0", "DOWN": "0"}


def test_kind_b_market_exposes_four_asset_pools(before):
    market_id = before.create_market("B", "STOCKS", "", DAY_STR)
    m = before.get_market(market_id)
    assert sorted(m["pools"].keys()) == ["AAPL", "MSFT", "NVDA", "TSLA"]
    assert m["universe"] == ["AAPL", "MSFT", "NVDA", "TSLA"]


def test_creating_a_market_writes_an_activity_record(before, accounts):
    before.create_market("A", "CRYPTO", "BTC", DAY_STR)
    activity = before.get_activity(0, 10)
    assert activity["total"] == 1
    assert activity["items"][0]["kind"] == "CREATE"
    assert activity["items"][0]["detail"] == "A/CRYPTO"


@pytest.mark.parametrize("day_str,weekday", [("2026-03-14", "Saturday"), ("2026-03-15", "Sunday")])
def test_stock_markets_cannot_target_a_weekend(market, vm, day_str, weekday):
    from datetime import date

    assert date.fromisoformat(day_str).strftime("%A") == weekday
    warp(vm, window(day_str)[0] - 5 * 86400)
    with pytest.raises(Exception) as excinfo:
        market.create_market("A", "STOCKS", "AAPL", day_str)
    assert_reverts(excinfo, "EXPECTED:", "Saturday or Sunday")
    with pytest.raises(Exception) as excinfo:
        market.create_market("B", "STOCKS", "", day_str)
    assert_reverts(excinfo, "EXPECTED:", "Saturday or Sunday")


def test_crypto_markets_can_target_a_weekend(market, vm):
    """Crypto trades every day, so the weekend rule applies to stocks only."""
    warp(vm, window("2026-03-14")[0] - 5 * 86400)
    assert int(market.create_market("A", "CRYPTO", "BTC", "2026-03-14")) == 1


def test_weekday_of_matches_python(gm):
    from datetime import date

    for offset in range(-400, 400, 37):
        day = gm.parse_day_string("2026-03-10") + offset
        expected = date.fromordinal(day + date(1970, 1, 1).toordinal()).weekday()
        assert gm.weekday_of(day) == expected
