# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
Grok-Market -- a permissionless daily prediction market on GenLayer.

There is no admin key, no privileged oracle and no backend resolver. When anyone
calls ``resolve_market`` the contract itself fetches two independent public feeds
inside an equivalence-principle block, reconstructs the target GMT+1 calendar day
from each feed separately, and derives an outcome from each feed's own prices.

A single feed can never produce a direction or a winner: both must independently
agree, otherwise the market settles INCONCLUSIVE and every stake is refunded.
"""

import json
from dataclasses import dataclass

from genlayer import *

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAY = 86400
HOUR = 3600
GMT_PLUS_ONE = 3600  # fixed +1h offset, never DST, never a named timezone

GEN = 10**18
MIN_STAKE = 2 * GEN
MAX_STAKE = 6 * GEN

MAX_FORWARD_DAYS = 366
TERMINAL_REFUND_DELAY = 5 * DAY
MAX_PAGE = 50
MAX_SOURCE_BYTES = 60000
PRICE_SCALE = 10**8
BPS = 10000

KIND_DIRECTION = "A"  # one asset closes UP or DOWN over the GMT+1 day
KIND_RELATIVE = "B"  # which asset in the category posts the best % return

CAT_CRYPTO = "CRYPTO"
CAT_STOCKS = "STOCKS"

STATE_UNRESOLVED = "UNRESOLVED"
STATE_SETTLED = "SETTLED"
STATE_INCONCLUSIVE = "INCONCLUSIVE"

PHASE_OPEN = "OPEN"
PHASE_WINDOW_LIVE = "WINDOW_LIVE"
PHASE_READY = "READY_TO_SETTLE"
PHASE_SETTLED_UP = "SETTLED_UP"
PHASE_SETTLED_DOWN = "SETTLED_DOWN"
PHASE_SETTLED_WINNER = "SETTLED_WINNER"
PHASE_INCONCLUSIVE = "INCONCLUSIVE"

UP = "UP"
DOWN = "DOWN"
TIE = "TIE"
INCONCLUSIVE = "INCONCLUSIVE"

PAYLOAD_VERSION = "v1"
PAYLOAD_FIELDS = 12

# ---------------------------------------------------------------------------
# Catalogs -- compile time. Callers pick a key, they never supply a URL.
# ---------------------------------------------------------------------------

CRYPTO_ASSETS = ("BTC", "ETH", "SOL", "XRP")
STOCKS_ASSETS = ("AAPL", "MSFT", "NVDA", "TSLA")

COINGECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple"}
BINANCE_PAIRS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT"}

SRC_COINGECKO = "coingecko"
SRC_BINANCE = "binance"
SRC_STOCKANALYSIS = "stockanalysis"
SRC_NASDAQ = "nasdaq"

# Both stock feeds gate non-browser clients, so the contract pins an explicit
# header set. These headers are part of the locked request, not caller input.
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def category_assets(category: str) -> tuple:
    if category == CAT_CRYPTO:
        return CRYPTO_ASSETS
    if category == CAT_STOCKS:
        return STOCKS_ASSETS
    return ()


def category_sources(category: str) -> tuple:
    if category == CAT_CRYPTO:
        return (SRC_COINGECKO, SRC_BINANCE)
    return (SRC_STOCKANALYSIS, SRC_NASDAQ)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _expected(msg: str):
    raise gl.vm.UserError("EXPECTED: " + msg)


def _invariant(msg: str):
    raise gl.vm.UserError("INVARIANT: " + msg)


def _transient(msg: str):
    raise gl.vm.UserError("TRANSIENT: " + msg)


def _external(msg: str):
    raise gl.vm.UserError("EXTERNAL: " + msg)


# ---------------------------------------------------------------------------
# Civil calendar math, hand rolled so the contract never depends on a host
# clock or on a timezone database.
# ---------------------------------------------------------------------------


def _is_leap(y: int) -> bool:
    return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0


def _days_from_civil(y: int, m: int, d: int) -> int:
    yy = y - 1 if m <= 2 else y
    era = (yy if yy >= 0 else yy - 399) // 400
    yoe = yy - era * 400
    mp = m - 3 if m > 2 else m + 9
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z: int) -> tuple:
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    if m <= 2:
        y += 1
    return (y, m, d)


def _days_in_month(y: int, m: int) -> int:
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m == 4 or m == 6 or m == 9 or m == 11:
        return 30
    return 31


def _all_digits(s: str) -> bool:
    if len(s) == 0:
        return False
    for ch in s:
        if ch < "0" or ch > "9":
            return False
    return True


def parse_day_string(s: str) -> int:
    """``YYYY-MM-DD`` (a GMT+1 calendar date) -> day index since 1970-01-01."""
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        _expected("target_day must be YYYY-MM-DD")
    ys = s[0:4]
    ms = s[5:7]
    ds = s[8:10]
    if not (_all_digits(ys) and _all_digits(ms) and _all_digits(ds)):
        _expected("target_day must be YYYY-MM-DD")
    y = int(ys)
    m = int(ms)
    d = int(ds)
    if y < 1970 or y > 9999 or m < 1 or m > 12:
        _expected("target_day out of range")
    if d < 1 or d > _days_in_month(y, m):
        _expected("target_day is not a real calendar date")
    return _days_from_civil(y, m, d)


def format_day(day_index: int) -> str:
    y, m, d = _civil_from_days(day_index)
    return "%04d-%02d-%02d" % (y, m, d)


def format_day_us(day_index: int) -> str:
    y, m, d = _civil_from_days(day_index)
    return "%02d/%02d/%04d" % (m, d, y)


def parse_iso_utc(s: str) -> int:
    """Parse the consensus transaction datetime into Unix seconds.

    Accepts ``YYYY-MM-DD`` + ``T``/space + ``HH:MM:SS`` with an optional
    fractional part and an optional ``Z`` / ``+HH:MM`` / ``-HH:MM`` offset.
    """
    if len(s) < 19:
        _invariant("unparseable transaction datetime")
    date_part = s[0:10]
    if s[10] != "T" and s[10] != " ":
        _invariant("unparseable transaction datetime")
    rest = s[11:]

    offset = 0
    if rest.endswith("Z") or rest.endswith("z"):
        rest = rest[:-1]
    else:
        sign = 0
        cut = -1
        for i in range(len(rest) - 1, -1, -1):
            if rest[i] == "+":
                sign = 1
                cut = i
                break
            if rest[i] == "-":
                sign = -1
                cut = i
                break
        if cut >= 0:
            tz = rest[cut + 1 :].replace(":", "")
            rest = rest[:cut]
            if len(tz) == 4 and _all_digits(tz):
                offset = sign * (int(tz[0:2]) * 3600 + int(tz[2:4]) * 60)
            elif len(tz) == 2 and _all_digits(tz):
                offset = sign * int(tz) * 3600
            else:
                _invariant("unparseable transaction datetime offset")

    dot = rest.find(".")
    if dot >= 0:
        rest = rest[:dot]
    if len(rest) != 8 or rest[2] != ":" or rest[5] != ":":
        _invariant("unparseable transaction time")

    ys = date_part[0:4]
    ms = date_part[5:7]
    ds = date_part[8:10]
    hh = rest[0:2]
    mi = rest[3:5]
    ss = rest[6:8]
    if not (
        _all_digits(ys)
        and _all_digits(ms)
        and _all_digits(ds)
        and _all_digits(hh)
        and _all_digits(mi)
        and _all_digits(ss)
    ):
        _invariant("unparseable transaction datetime digits")

    days = _days_from_civil(int(ys), int(ms), int(ds))
    return days * DAY + int(hh) * 3600 + int(mi) * 60 + int(ss) - offset


def window_for_day(day_index: int) -> tuple:
    """GMT+1 calendar day -> ``[start, end)`` in Unix seconds."""
    start = day_index * DAY - GMT_PLUS_ONE
    return (start, start + DAY)


# ---------------------------------------------------------------------------
# Exact decimal -> scaled integer. No floats anywhere in settlement.
# ---------------------------------------------------------------------------


def dec_to_scaled(raw, scale_digits: int = 8) -> int:
    """Parse a decimal *string* (or JSON int) into an integer scaled by 10**8.

    Truncates toward zero. Tolerates ``$`` and thousands separators so the
    stock feeds' money strings parse without a float ever being constructed.
    """
    if isinstance(raw, bool):
        _external("non-numeric price")
    if isinstance(raw, int):
        return raw * (10**scale_digits)
    if not isinstance(raw, str):
        _external("non-numeric price")

    s = raw.strip().replace("$", "").replace(",", "").replace("_", "")
    if s == "":
        _external("empty price")

    neg = False
    if s[0] == "+":
        s = s[1:]
    elif s[0] == "-":
        neg = True
        s = s[1:]

    exp = 0
    idx = s.find("e")
    if idx < 0:
        idx = s.find("E")
    if idx >= 0:
        exp_part = s[idx + 1 :]
        s = s[:idx]
        if exp_part.startswith("+"):
            exp_part = exp_part[1:]
        eneg = exp_part.startswith("-")
        if eneg:
            exp_part = exp_part[1:]
        if not _all_digits(exp_part):
            _external("bad price exponent")
        exp = -int(exp_part) if eneg else int(exp_part)

    dot = s.find(".")
    if dot >= 0:
        int_part = s[:dot]
        frac_part = s[dot + 1 :]
    else:
        int_part = s
        frac_part = ""
    if int_part == "":
        int_part = "0"
    if not _all_digits(int_part):
        _external("bad price mantissa")
    if frac_part != "" and not _all_digits(frac_part):
        _external("bad price fraction")

    digits = int(int_part + frac_part)
    power = exp - len(frac_part) + scale_digits
    if power >= 0:
        value = digits * (10**power)
    else:
        value = digits // (10 ** (-power))
    return -value if neg else value


# ---------------------------------------------------------------------------
# Locked source URLs
# ---------------------------------------------------------------------------


def coingecko_url(asset: str, win_start: int, win_end: int) -> str:
    return (
        "https://api.coingecko.com/api/v3/coins/"
        + COINGECKO_IDS[asset]
        + "/market_chart/range?vs_currency=usd&from="
        + str(win_start - HOUR)
        + "&to="
        + str(win_end + HOUR)
    )


def binance_url(asset: str, win_start: int, win_end: int) -> str:
    # data-api.binance.vision is the unrestricted public market-data host.
    # api.binance.com answers 451 from restricted regions, which would split
    # any validator that happens to sit in one of them.
    return (
        "https://data-api.binance.vision/api/v3/klines?symbol="
        + BINANCE_PAIRS[asset]
        + "&interval=1h&startTime="
        + str(win_start * 1000)
        + "&endTime="
        + str((win_end - 1) * 1000)
        + "&limit=24"
    )


def stockanalysis_url(asset: str, day_index: int) -> str:
    return "https://stockanalysis.com/api/symbol/s/" + asset.lower() + "/history"


def nasdaq_url(asset: str, day_index: int) -> str:
    # The endpoint rejects fromdate == todate, so it always asks for D..D+1
    # and the parser selects the row dated D.
    return (
        "https://api.nasdaq.com/api/quote/"
        + asset
        + "/historical?assetclass=stocks&fromdate="
        + format_day(day_index)
        + "&todate="
        + format_day(day_index + 1)
        + "&limit=10"
    )


# ---------------------------------------------------------------------------
# Source readers. Each one reconstructs the window from that source's own
# bytes only, so neither source can ever see the other's numbers.
# ---------------------------------------------------------------------------


def classify_response(status: int, body) -> str:
    """HTTP response -> decoded text, or a classified revert."""
    if status == 408 or status == 425 or status == 429 or status >= 500:
        _transient("source http " + str(status))
    if status != 200:
        _external("source http " + str(status))
    if body is None or len(body) == 0:
        _transient("source returned an empty body")
    if len(body) > MAX_SOURCE_BYTES:
        _external("source body exceeds " + str(MAX_SOURCE_BYTES) + " bytes")
    try:
        return body.decode("utf-8")
    except Exception:
        _external("source body is not utf-8")
    return ""


def _load_json(text: str):
    # parse_float=str keeps every decimal as its original text, so no float is
    # ever constructed from a price.
    try:
        return json.loads(text, parse_float=str)
    except Exception:
        _external("source returned malformed json")
    return None


def _as_int(v) -> int:
    if isinstance(v, bool):
        _external("expected a timestamp")
    if isinstance(v, int):
        return v
    if isinstance(v, str) and _all_digits(v):
        return int(v)
    _external("expected a timestamp")
    return 0


def coingecko_window(text: str, win_start: int, win_end: int) -> tuple:
    """First sample at/after window start, last sample before window end."""
    obj = _load_json(text)
    if not isinstance(obj, dict):
        _external("coingecko payload is not an object")
    prices = obj.get("prices")
    if not isinstance(prices, list) or len(prices) == 0:
        _external("coingecko returned no prices")

    first_ts = -1
    last_ts = -1
    open_v = 0
    close_v = 0
    for item in prices:
        if not isinstance(item, list) or len(item) < 2:
            _external("coingecko sample is malformed")
        ts = _as_int(item[0]) // 1000
        if ts < win_start or ts >= win_end:
            continue
        if first_ts < 0 or ts < first_ts:
            first_ts = ts
            open_v = dec_to_scaled(item[1])
        if ts > last_ts:
            last_ts = ts
            close_v = dec_to_scaled(item[1])

    if first_ts < 0 or last_ts < 0:
        _external("coingecko has no sample inside the window")
    if first_ts - win_start > HOUR:
        _external("coingecko window is missing its opening hour")
    if win_end - last_ts > 2 * HOUR:
        _external("coingecko window is missing its closing hour")
    if open_v <= 0 or close_v <= 0:
        _external("coingecko returned a non-positive price")
    return (open_v, close_v)


def binance_window(text: str, win_start: int, win_end: int) -> tuple:
    """24 consecutive hourly klines covering the GMT+1 day exactly."""
    arr = _load_json(text)
    if not isinstance(arr, list):
        _external("binance payload is not a list")
    if len(arr) != 24:
        _external("binance returned " + str(len(arr)) + " of 24 hourly klines")
    first = arr[0]
    last = arr[23]
    if not isinstance(first, list) or len(first) < 5:
        _external("binance kline is malformed")
    if not isinstance(last, list) or len(last) < 5:
        _external("binance kline is malformed")
    if _as_int(first[0]) // 1000 != win_start:
        _external("binance window does not start on the GMT+1 day")
    if _as_int(last[0]) // 1000 != win_end - HOUR:
        _external("binance window does not end on the GMT+1 day")
    open_v = dec_to_scaled(first[1])
    close_v = dec_to_scaled(last[4])
    if open_v <= 0 or close_v <= 0:
        _external("binance returned a non-positive price")
    return (open_v, close_v)


def stockanalysis_day(text: str, day_index: int) -> tuple:
    obj = _load_json(text)
    data = obj.get("data") if isinstance(obj, dict) else None
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) == 0:
        _external("stockanalysis returned no rows")
    target = format_day(day_index)
    for r in rows:
        if isinstance(r, dict) and r.get("t") == target:
            open_v = dec_to_scaled(r.get("o"))
            close_v = dec_to_scaled(r.get("c"))
            if open_v <= 0 or close_v <= 0:
                _external("stockanalysis returned a non-positive price")
            return (open_v, close_v)
    _external("stockanalysis has no session dated " + target)
    return (0, 0)


def nasdaq_day(text: str, day_index: int) -> tuple:
    obj = _load_json(text)
    data = obj.get("data") if isinstance(obj, dict) else None
    if not isinstance(data, dict):
        _external("nasdaq returned no data")
    table = data.get("tradesTable")
    rows = table.get("rows") if isinstance(table, dict) else None
    if not isinstance(rows, list) or len(rows) == 0:
        _external("nasdaq returned no rows")
    target = format_day_us(day_index)
    for r in rows:
        if isinstance(r, dict) and r.get("date") == target:
            open_v = dec_to_scaled(r.get("open"))
            close_v = dec_to_scaled(r.get("close"))
            if open_v <= 0 or close_v <= 0:
                _external("nasdaq returned a non-positive price")
            return (open_v, close_v)
    _external("nasdaq has no session dated " + target)
    return (0, 0)


# ---------------------------------------------------------------------------
# Outcome math -- applied per source, to that source's own prices.
# ---------------------------------------------------------------------------


def direction_of(open_v: int, close_v: int) -> str:
    """A flat day counts as DOWN, so there is no third directional outcome."""
    return UP if close_v > open_v else DOWN


def return_bps(open_v: int, close_v: int) -> int:
    if open_v <= 0:
        _external("cannot compute a return from a non-positive open")
    return ((close_v - open_v) * BPS) // open_v


def winner_of(symbols: tuple, opens: list, closes: list) -> str:
    """Strictly greatest return wins. A tie for first makes this source TIE."""
    best = 0
    best_sym = ""
    tied = False
    for i in range(len(symbols)):
        b = return_bps(opens[i], closes[i])
        if best_sym == "" or b > best:
            best = b
            best_sym = symbols[i]
            tied = False
        elif b == best:
            tied = True
    if best_sym == "":
        _external("no assets to rank")
    return TIE if tied else best_sym


def combine(a_verdict: str, b_verdict: str) -> str:
    """Both sources must independently produce the same verdict."""
    if a_verdict == "" or b_verdict == "":
        return INCONCLUSIVE
    if a_verdict == TIE or b_verdict == TIE:
        return INCONCLUSIVE
    if a_verdict == INCONCLUSIVE or b_verdict == INCONCLUSIVE:
        return INCONCLUSIVE
    return a_verdict if a_verdict == b_verdict else INCONCLUSIVE


# ---------------------------------------------------------------------------
# Canonical consensus payload
#
#   v1|kind|category|asset|src_a|src_b|day|A_SERIES|a_verdict|B_SERIES|b_verdict|final
#
# where SERIES is comma joined "SYM:open:close" using PRICE_SCALE integers.
# Every field that gets persisted is inside this string, and nothing outside
# it is ever written to storage.
# ---------------------------------------------------------------------------


def build_series(symbols: tuple, opens: list, closes: list) -> str:
    parts = []
    for i in range(len(symbols)):
        parts.append(symbols[i] + ":" + str(opens[i]) + ":" + str(closes[i]))
    return ",".join(parts)


def parse_series(s: str, expect: tuple) -> tuple:
    entries = s.split(",")
    if len(entries) != len(expect):
        _invariant("agreed series has the wrong entry count")
    opens = []
    closes = []
    for i in range(len(entries)):
        bits = entries[i].split(":")
        if len(bits) != 3:
            _invariant("agreed series entry is malformed")
        if bits[0] != expect[i]:
            _invariant("agreed series symbol does not match the catalog")
        if not _all_digits(bits[1]) or not _all_digits(bits[2]):
            _invariant("agreed series price is not an integer")
        o = int(bits[1])
        c = int(bits[2])
        if o <= 0 or c <= 0:
            _invariant("agreed series price is not positive")
        opens.append(o)
        closes.append(c)
    return (opens, closes)


def build_payload(
    kind: str,
    category: str,
    asset: str,
    day_index: int,
    symbols: tuple,
    a_opens: list,
    a_closes: list,
    b_opens: list,
    b_closes: list,
) -> str:
    src_a, src_b = category_sources(category)
    if kind == KIND_DIRECTION:
        a_verdict = direction_of(a_opens[0], a_closes[0])
        b_verdict = direction_of(b_opens[0], b_closes[0])
    else:
        a_verdict = winner_of(symbols, a_opens, a_closes)
        b_verdict = winner_of(symbols, b_opens, b_closes)
    final = combine(a_verdict, b_verdict)
    return "|".join(
        [
            PAYLOAD_VERSION,
            kind,
            category,
            asset,
            src_a,
            src_b,
            str(day_index),
            build_series(symbols, a_opens, a_closes),
            a_verdict,
            build_series(symbols, b_opens, b_closes),
            b_verdict,
            final,
        ]
    )


def parse_agreed(payload: str, kind: str, category: str, asset: str, day_index: int) -> dict:
    """Re-derive every decision from the agreed payload after consensus.

    This runs in deterministic code with no network access. It proves that the
    stored outcome follows from the stored prices, so a malformed or tampered
    payload can never be persisted.
    """
    fields = payload.split("|")
    if len(fields) != PAYLOAD_FIELDS:
        _invariant("agreed payload has the wrong field count")
    if fields[0] != PAYLOAD_VERSION:
        _invariant("agreed payload version is unknown")

    symbols = category_assets(category)
    if kind == KIND_DIRECTION:
        expect = (asset,)
    else:
        expect = symbols

    src_a, src_b = category_sources(category)
    if fields[1] != kind:
        _invariant("agreed payload kind does not bind to this market")
    if fields[2] != category:
        _invariant("agreed payload category does not bind to this market")
    if fields[3] != (asset if kind == KIND_DIRECTION else ""):
        _invariant("agreed payload asset does not bind to this market")
    if fields[4] != src_a or fields[5] != src_b:
        _invariant("agreed payload sources do not bind to this market")
    if fields[6] != str(day_index):
        _invariant("agreed payload day does not bind to this market")

    a_opens, a_closes = parse_series(fields[7], expect)
    b_opens, b_closes = parse_series(fields[9], expect)

    if kind == KIND_DIRECTION:
        a_expected = direction_of(a_opens[0], a_closes[0])
        b_expected = direction_of(b_opens[0], b_closes[0])
    else:
        a_expected = winner_of(expect, a_opens, a_closes)
        b_expected = winner_of(expect, b_opens, b_closes)

    if fields[8] != a_expected:
        _invariant("source A verdict contradicts source A prices")
    if fields[10] != b_expected:
        _invariant("source B verdict contradicts source B prices")

    final = combine(fields[8], fields[10])
    if fields[11] != final:
        _invariant("final result contradicts the two source verdicts")

    if final != INCONCLUSIVE:
        if kind == KIND_DIRECTION:
            if final != UP and final != DOWN:
                _invariant("directional result is neither UP nor DOWN")
        else:
            if final not in symbols:
                _invariant("winner is not in the category catalog")

    return {
        "a_opens": a_opens,
        "a_closes": a_closes,
        "a_verdict": fields[8],
        "b_opens": b_opens,
        "b_closes": b_closes,
        "b_verdict": fields[10],
        "final": final,
        "source_a": src_a,
        "source_b": src_b,
    }


# ---------------------------------------------------------------------------
# Storage records
# ---------------------------------------------------------------------------


@allow_storage
@dataclass
class MarketRecord:
    id: u256
    kind: str
    category: str
    asset: str
    target_day: u256
    created_at: u256
    cutoff_at: u256
    settles_at: u256
    terminal_refund_at: u256
    creator: Address
    up_pool: u256
    down_pool: u256
    pool0: u256
    pool1: u256
    pool2: u256
    pool3: u256
    position_count: u256
    paid_out: u256
    state: str
    result: str
    refund_all: bool
    resolved_at: u256


@allow_storage
@dataclass
class PositionRecord:
    market_id: u256
    owner: Address
    side: str
    stake: u256
    claimed: bool


@allow_storage
@dataclass
class SettlementEvidence:
    market_id: u256
    kind: str
    category: str
    target_day: u256
    source_a: str
    source_b: str
    a_verdict: str
    b_verdict: str
    final_result: str
    terminal_refund: bool
    resolved_at: u256
    payload: str


@allow_storage
@dataclass
class ActivityRecord:
    seq: u256
    kind: str
    market_id: u256
    actor: Address
    detail: str
    amount: u256
    at: u256


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass

    class Write:
        pass


def addr_key(a: Address) -> str:
    return "0x" + a.as_bytes.hex()


def _wei(v) -> str:
    # Views return wei as decimal strings: 6 GEN exceeds JS Number precision.
    return str(int(v))


class Contract(gl.Contract):
    markets: TreeMap[u256, MarketRecord]
    positions: TreeMap[str, PositionRecord]
    evidence: TreeMap[u256, SettlementEvidence]

    unique_index: TreeMap[str, u256]
    market_seq: TreeMap[u256, u256]
    user_markets: TreeMap[str, u256]
    user_market_count: TreeMap[str, u256]
    user_positions: TreeMap[str, u256]
    user_position_count: TreeMap[str, u256]
    market_positions: TreeMap[str, str]
    activity: TreeMap[u256, ActivityRecord]

    next_id: u256
    market_count: u256
    activity_count: u256

    def __init__(self):
        self.next_id = u256(1)
        self.market_count = u256(0)
        self.activity_count = u256(0)

    # -- internal helpers ---------------------------------------------------

    def _now(self) -> int:
        return parse_iso_utc(gl.message_raw["datetime"])

    def _log(self, kind: str, market_id: int, detail: str, amount: int, at: int) -> None:
        seq = int(self.activity_count)
        self.activity[u256(seq)] = ActivityRecord(
            seq=u256(seq),
            kind=kind,
            market_id=u256(market_id),
            actor=gl.message.sender_address,
            detail=detail,
            amount=u256(amount),
            at=u256(at),
        )
        self.activity_count = u256(seq + 1)

    def _market_or_revert(self, market_id: u256) -> MarketRecord:
        m = self.markets.get(u256(int(market_id)), None)
        if m is None:
            _expected("unknown market")
        return m

    def _pool_of(self, m: MarketRecord, side: str) -> int:
        if m.kind == KIND_DIRECTION:
            return int(m.up_pool) if side == UP else int(m.down_pool)
        idx = self._asset_index(m.category, side)
        if idx == 0:
            return int(m.pool0)
        if idx == 1:
            return int(m.pool1)
        if idx == 2:
            return int(m.pool2)
        return int(m.pool3)

    def _add_pool(self, m: MarketRecord, side: str, amount: int) -> None:
        if m.kind == KIND_DIRECTION:
            if side == UP:
                m.up_pool = u256(int(m.up_pool) + amount)
            else:
                m.down_pool = u256(int(m.down_pool) + amount)
            return
        idx = self._asset_index(m.category, side)
        if idx == 0:
            m.pool0 = u256(int(m.pool0) + amount)
        elif idx == 1:
            m.pool1 = u256(int(m.pool1) + amount)
        elif idx == 2:
            m.pool2 = u256(int(m.pool2) + amount)
        else:
            m.pool3 = u256(int(m.pool3) + amount)

    def _asset_index(self, category: str, symbol: str) -> int:
        symbols = category_assets(category)
        for i in range(len(symbols)):
            if symbols[i] == symbol:
                return i
        _expected("unknown asset for this category")
        return -1

    def _total_pool(self, m: MarketRecord) -> int:
        if m.kind == KIND_DIRECTION:
            return int(m.up_pool) + int(m.down_pool)
        return int(m.pool0) + int(m.pool1) + int(m.pool2) + int(m.pool3)

    def _phase(self, m: MarketRecord, now: int) -> str:
        if m.state == STATE_INCONCLUSIVE:
            return PHASE_INCONCLUSIVE
        if m.state == STATE_SETTLED:
            if m.result == UP:
                return PHASE_SETTLED_UP
            if m.result == DOWN:
                return PHASE_SETTLED_DOWN
            return PHASE_SETTLED_WINNER
        if now < int(m.cutoff_at):
            return PHASE_OPEN
        if now < int(m.settles_at):
            return PHASE_WINDOW_LIVE
        return PHASE_READY

    def _payout_for(self, m: MarketRecord, p: PositionRecord) -> int:
        stake = int(p.stake)
        if m.state == STATE_UNRESOLVED:
            _expected("market is not resolved yet")
        if m.refund_all or m.state == STATE_INCONCLUSIVE:
            return stake
        winner_pool = self._pool_of(m, m.result)
        if winner_pool <= 0:
            # Nobody backed the winning outcome: everyone gets their stake back.
            return stake
        if p.side != m.result:
            return 0
        return (stake * self._total_pool(m)) // winner_pool

    # -- writes -------------------------------------------------------------

    @gl.public.write
    def create_market(self, kind: str, category: str, asset: str, target_day: str) -> u256:
        if kind != KIND_DIRECTION and kind != KIND_RELATIVE:
            _expected("kind must be A or B")
        if category != CAT_CRYPTO and category != CAT_STOCKS:
            _expected("category must be CRYPTO or STOCKS")

        symbols = category_assets(category)
        if kind == KIND_DIRECTION:
            if asset not in symbols:
                _expected("asset is not in this category")
        else:
            if asset != "":
                _expected("kind B markets cover the whole category, pass an empty asset")

        day_index = parse_day_string(target_day)
        win_start, win_end = window_for_day(day_index)
        now = self._now()

        if win_start <= now:
            _expected("target day must start in the future")
        if win_start - now > MAX_FORWARD_DAYS * DAY:
            _expected("target day is more than " + str(MAX_FORWARD_DAYS) + " days ahead")

        unique = category + "|" + (asset if kind == KIND_DIRECTION else "*") + "|" + target_day
        if self.unique_index.get(unique, None) is not None:
            _expected("a market for this asset and day already exists")

        market_id = int(self.next_id)
        self.markets[u256(market_id)] = MarketRecord(
            id=u256(market_id),
            kind=kind,
            category=category,
            asset=asset,
            target_day=u256(day_index),
            created_at=u256(now),
            cutoff_at=u256(win_start),
            settles_at=u256(win_end),
            terminal_refund_at=u256(win_end + TERMINAL_REFUND_DELAY),
            creator=gl.message.sender_address,
            up_pool=u256(0),
            down_pool=u256(0),
            pool0=u256(0),
            pool1=u256(0),
            pool2=u256(0),
            pool3=u256(0),
            position_count=u256(0),
            paid_out=u256(0),
            state=STATE_UNRESOLVED,
            result="",
            refund_all=False,
            resolved_at=u256(0),
        )
        self.unique_index[unique] = u256(market_id)

        seq = int(self.market_count)
        self.market_seq[u256(seq)] = u256(market_id)
        self.market_count = u256(seq + 1)

        creator = addr_key(gl.message.sender_address)
        ucount = int(self.user_market_count.get(creator, u256(0)))
        self.user_markets[creator + ":" + str(ucount)] = u256(market_id)
        self.user_market_count[creator] = u256(ucount + 1)

        self.next_id = u256(market_id + 1)
        self._log("CREATE", market_id, kind + "/" + category, 0, now)
        return u256(market_id)

    @gl.public.write.payable
    def take_position(self, market_id: u256, side: str) -> u256:
        value = int(gl.message.value)
        m = self._market_or_revert(market_id)
        now = self._now()

        if m.state != STATE_UNRESOLVED:
            _expected("market is already resolved")
        if now >= int(m.cutoff_at):
            _expected("market is closed for new positions")

        if m.kind == KIND_DIRECTION:
            if side != UP and side != DOWN:
                _expected("side must be UP or DOWN")
        else:
            if side not in category_assets(m.category):
                _expected("side must be an asset in this category")

        owner = gl.message.sender_address
        key = str(int(market_id)) + ":" + addr_key(owner)
        existing = self.positions.get(key, None)

        if existing is None:
            if value < MIN_STAKE:
                _expected("first stake must be at least 2 GEN")
            if value > MAX_STAKE:
                _expected("stake must not exceed 6 GEN")
            self.positions[key] = PositionRecord(
                market_id=u256(int(market_id)),
                owner=owner,
                side=side,
                stake=u256(value),
                claimed=False,
            )
            pcount = int(m.position_count)
            self.market_positions[str(int(market_id)) + ":" + str(pcount)] = key
            m.position_count = u256(pcount + 1)

            ukey = addr_key(owner)
            ucount = int(self.user_position_count.get(ukey, u256(0)))
            self.user_positions[ukey + ":" + str(ucount)] = u256(int(market_id))
            self.user_position_count[ukey] = u256(ucount + 1)
            total = value
        else:
            if existing.side != side:
                _expected("cannot switch sides, top up the side you already hold")
            if value <= 0:
                _expected("top up must send value")
            total = int(existing.stake) + value
            if total > MAX_STAKE:
                _expected("total stake must not exceed 6 GEN")
            existing.stake = u256(total)

        self._add_pool(m, side, value)
        self._log("STAKE", int(market_id), side, value, now)
        return u256(total)

    @gl.public.write
    def resolve_market(self, market_id: u256) -> str:
        m = self._market_or_revert(market_id)
        if m.state != STATE_UNRESOLVED:
            _expected("market is already resolved")

        now = self._now()
        if now < int(m.settles_at):
            _expected("the GMT+1 day has not finished yet")

        kind = m.kind
        category = m.category
        asset = m.asset
        day_index = int(m.target_day)

        # Terminal refund: past the deadline the contract stops asking the web
        # anything at all and refunds every stake. It never invents a price.
        if now >= int(m.terminal_refund_at):
            src_a, src_b = category_sources(category)
            self.evidence[u256(int(market_id))] = SettlementEvidence(
                market_id=u256(int(market_id)),
                kind=kind,
                category=category,
                target_day=u256(day_index),
                source_a=src_a,
                source_b=src_b,
                a_verdict="",
                b_verdict="",
                final_result=INCONCLUSIVE,
                terminal_refund=True,
                resolved_at=u256(now),
                payload="",
            )
            m.state = STATE_INCONCLUSIVE
            m.result = INCONCLUSIVE
            m.refund_all = True
            m.resolved_at = u256(now)
            self._log("RESOLVE", int(market_id), "TERMINAL_REFUND", 0, now)
            return INCONCLUSIVE

        win_start, win_end = window_for_day(day_index)
        symbols = (asset,) if kind == KIND_DIRECTION else category_assets(category)

        def read_sources() -> str:
            a_opens = []
            a_closes = []
            b_opens = []
            b_closes = []
            for sym in symbols:
                if category == CAT_CRYPTO:
                    ra = gl.nondet.web.get(
                        coingecko_url(sym, win_start, win_end), headers=REQUEST_HEADERS
                    )
                    oa, ca = coingecko_window(
                        classify_response(ra.status, ra.body), win_start, win_end
                    )
                    rb = gl.nondet.web.get(
                        binance_url(sym, win_start, win_end), headers=REQUEST_HEADERS
                    )
                    ob, cb = binance_window(
                        classify_response(rb.status, rb.body), win_start, win_end
                    )
                else:
                    ra = gl.nondet.web.get(
                        stockanalysis_url(sym, day_index), headers=REQUEST_HEADERS
                    )
                    oa, ca = stockanalysis_day(
                        classify_response(ra.status, ra.body), day_index
                    )
                    rb = gl.nondet.web.get(
                        nasdaq_url(sym, day_index), headers=REQUEST_HEADERS
                    )
                    ob, cb = nasdaq_day(classify_response(rb.status, rb.body), day_index)
                a_opens.append(oa)
                a_closes.append(ca)
                b_opens.append(ob)
                b_closes.append(cb)
            return build_payload(
                kind, category, asset, day_index, symbols, a_opens, a_closes, b_opens, b_closes
            )

        payload = gl.eq_principle.strict_eq(read_sources)

        # Consensus is done. Nothing below this line touches the network.
        agreed = parse_agreed(payload, kind, category, asset, day_index)
        final = agreed["final"]

        self.evidence[u256(int(market_id))] = SettlementEvidence(
            market_id=u256(int(market_id)),
            kind=kind,
            category=category,
            target_day=u256(day_index),
            source_a=agreed["source_a"],
            source_b=agreed["source_b"],
            a_verdict=agreed["a_verdict"],
            b_verdict=agreed["b_verdict"],
            final_result=final,
            terminal_refund=False,
            resolved_at=u256(now),
            payload=payload,
        )

        if final == INCONCLUSIVE:
            m.state = STATE_INCONCLUSIVE
            m.result = INCONCLUSIVE
            m.refund_all = True
        else:
            m.state = STATE_SETTLED
            m.result = final
            m.refund_all = self._pool_of(m, final) <= 0
        m.resolved_at = u256(now)
        self._log("RESOLVE", int(market_id), final, 0, now)
        return final

    @gl.public.write
    def claim(self, market_id: u256) -> u256:
        owner = gl.message.sender_address
        key = str(int(market_id)) + ":" + addr_key(owner)
        p = self.positions.get(key, None)
        if p is None:
            _expected("no position on this market")
        if p.owner.as_bytes != owner.as_bytes:
            _expected("only the position owner can claim")
        if p.claimed:
            _expected("position is already claimed")

        m = self._market_or_revert(market_id)
        amount = self._payout_for(m, p)
        now = self._now()

        if amount > 0:
            # Transfer first. If the send reverts the whole transaction rolls
            # back, claimed stays false and the owner can retry.
            _Recipient(owner).emit_transfer(value=u256(amount))
            m.paid_out = u256(int(m.paid_out) + amount)

        p.claimed = True
        self._log("CLAIM", int(market_id), p.side, amount, now)
        return u256(amount)

    # -- views --------------------------------------------------------------

    def _market_view(self, m: MarketRecord, now: int) -> dict:
        day_index = int(m.target_day)
        symbols = category_assets(m.category)
        pools = {}
        if m.kind == KIND_DIRECTION:
            pools = {UP: _wei(m.up_pool), DOWN: _wei(m.down_pool)}
        else:
            pools = {
                symbols[0]: _wei(m.pool0),
                symbols[1]: _wei(m.pool1),
                symbols[2]: _wei(m.pool2),
                symbols[3]: _wei(m.pool3),
            }
        leader = ""
        best = -1
        for k in pools:
            v = int(pools[k])
            if v > best:
                best = v
                leader = k
            elif v == best:
                leader = ""
        src_a, src_b = category_sources(m.category)
        return {
            "id": int(m.id),
            "kind": m.kind,
            "category": m.category,
            "asset": m.asset,
            "universe": list(symbols),
            "target_day": format_day(day_index),
            "target_day_index": day_index,
            "created_at": int(m.created_at),
            "cutoff_at": int(m.cutoff_at),
            "settles_at": int(m.settles_at),
            "terminal_refund_at": int(m.terminal_refund_at),
            "creator": addr_key(m.creator),
            "pools": pools,
            "total_pool": _wei(self._total_pool(m)),
            "leading": leader,
            "position_count": int(m.position_count),
            "paid_out": _wei(m.paid_out),
            "state": m.state,
            "result": m.result,
            "refund_all": bool(m.refund_all),
            "resolved_at": int(m.resolved_at),
            "phase": self._phase(m, now),
            "source_a": src_a,
            "source_b": src_b,
            "now": now,
        }

    @gl.public.view
    def get_supported_universe(self) -> dict:
        return {
            "kinds": [
                {"id": KIND_DIRECTION, "label": "Daily direction"},
                {"id": KIND_RELATIVE, "label": "Daily relative return"},
            ],
            "categories": [
                {
                    "id": CAT_CRYPTO,
                    "assets": list(CRYPTO_ASSETS),
                    "source_a": SRC_COINGECKO,
                    "source_b": SRC_BINANCE,
                },
                {
                    "id": CAT_STOCKS,
                    "assets": list(STOCKS_ASSETS),
                    "source_a": SRC_STOCKANALYSIS,
                    "source_b": SRC_NASDAQ,
                },
            ],
            "min_stake": _wei(MIN_STAKE),
            "max_stake": _wei(MAX_STAKE),
            "price_scale": PRICE_SCALE,
            "utc_offset_seconds": GMT_PLUS_ONE,
            "max_forward_days": MAX_FORWARD_DAYS,
            "terminal_refund_delay": TERMINAL_REFUND_DELAY,
            "max_page": MAX_PAGE,
        }

    @gl.public.view
    def get_market(self, market_id: u256) -> dict:
        m = self.markets.get(u256(int(market_id)), None)
        if m is None:
            return {"found": False}
        view = self._market_view(m, self._now())
        view["found"] = True
        return view

    @gl.public.view
    def get_market_phase(self, market_id: u256) -> str:
        m = self._market_or_revert(market_id)
        return self._phase(m, self._now())

    @gl.public.view
    def get_position(self, market_id: u256, wallet: str) -> dict:
        key = str(int(market_id)) + ":" + addr_key(Address(wallet))
        p = self.positions.get(key, None)
        if p is None:
            return {"found": False, "side": "", "stake": "0", "claimed": False}
        return {
            "found": True,
            "market_id": int(p.market_id),
            "owner": addr_key(p.owner),
            "side": p.side,
            "stake": _wei(p.stake),
            "claimed": bool(p.claimed),
        }

    @gl.public.view
    def get_claimable(self, market_id: u256, wallet: str) -> dict:
        key = str(int(market_id)) + ":" + addr_key(Address(wallet))
        p = self.positions.get(key, None)
        if p is None:
            return {"claimable": "0", "reason": "no position"}
        m = self.markets.get(u256(int(market_id)), None)
        if m is None:
            return {"claimable": "0", "reason": "unknown market"}
        if m.state == STATE_UNRESOLVED:
            return {"claimable": "0", "reason": "not resolved"}
        if p.claimed:
            return {"claimable": "0", "reason": "already claimed"}
        amount = self._payout_for(m, p)
        reason = "refund" if (m.refund_all or m.state == STATE_INCONCLUSIVE) else "win"
        if amount == 0:
            reason = "lost"
        return {"claimable": _wei(amount), "reason": reason, "side": p.side, "result": m.result}

    @gl.public.view
    def get_markets(self, offset: u256, limit: u256) -> dict:
        now = self._now()
        total = int(self.market_count)
        lim = min(int(limit), MAX_PAGE)
        i = total - 1 - int(offset)
        items = []
        while i >= 0 and len(items) < lim:
            mid = self.market_seq.get(u256(i), None)
            if mid is not None:
                m = self.markets.get(u256(int(mid)), None)
                if m is not None:
                    items.append(self._market_view(m, now))
            i -= 1
        return {"total": total, "offset": int(offset), "items": items}

    def _filtered(self, now: int, offset: int, limit: int, category: str, open_only: bool) -> dict:
        total = int(self.market_count)
        lim = min(limit, MAX_PAGE)
        # Bounded scan so a view can never run unbounded as the board grows.
        scan_cap = MAX_PAGE * 8
        scanned = 0
        matched = 0
        items = []
        i = total - 1
        while i >= 0 and len(items) < lim and scanned < scan_cap:
            scanned += 1
            mid = self.market_seq.get(u256(i), None)
            i -= 1
            if mid is None:
                continue
            m = self.markets.get(u256(int(mid)), None)
            if m is None:
                continue
            if category != "" and m.category != category:
                continue
            if open_only and self._phase(m, now) != PHASE_OPEN:
                continue
            matched += 1
            if matched <= offset:
                continue
            items.append(self._market_view(m, now))
        return {
            "total": total,
            "offset": offset,
            "scanned": scanned,
            "truncated": scanned >= scan_cap,
            "items": items,
        }

    @gl.public.view
    def get_open_markets(self, offset: u256, limit: u256) -> dict:
        return self._filtered(self._now(), int(offset), int(limit), "", True)

    @gl.public.view
    def get_markets_by_category(self, category: str, offset: u256, limit: u256) -> dict:
        if category != CAT_CRYPTO and category != CAT_STOCKS:
            _expected("category must be CRYPTO or STOCKS")
        return self._filtered(self._now(), int(offset), int(limit), category, False)

    @gl.public.view
    def get_market_by_unique_key(self, kind: str, category: str, asset: str, target_day: str) -> dict:
        unique = category + "|" + (asset if kind == KIND_DIRECTION else "*") + "|" + target_day
        mid = self.unique_index.get(unique, None)
        if mid is None:
            return {"found": False, "exists": False}
        return {"found": True, "exists": True, "market_id": int(mid)}

    @gl.public.view
    def get_user_markets(self, wallet: str, offset: u256, limit: u256) -> dict:
        now = self._now()
        ukey = addr_key(Address(wallet))
        total = int(self.user_market_count.get(ukey, u256(0)))
        lim = min(int(limit), MAX_PAGE)
        i = total - 1 - int(offset)
        items = []
        while i >= 0 and len(items) < lim:
            mid = self.user_markets.get(ukey + ":" + str(i), None)
            if mid is not None:
                m = self.markets.get(u256(int(mid)), None)
                if m is not None:
                    items.append(self._market_view(m, now))
            i -= 1
        return {"total": total, "offset": int(offset), "items": items}

    @gl.public.view
    def get_user_positions(self, wallet: str, offset: u256, limit: u256) -> dict:
        now = self._now()
        ukey = addr_key(Address(wallet))
        total = int(self.user_position_count.get(ukey, u256(0)))
        lim = min(int(limit), MAX_PAGE)
        i = total - 1 - int(offset)
        items = []
        while i >= 0 and len(items) < lim:
            mid = self.user_positions.get(ukey + ":" + str(i), None)
            i -= 1
            if mid is None:
                continue
            m = self.markets.get(u256(int(mid)), None)
            if m is None:
                continue
            p = self.positions.get(str(int(mid)) + ":" + ukey, None)
            if p is None:
                continue
            claimable = 0
            if m.state != STATE_UNRESOLVED and not p.claimed:
                claimable = self._payout_for(m, p)
            items.append(
                {
                    "market": self._market_view(m, now),
                    "side": p.side,
                    "stake": _wei(p.stake),
                    "claimed": bool(p.claimed),
                    "claimable": _wei(claimable),
                }
            )
        return {"total": total, "offset": int(offset), "items": items}

    @gl.public.view
    def get_market_positions(self, market_id: u256, offset: u256, limit: u256) -> dict:
        m = self._market_or_revert(market_id)
        total = int(m.position_count)
        lim = min(int(limit), MAX_PAGE)
        items = []
        i = int(offset)
        while i < total and len(items) < lim:
            key = self.market_positions.get(str(int(market_id)) + ":" + str(i), None)
            i += 1
            if key is None:
                continue
            p = self.positions.get(key, None)
            if p is None:
                continue
            items.append(
                {
                    "owner": addr_key(p.owner),
                    "side": p.side,
                    "stake": _wei(p.stake),
                    "claimed": bool(p.claimed),
                }
            )
        return {"total": total, "offset": int(offset), "items": items}

    @gl.public.view
    def get_settlement_evidence(self, market_id: u256) -> dict:
        e = self.evidence.get(u256(int(market_id)), None)
        if e is None:
            return {"found": False}
        # Rows are derived from the agreed payload itself, so what the UI shows
        # is exactly the string validators reached consensus on.
        rows = []
        if e.payload != "":
            fields = e.payload.split("|")
            if len(fields) == PAYLOAD_FIELDS:
                a_entries = fields[7].split(",")
                b_entries = fields[9].split(",")
                for i in range(len(a_entries)):
                    a_bits = a_entries[i].split(":")
                    b_bits = b_entries[i].split(":") if i < len(b_entries) else []
                    if len(a_bits) != 3 or len(b_bits) != 3:
                        continue
                    a_o = int(a_bits[1])
                    a_c = int(a_bits[2])
                    b_o = int(b_bits[1])
                    b_c = int(b_bits[2])
                    rows.append(
                        {
                            "symbol": a_bits[0],
                            "a_open": a_o,
                            "a_close": a_c,
                            "a_bps": return_bps(a_o, a_c),
                            "b_open": b_o,
                            "b_close": b_c,
                            "b_bps": return_bps(b_o, b_c),
                        }
                    )
        return {
            "found": True,
            "market_id": int(e.market_id),
            "kind": e.kind,
            "category": e.category,
            "target_day": format_day(int(e.target_day)),
            "source_a": e.source_a,
            "source_b": e.source_b,
            "rows": rows,
            "a_verdict": e.a_verdict,
            "b_verdict": e.b_verdict,
            "final_result": e.final_result,
            "terminal_refund": bool(e.terminal_refund),
            "resolved_at": int(e.resolved_at),
            "payload": e.payload,
            "price_scale": PRICE_SCALE,
        }

    @gl.public.view
    def get_activity(self, offset: u256, limit: u256) -> dict:
        total = int(self.activity_count)
        lim = min(int(limit), MAX_PAGE)
        i = total - 1 - int(offset)
        items = []
        while i >= 0 and len(items) < lim:
            a = self.activity.get(u256(i), None)
            i -= 1
            if a is None:
                continue
            items.append(
                {
                    "seq": int(a.seq),
                    "kind": a.kind,
                    "market_id": int(a.market_id),
                    "actor": addr_key(a.actor),
                    "detail": a.detail,
                    "amount": _wei(a.amount),
                    "at": int(a.at),
                }
            )
        return {"total": total, "offset": int(offset), "items": items}

    @gl.public.view
    def get_stats(self) -> dict:
        now = self._now()
        total = int(self.market_count)
        scan_cap = MAX_PAGE * 8
        open_count = 0
        live_count = 0
        ready_count = 0
        settled_count = 0
        open_pool = 0
        i = total - 1
        scanned = 0
        while i >= 0 and scanned < scan_cap:
            scanned += 1
            mid = self.market_seq.get(u256(i), None)
            i -= 1
            if mid is None:
                continue
            m = self.markets.get(u256(int(mid)), None)
            if m is None:
                continue
            ph = self._phase(m, now)
            if ph == PHASE_OPEN:
                open_count += 1
                open_pool += self._total_pool(m)
            elif ph == PHASE_WINDOW_LIVE:
                live_count += 1
                open_pool += self._total_pool(m)
            elif ph == PHASE_READY:
                ready_count += 1
            else:
                settled_count += 1
        return {
            "markets": total,
            "open": open_count,
            "window_live": live_count,
            "ready_to_settle": ready_count,
            "settled": settled_count,
            "open_pool": _wei(open_pool),
            "activity": int(self.activity_count),
            "scanned": scanned,
            "now": now,
        }
