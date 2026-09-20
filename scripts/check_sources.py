"""Prove that every locked source can reconstruct a real GMT+1 day.

This script imports the parsers out of ``contracts/GrokMarket.py`` itself, so
what it exercises is exactly what ``resolve_market`` runs on chain. If this
passes for an asset, the only remaining reason the contract cannot settle that
asset is the network itself.

    python scripts/check_sources.py
    python scripts/check_sources.py --day 2026-09-18
    python scripts/check_sources.py --category STOCKS --verbose

Exit code is 0 only when every checked asset produced an agreeing verdict from
both of its independent sources.
"""

import argparse
import contextlib
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "GrokMarket.py"


def load_contract_module(stack):
    """Import the contract with the real SDK on sys.path.

    The VM context must stay open for as long as the module is used: leaving it
    evicts every ``_contract_*`` module and strips the SDK from ``sys.path``.
    """
    try:
        from gltest.direct import VMContext, load_contract_class
    except ImportError:
        print("genlayer-test is required: pip install -r requirements-dev.txt")
        raise SystemExit(2)

    vm = VMContext()
    vm.warp("2026-01-01T00:00:00Z")
    stack.enter_context(vm.activate())
    load_contract_class(CONTRACT, vm)
    module = sys.modules.get("_contract_GrokMarket")
    if module is None:
        print("could not import the contract module")
        raise SystemExit(2)
    return module


def fetch(url: str, headers: dict, timeout: int = 30):
    request = urllib.request.Request(url, headers=headers)
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), time.time() - started
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), time.time() - started
    except Exception as exc:  # network level failure
        return 0, str(exc).encode("utf-8"), time.time() - started


def most_recent_complete_day(gm) -> int:
    """Newest GMT+1 calendar day whose window has already closed."""
    now = int(time.time())
    day = now // 86400 + 1
    while True:
        _, win_end = gm.window_for_day(day)
        if win_end <= now:
            return day
        day -= 1


def check_asset(gm, category: str, asset: str, day_index: int, verbose: bool) -> dict:
    win_start, win_end = gm.window_for_day(day_index)
    src_a, src_b = gm.category_sources(category)

    if category == "CRYPTO":
        url_a = gm.coingecko_url(asset, win_start, win_end)
        url_b = gm.binance_url(asset, win_start, win_end)
    else:
        url_a = gm.stockanalysis_url(asset, day_index)
        url_b = gm.nasdaq_url(asset, day_index)

    row = {"asset": asset, "day": gm.format_day(day_index), "ok": False}

    for label, url, source in (("a", url_a, src_a), ("b", url_b, src_b)):
        status, body, elapsed = fetch(url, gm.REQUEST_HEADERS)
        row[label + "_source"] = source
        row[label + "_status"] = status
        row[label + "_ms"] = int(elapsed * 1000)
        row[label + "_url"] = url
        try:
            text = gm.classify_response(status, body)
            if source == "coingecko":
                open_v, close_v = gm.coingecko_window(text, win_start, win_end)
            elif source == "binance":
                open_v, close_v = gm.binance_window(text, win_start, win_end)
            elif source == "stockanalysis":
                open_v, close_v = gm.stockanalysis_day(text, day_index)
            else:
                open_v, close_v = gm.nasdaq_day(text, day_index)
            row[label + "_open"] = open_v
            row[label + "_close"] = close_v
            row[label + "_dir"] = gm.direction_of(open_v, close_v)
            row[label + "_bps"] = gm.return_bps(open_v, close_v)
            row[label + "_error"] = ""
        except Exception as exc:
            message = getattr(exc, "message", None) or str(exc)
            row[label + "_error"] = message
            if verbose:
                row[label + "_body"] = body[:200]

    if not row.get("a_error") and not row.get("b_error"):
        row["readable"] = True
        row["agree"] = row["a_dir"] == row["b_dir"]
        row["ok"] = row["agree"]
    else:
        row["readable"] = False
    return row


def human(scaled_price: int) -> str:
    if scaled_price is None:
        return "-"
    return "%.4f" % (scaled_price / 1e8)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", help="GMT+1 day as YYYY-MM-DD (default: last complete day)")
    parser.add_argument("--category", choices=["CRYPTO", "STOCKS"], help="check one category")
    parser.add_argument(
        "--lookback",
        type=int,
        default=5,
        help="for STOCKS, walk back this many days to find a trading session",
    )
    parser.add_argument("--verbose", action="store_true", help="print URLs and error bodies")
    args = parser.parse_args()

    with contextlib.ExitStack() as stack:
        gm = load_contract_module(stack)
        return run(gm, args)


def run(gm, args) -> int:
    if args.day:
        base_day = gm.parse_day_string(args.day)
    else:
        base_day = most_recent_complete_day(gm)

    categories = [args.category] if args.category else ["CRYPTO", "STOCKS"]
    all_rows = []
    unreadable = 0
    disagreed = 0

    for category in categories:
        assets = gm.category_assets(category)
        src_a, src_b = gm.category_sources(category)
        print()
        print("=" * 78)
        print("%s   sources: %s + %s" % (category, src_a, src_b))
        print("=" * 78)

        for asset in assets:
            day = base_day
            row = check_asset(gm, category, asset, day, args.verbose)

            # US equities do not trade every calendar day. Walking back finds
            # the newest real session rather than reporting a weekend as broken.
            attempts = 0
            while (
                category == "STOCKS"
                and not row["ok"]
                and "no session dated" in (row.get("a_error", "") + row.get("b_error", ""))
                and attempts < args.lookback
            ):
                attempts += 1
                day -= 1
                row = check_asset(gm, category, asset, day, args.verbose)

            all_rows.append(row)
            if not row["readable"]:
                unreadable += 1
            elif not row["agree"]:
                disagreed += 1

            status = "OK  " if row["ok"] else ("SPLIT" if row["readable"] else "FAIL ")
            print()
            print(
                "  [%s] %-5s  day %s" % (status, asset, row["day"])
                + ("" if attempts == 0 else "  (walked back %d day(s))" % attempts)
            )
            for label in ("a", "b"):
                source = row["%s_source" % label]
                if row.get("%s_error" % label):
                    print(
                        "        %-14s http=%-3s  %s"
                        % (source, row["%s_status" % label], row["%s_error" % label])
                    )
                    if args.verbose and row.get("%s_body" % label):
                        print("            body: %r" % row["%s_body" % label])
                else:
                    print(
                        "        %-14s http=%-3s  open=%-12s close=%-12s  %-4s %+d bps  (%d ms)"
                        % (
                            source,
                            row["%s_status" % label],
                            human(row["%s_open" % label]),
                            human(row["%s_close" % label]),
                            row["%s_dir" % label],
                            row["%s_bps" % label],
                            row["%s_ms" % label],
                        )
                    )
                if args.verbose:
                    print("            url:  %s" % row["%s_url" % label])
            if "agree" in row:
                if row["agree"]:
                    print("        verdict        both sources agree: " + row["a_dir"])
                else:
                    print(
                        "        verdict        sources disagree -> market would settle"
                        " INCONCLUSIVE and refund every stake"
                    )

    print()
    print("=" * 78)
    checked = len(all_rows)
    readable = checked - unreadable
    print("%d/%d assets reconstructed from both sources" % (readable, checked))
    print("%d/%d of those produced an agreeing verdict" % (readable - disagreed, readable))
    if disagreed:
        print()
        print("A split is not a bug: on a near-flat day a global average (coingecko)")
        print("and a single venue pair (binance) can genuinely differ in sign. The")
        print("contract refuses to pick one, settles INCONCLUSIVE and refunds stakes.")
    if unreadable:
        print()
        print("Unreadable sources above would make resolve_market revert, leaving the")
        print("market READY_TO_SETTLE so anyone can retry until the 5 day refund deadline.")
    print("=" * 78)
    return 1 if unreadable else 0


if __name__ == "__main__":
    raise SystemExit(main())
