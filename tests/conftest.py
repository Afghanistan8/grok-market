"""Shared fixtures for the Grok-Market test suite.

Tests run against the real ``py-genlayer`` SDK through ``gltest``'s direct
mode, so storage, calldata, the equivalence principle and native transfers
behave exactly as they do on chain. Nothing here is a hand written stand-in
for the VM.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest
from gltest.direct import VMContext, create_address, deploy_contract, load_contract_class

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "GrokMarket.py"

GEN = 10**18
DAY = 86400
HOUR = 3600
GMT_PLUS_ONE = 3600
PRICE_SCALE = 10**8
MAX_PAGE = 50

EPOCH_ORDINAL = date(1970, 1, 1).toordinal()


# ---------------------------------------------------------------------------
# Time helpers (independent of the contract, so they cross check its math)
# ---------------------------------------------------------------------------


def day_index(day_str: str) -> int:
    y, m, d = int(day_str[0:4]), int(day_str[5:7]), int(day_str[8:10])
    return date(y, m, d).toordinal() - EPOCH_ORDINAL


def day_string(index: int) -> str:
    return date.fromordinal(index + EPOCH_ORDINAL).isoformat()


def day_string_us(index: int) -> str:
    d = date.fromordinal(index + EPOCH_ORDINAL)
    return "%02d/%02d/%04d" % (d.month, d.day, d.year)


def window(day_str: str) -> tuple:
    start = day_index(day_str) * DAY - GMT_PLUS_ONE
    return (start, start + DAY)


def iso(epoch_seconds: int) -> str:
    """Unix seconds -> the ISO 8601 string the GenVM hands the contract."""
    days, rem = divmod(epoch_seconds, DAY)
    d = date.fromordinal(days + EPOCH_ORDINAL)
    return "%sT%02d:%02d:%02dZ" % (d.isoformat(), rem // 3600, (rem % 3600) // 60, rem % 60)


def warp(vm, epoch_seconds: int) -> str:
    """Move consensus time, including the field the contract actually reads.

    ``VMContext.warp`` updates the patched stdlib clock and re-publishes
    ``gl.message``, but its refresh does not carry ``datetime`` back into the
    already-imported ``gl.message_raw`` dict. The contract deliberately reads
    ``gl.message_raw['datetime']`` (the consensus transaction time) rather than
    a host clock, so tests patch that field too.
    """
    ts = iso(epoch_seconds)
    vm.warp(ts)
    gl_module = sys.modules.get("genlayer.gl")
    if gl_module is not None and getattr(gl_module, "message_raw", None) is not None:
        gl_module.message_raw["datetime"] = ts
    return ts


# ---------------------------------------------------------------------------
# Source payload builders. These emit raw JSON text so tests control the exact
# numeric literals, which is what the contract parses.
# ---------------------------------------------------------------------------


def coinbase_body(win_start: int, bars, newest_first: bool = True) -> str:
    """``bars`` is a list of (open, close) decimal-string pairs, one per hour.

    Rows are ``[time, low, high, open, close, volume]``. Coinbase returns them
    newest first, so that is the default.
    """
    rows = []
    for i, (o, c) in enumerate(bars):
        rows.append("[%d,%s,%s,%s,%s,1.5]" % (win_start + i * HOUR, o, c, o, c))
    if newest_first:
        rows.reverse()
    return "[" + ",".join(rows) + "]"


def coinbase_simple(win_start: int, open_price: str, close_price: str) -> str:
    bars = [(open_price, "1.0")] + [("1.0", "1.0")] * 22 + [("1.0", close_price)]
    return coinbase_body(win_start, bars)


def binance_body(win_start: int, bars) -> str:
    """``bars`` is a list of (open, close) decimal-string pairs, one per hour."""
    out = []
    for i, (o, c) in enumerate(bars):
        open_ms = (win_start + i * HOUR) * 1000
        close_ms = open_ms + HOUR * 1000 - 1
        out.append(
            '[%d,"%s","%s","%s","%s","1.0",%d,"1.0",1,"1.0","1.0","0"]'
            % (open_ms, o, o, o, c, close_ms)
        )
    return "[" + ",".join(out) + "]"


def binance_simple(win_start: int, open_price: str, close_price: str) -> str:
    bars = [(open_price, "1.0")] + [("1.0", "1.0")] * 22 + [("1.0", close_price)]
    return binance_body(win_start, bars)


def stockanalysis_body(rows) -> str:
    """``rows`` is a list of (day_string, open, close) tuples."""
    entries = []
    for day_str, o, c in rows:
        entries.append(
            '{"a":%s,"c":%s,"h":%s,"l":%s,"o":%s,"t":"%s","v":1000,"ch":0}'
            % (c, c, c, o, o, day_str)
        )
    return '{"status":200,"data":{"data":[' + ",".join(entries) + '],"news":[],"other":{}}}'


def nasdaq_body(rows) -> str:
    """``rows`` is a list of (us_day_string, open, close) tuples."""
    entries = []
    for day_us, o, c in rows:
        entries.append(
            '{"date":"%s","close":"$%s","volume":"1,000","open":"$%s","high":"$%s","low":"$%s"}'
            % (day_us, c, o, c, o)
        )
    return (
        '{"data":{"symbol":"X","totalRecords":%d,"tradesTable":{"asOf":null,'
        '"headers":{"date":"Date","close":"Close/Last","volume":"Volume",'
        '"open":"Open","high":"High","low":"Low"},"rows":[%s]}},'
        '"message":null,"status":{"rCode":200}}' % (len(rows), ",".join(entries))
    )


# ---------------------------------------------------------------------------
# Mock wiring
# ---------------------------------------------------------------------------

COINBASE_PRODUCTS = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "XRP": "XRP-USD"}
BINANCE_PAIRS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT"}
CRYPTO_ASSETS = ("BTC", "ETH", "SOL", "XRP")
STOCKS_ASSETS = ("AAPL", "MSFT", "NVDA", "TSLA")


def mock_crypto(vm, asset, day_str, a_open, a_close, b_open, b_close, status=200):
    win_start, _ = window(day_str)
    vm.mock_web(
        r"products/%s/candles" % COINBASE_PRODUCTS[asset],
        {"method": "GET", "status": status, "body": coinbase_simple(win_start, a_open, a_close)},
    )
    vm.mock_web(
        r"symbol=%s&" % BINANCE_PAIRS[asset],
        {"method": "GET", "status": status, "body": binance_simple(win_start, b_open, b_close)},
    )


def mock_stock(vm, asset, day_str, a_open, a_close, b_open, b_close, status=200):
    idx = day_index(day_str)
    vm.mock_web(
        r"/s/%s/history" % asset.lower(),
        {
            "method": "GET",
            "status": status,
            "body": stockanalysis_body([(day_string(idx), a_open, a_close)]),
        },
    )
    vm.mock_web(
        r"quote/%s/historical" % asset,
        {
            "method": "GET",
            "status": status,
            "body": nasdaq_body([(day_string_us(idx), b_open, b_close)]),
        },
    )


def mock_agree(vm, category, day_str, prices):
    """``prices`` maps symbol -> (open, close); both sources report the same."""
    for symbol, (o, c) in prices.items():
        if category == "CRYPTO":
            mock_crypto(vm, symbol, day_str, o, c, o, c)
        else:
            mock_stock(vm, symbol, day_str, o, c, o, c)


def scaled(decimal_string: str) -> int:
    """Mirror of the contract's decimal -> 1e8 integer conversion."""
    s = decimal_string.replace("$", "").replace(",", "")
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        int_part, frac = s.split(".", 1)
    else:
        int_part, frac = s, ""
    digits = int((int_part or "0") + frac)
    power = 8 - len(frac)
    value = digits * (10**power) if power >= 0 else digits // (10 ** (-power))
    return -value if neg else value


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def accounts():
    return {
        "alice": create_address("alice"),
        "bob": create_address("bob"),
        "carol": create_address("carol"),
        "dave": create_address("dave"),
    }


@pytest.fixture
def vm(accounts):
    context = VMContext()
    context.sender = accounts["alice"]
    context.warp("2026-01-01T00:00:00Z")
    return context


@pytest.fixture
def market(vm):
    """Deployed contract inside an active VM context."""
    with vm.activate():
        contract = deploy_contract(CONTRACT, vm)
        vm.deal(vm._contract_address, 10_000 * GEN)
        yield contract


@pytest.fixture
def gm(vm):
    """The contract module itself, for testing its pure helpers directly."""
    with vm.activate():
        load_contract_class(CONTRACT, vm)
        yield sys.modules["_contract_GrokMarket"]


def record_transfers(vm):
    """Capture every native value transfer the contract emits.

    Direct mode has no EthSend handler, so unhandled gl_calls fall through to
    this hook. Returning None lets the call complete as a no-op.
    """
    sent = []

    def hook(_vm, request):
        if "EthSend" in request:
            sent.append(request["EthSend"])
        return None

    vm._gl_call_hook = hook
    return sent


def fail_transfers(vm, message: str = "recipient rejected the transfer"):
    """Make every native value transfer raise, as a failing send would."""

    def hook(_vm, request):
        if "EthSend" in request:
            raise RuntimeError(message)
        return None

    vm._gl_call_hook = hook


def revert_message(exc: BaseException) -> str:
    return getattr(exc, "message", None) or str(exc)


def assert_reverts(excinfo, prefix: str, fragment: str = "") -> None:
    message = revert_message(excinfo.value)
    assert prefix in message, "expected %s, got %r" % (prefix, message)
    if fragment:
        assert fragment in message, "expected %r in %r" % (fragment, message)
