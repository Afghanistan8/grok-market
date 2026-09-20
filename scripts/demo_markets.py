"""Walk five market lifecycles end to end, printing what the contract does.

Runs in-process against the real SDK, so no node, faucet or wallet is needed:

    python scripts/demo_markets.py

The five scenarios are the ones worth understanding before putting GEN behind
a position:

  1. Both feeds agree the day closed up          -> settles UP, winners split the pool
  2. Both feeds agree the day closed down        -> settles DOWN
  3. The two feeds disagree on direction         -> INCONCLUSIVE, everyone refunded
  4. Two feeds pick the same best performer      -> settles to that asset
  5. No feed is reachable for five days          -> terminal refund, no invented price
"""

import contextlib
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

GEN = 10**18
DAY_STR = "2026-03-10"


def banner(number, title):
    print()
    print("=" * 74)
    print(" %d. %s" % (number, title))
    print("=" * 74)


def show(market, market_id, label=""):
    m = market.get_market(market_id)
    pools = "  ".join("%s=%s" % (k, int(v) / GEN) for k, v in m["pools"].items())
    print(
        "    %-18s phase=%-16s result=%-13s pool=%s GEN"
        % (label, m["phase"], m["result"] or "-", int(m["total_pool"]) / GEN)
    )
    print("    %-18s %s" % ("", pools))


def show_evidence(market, market_id):
    evidence = market.get_settlement_evidence(market_id)
    if not evidence["found"]:
        print("    no evidence recorded")
        return
    if evidence["terminal_refund"]:
        print("    terminal refund: no prices were fetched, nothing was invented")
        return
    print(
        "    %-14s %-14s %s"
        % ("", evidence["source_a"] + " (A)", evidence["source_b"] + " (B)")
    )
    for row in evidence["rows"]:
        print(
            "    %-14s %-14s %s"
            % (
                row["symbol"],
                "%.2f -> %.2f" % (row["a_open"] / 1e8, row["a_close"] / 1e8),
                "%.2f -> %.2f" % (row["b_open"] / 1e8, row["b_close"] / 1e8),
            )
        )
    print(
        "    verdicts:      A=%s  B=%s  ->  final=%s"
        % (evidence["a_verdict"], evidence["b_verdict"], evidence["final_result"])
    )


def show_claims(market, market_id, accounts, names):
    for name in names:
        wallet = "0x" + bytes(accounts[name]).hex()
        claim = market.get_claimable(market_id, wallet)
        print(
            "    %-8s stake %-6s -> claimable %-8s (%s)"
            % (
                name,
                "%.2f" % (int(market.get_position(market_id, wallet)["stake"]) / GEN),
                "%.2f" % (int(claim["claimable"]) / GEN),
                claim["reason"],
            )
        )


def main() -> int:
    from gltest.direct import VMContext, create_address, deploy_contract

    import conftest as helpers

    accounts = {name: create_address(name) for name in ("alice", "bob", "carol", "dave")}
    win_start, win_end = helpers.window(DAY_STR)

    with contextlib.ExitStack() as stack:
        vm = VMContext()
        vm.sender = accounts["alice"]
        vm.warp("2026-01-01T00:00:00Z")
        stack.enter_context(vm.activate())
        market = deploy_contract(ROOT / "contracts" / "GrokMarket.py", vm)
        vm.deal(vm._contract_address, 10_000 * GEN)

        print("Grok-Market demo, target GMT+1 day %s" % DAY_STR)
        print("window %d..%d (a GMT+1 day is one hour ahead of UTC, always)" % (win_start, win_end))

        def new_market(kind, category, asset):
            helpers.warp(vm, win_start - 5 * 86400)
            return market.create_market(kind, category, asset, DAY_STR)

        def bet(market_id, name, side, amount):
            vm.sender = accounts[name]
            vm.value = amount
            try:
                market.take_position(market_id, side)
            finally:
                vm.value = 0
            vm.sender = accounts["alice"]

        # 1 -------------------------------------------------------------
        banner(1, "Both feeds agree the day closed UP")
        market_id = new_market("A", "CRYPTO", "BTC")
        bet(market_id, "bob", "UP", 3 * GEN)
        bet(market_id, "carol", "DOWN", 2 * GEN)
        show(market, market_id, "after staking")
        helpers.mock_agree(vm, "CRYPTO", DAY_STR, {"BTC": ("100.00", "110.00")})
        helpers.warp(vm, win_end + 60)
        print("    resolve_market ->", market.resolve_market(market_id))
        show(market, market_id, "after resolve")
        show_evidence(market, market_id)
        show_claims(market, market_id, accounts, ["bob", "carol"])
        vm.sender = accounts["bob"]
        print("    bob claims %.2f GEN" % (int(market.claim(market_id)) / GEN))
        vm.sender = accounts["alice"]

        # 2 -------------------------------------------------------------
        banner(2, "Both feeds agree the day closed DOWN")
        market_id = new_market("A", "CRYPTO", "ETH")
        bet(market_id, "bob", "UP", 2 * GEN)
        bet(market_id, "carol", "DOWN", 4 * GEN)
        helpers.mock_agree(vm, "CRYPTO", DAY_STR, {"ETH": ("2600.00", "2500.00")})
        helpers.warp(vm, win_end + 60)
        print("    resolve_market ->", market.resolve_market(market_id))
        show(market, market_id, "after resolve")
        show_evidence(market, market_id)
        show_claims(market, market_id, accounts, ["bob", "carol"])

        # 3 -------------------------------------------------------------
        banner(3, "The two feeds disagree, so nobody wins")
        market_id = new_market("A", "CRYPTO", "SOL")
        bet(market_id, "bob", "UP", 3 * GEN)
        bet(market_id, "carol", "DOWN", 3 * GEN)
        vm.clear_mocks()
        helpers.mock_crypto(vm, "SOL", DAY_STR, "100.00", "110.00", "100.00", "90.00")
        helpers.warp(vm, win_end + 60)
        print("    resolve_market ->", market.resolve_market(market_id))
        show(market, market_id, "after resolve")
        show_evidence(market, market_id)
        show_claims(market, market_id, accounts, ["bob", "carol"])
        print("    note: a refund, not a coin flip. The contract will not pick a side.")

        # 4 -------------------------------------------------------------
        banner(4, "Relative return: which asset led the GMT+1 day")
        market_id = new_market("B", "CRYPTO", "")
        bet(market_id, "bob", "ETH", 2 * GEN)
        bet(market_id, "carol", "BTC", 3 * GEN)
        bet(market_id, "dave", "ETH", 2 * GEN)
        vm.clear_mocks()
        helpers.mock_agree(
            vm,
            "CRYPTO",
            DAY_STR,
            {
                "BTC": ("100.00", "101.00"),
                "ETH": ("100.00", "105.00"),
                "SOL": ("100.00", "99.00"),
                "XRP": ("100.00", "102.00"),
            },
        )
        helpers.warp(vm, win_end + 60)
        print("    resolve_market ->", market.resolve_market(market_id))
        show(market, market_id, "after resolve")
        show_evidence(market, market_id)
        show_claims(market, market_id, accounts, ["bob", "carol", "dave"])

        # 5 -------------------------------------------------------------
        banner(5, "Every feed is unreachable for five days")
        market_id = new_market("A", "STOCKS", "MSFT")
        bet(market_id, "bob", "UP", 2 * GEN)
        bet(market_id, "carol", "DOWN", 5 * GEN)
        vm.clear_mocks()
        helpers.warp(vm, win_end + 60)
        try:
            market.resolve_market(market_id)
        except Exception as exc:
            print("    early resolve reverts:", getattr(exc, "message", exc))
        show(market, market_id, "still retryable")
        helpers.warp(vm, win_end + 5 * 86400)
        print("    resolve_market ->", market.resolve_market(market_id))
        show(market, market_id, "after deadline")
        show_evidence(market, market_id)
        show_claims(market, market_id, accounts, ["bob", "carol"])

        # ----------------------------------------------------------------
        print()
        print("=" * 74)
        stats = market.get_stats()
        print(
            " board: %d markets, %d settled, %.2f GEN paid out across the demo"
            % (
                stats["markets"],
                stats["settled"],
                sum(
                    int(market.get_market(i)["paid_out"])
                    for i in range(1, stats["markets"] + 1)
                )
                / GEN,
            )
        )
        print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
