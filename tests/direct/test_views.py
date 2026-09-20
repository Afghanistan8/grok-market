"""Views: phases, pagination and the portfolio feed.

The frontend runs entirely off these views, so they have to be complete and
self consistent without an indexer.
"""

import pytest

from conftest import GEN, MAX_PAGE, assert_reverts, mock_agree, warp, window

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


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


def test_phase_moves_through_the_lifecycle(market, vm, accounts):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)

    assert market.get_market_phase(market_id) == "OPEN"

    warp(vm, WIN_START + 60)
    assert market.get_market_phase(market_id) == "WINDOW_LIVE"

    warp(vm, WIN_END - 1)
    assert market.get_market_phase(market_id) == "WINDOW_LIVE"

    warp(vm, WIN_END)
    assert market.get_market_phase(market_id) == "READY_TO_SETTLE"

    mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("100.0", "110.0")})
    market.resolve_market(market_id)
    assert market.get_market_phase(market_id) == "SETTLED_UP"


def test_phase_reports_a_down_settlement(market, vm):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("110.0", "100.0")})
    warp(vm, WIN_END + 60)
    market.resolve_market(market_id)
    assert market.get_market_phase(market_id) == "SETTLED_DOWN"


def test_phase_reports_a_kind_b_winner(market, vm):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("B", "CRYPTO", "", DAY_STR)
    mock_agree(
        vm,
        "CRYPTO",
        DAY_STR,
        {"BTC": ("100", "101"), "ETH": ("100", "105"), "SOL": ("100", "99"), "XRP": ("100", "102")},
    )
    warp(vm, WIN_END + 60)
    market.resolve_market(market_id)
    assert market.get_market_phase(market_id) == "SETTLED_WINNER"
    assert market.get_market(market_id)["result"] == "ETH"


def test_unknown_market_views(market):
    assert market.get_market(999)["found"] is False
    assert market.get_settlement_evidence(999)["found"] is False
    assert market.get_position(999, "0x" + "11" * 20)["found"] is False
    with pytest.raises(Exception) as excinfo:
        market.get_market_phase(999)
    assert_reverts(excinfo, "EXPECTED:", "unknown market")


def test_resolving_twice_is_rejected(market, vm):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("100.0", "110.0")})
    warp(vm, WIN_END + 60)
    market.resolve_market(market_id)
    with pytest.raises(Exception) as excinfo:
        market.resolve_market(market_id)
    assert_reverts(excinfo, "EXPECTED:", "already resolved")


def test_resolving_early_is_rejected(market, vm):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    warp(vm, WIN_END - 1)
    with pytest.raises(Exception) as excinfo:
        market.resolve_market(market_id)
    assert_reverts(excinfo, "EXPECTED:", "not finished")


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@pytest.fixture
def board(market, vm):
    """Twelve markets across both categories and several days."""
    warp(vm, WIN_START - 30 * 86400)
    ids = []
    for offset in range(3):
        day = "2026-03-%02d" % (10 + offset)
        for asset in ("BTC", "ETH"):
            ids.append(market.create_market("A", "CRYPTO", asset, day))
        for asset in ("AAPL", "MSFT"):
            ids.append(market.create_market("A", "STOCKS", asset, day))
    return market, ids


def test_markets_are_listed_newest_first(board):
    market, ids = board
    page = market.get_markets(0, 50)
    assert page["total"] == 12
    returned = [item["id"] for item in page["items"]]
    assert returned == sorted(returned, reverse=True)
    assert returned[0] == int(ids[-1])


def test_pagination_walks_the_whole_board_without_repeats(board):
    market, ids = board
    seen = []
    for offset in range(0, 12, 5):
        page = market.get_markets(offset, 5)
        seen.extend(item["id"] for item in page["items"])
    assert sorted(seen) == sorted(int(i) for i in ids)


def test_page_size_is_capped(board):
    market, _ = board
    assert len(market.get_markets(0, 9999)["items"]) <= MAX_PAGE


def test_offset_past_the_end_returns_nothing(board):
    market, _ = board
    assert market.get_markets(99, 10)["items"] == []


def test_filtering_by_category(board):
    market, _ = board
    crypto = market.get_markets_by_category("CRYPTO", 0, 50)
    stocks = market.get_markets_by_category("STOCKS", 0, 50)
    assert len(crypto["items"]) == 6
    assert len(stocks["items"]) == 6
    assert all(item["category"] == "CRYPTO" for item in crypto["items"])
    assert all(item["category"] == "STOCKS" for item in stocks["items"])


def test_filtering_by_an_unknown_category_is_rejected(board):
    market, _ = board
    with pytest.raises(Exception) as excinfo:
        market.get_markets_by_category("FOREX", 0, 50)
    assert_reverts(excinfo, "EXPECTED:")


def test_open_markets_exclude_closed_ones(board, vm):
    market, _ = board
    assert len(market.get_open_markets(0, 50)["items"]) == 12
    # Once the first day's window starts, its four markets are no longer OPEN.
    warp(vm, window("2026-03-10")[0] + 60)
    still_open = market.get_open_markets(0, 50)["items"]
    assert len(still_open) == 8
    assert all(item["target_day"] != "2026-03-10" for item in still_open)


def test_stats_summarise_the_board(board, vm, accounts):
    market, ids = board
    stake(market, vm, accounts["bob"], ids[0], "UP", 2 * GEN)
    stats = market.get_stats()
    assert stats["markets"] == 12
    assert stats["open"] == 12
    assert stats["open_pool"] == str(2 * GEN)
    assert stats["ready_to_settle"] == 0


def test_stats_count_markets_ready_to_settle(board, vm):
    market, _ = board
    warp(vm, window("2026-03-10")[1] + 60)
    stats = market.get_stats()
    assert stats["ready_to_settle"] == 4
    assert stats["open"] == 4
    assert stats["window_live"] == 4


# ---------------------------------------------------------------------------
# Per-wallet views
# ---------------------------------------------------------------------------


def test_user_markets_lists_what_that_wallet_created(market, vm, accounts):
    warp(vm, WIN_START - 5 * 86400)
    vm.sender = accounts["bob"]
    market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    market.create_market("A", "CRYPTO", "ETH", DAY_STR)
    vm.sender = accounts["carol"]
    market.create_market("A", "CRYPTO", "SOL", DAY_STR)

    assert market.get_user_markets(wallet(accounts["bob"]), 0, 50)["total"] == 2
    assert market.get_user_markets(wallet(accounts["carol"]), 0, 50)["total"] == 1
    assert market.get_user_markets(wallet(accounts["dave"]), 0, 50)["total"] == 0


def test_portfolio_reports_stake_and_claimable(market, vm, accounts):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    stake(market, vm, accounts["carol"], market_id, "DOWN", 4 * GEN)

    portfolio = market.get_user_positions(wallet(accounts["bob"]), 0, 50)
    assert portfolio["total"] == 1
    row = portfolio["items"][0]
    assert row["side"] == "UP"
    assert row["stake"] == str(2 * GEN)
    assert row["claimed"] is False
    assert row["claimable"] == "0"  # nothing to claim before resolution
    assert row["market"]["id"] == int(market_id)

    mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("100.0", "110.0")})
    warp(vm, WIN_END + 60)
    market.resolve_market(market_id)

    row = market.get_user_positions(wallet(accounts["bob"]), 0, 50)["items"][0]
    assert row["claimable"] == str(6 * GEN)

    vm.sender = accounts["bob"]
    market.claim(market_id)
    row = market.get_user_positions(wallet(accounts["bob"]), 0, 50)["items"][0]
    assert row["claimed"] is True
    assert row["claimable"] == "0"


def test_portfolio_spans_several_markets(market, vm, accounts):
    warp(vm, WIN_START - 5 * 86400)
    first = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    second = market.create_market("A", "CRYPTO", "ETH", DAY_STR)
    stake(market, vm, accounts["bob"], first, "UP", 2 * GEN)
    stake(market, vm, accounts["bob"], second, "DOWN", 3 * GEN)

    portfolio = market.get_user_positions(wallet(accounts["bob"]), 0, 50)
    assert portfolio["total"] == 2
    assert {row["market"]["id"] for row in portfolio["items"]} == {int(first), int(second)}


def test_activity_is_newest_first(market, vm, accounts):
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    stake(market, vm, accounts["bob"], market_id, "UP", 2 * GEN)
    feed = market.get_activity(0, 50)
    assert feed["total"] == 2
    assert [item["kind"] for item in feed["items"]] == ["STAKE", "CREATE"]
    assert feed["items"][0]["seq"] > feed["items"][1]["seq"]


def test_supported_universe_exposes_the_stake_band(market):
    universe = market.get_supported_universe()
    assert universe["min_stake"] == str(2 * GEN)
    assert universe["max_stake"] == str(6 * GEN)
    assert universe["utc_offset_seconds"] == 3600
    assert universe["max_page"] == MAX_PAGE
    assert universe["terminal_refund_delay"] == 5 * 86400
    assert [kind["id"] for kind in universe["kinds"]] == ["A", "B"]


def test_wei_values_are_returned_as_strings(market, vm, accounts):
    """6 GEN exceeds JS Number precision, so views never return raw integers."""
    warp(vm, WIN_START - 5 * 86400)
    market_id = market.create_market("A", "CRYPTO", "BTC", DAY_STR)
    stake(market, vm, accounts["bob"], market_id, "UP", 6 * GEN)
    m = market.get_market(market_id)
    assert isinstance(m["total_pool"], str)
    assert isinstance(m["pools"]["UP"], str)
    assert int(m["total_pool"]) == 6 * GEN
    assert int(m["total_pool"]) > 2**53
