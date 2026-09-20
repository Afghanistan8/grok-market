# Resolution

This document is self contained. After reading it you should be able to explain
why two validators, each making their own live HTTP requests at different
moments, end up writing the same `final_result` — and why a single feed can
never decide anything.

---

## 1. The window

Every market targets one **GMT+1 calendar day**, written `YYYY-MM-DD`.

GMT+1 here means a fixed +1 hour offset. It is not `Europe/Paris`, it is not a
timezone database entry, and it never shifts for daylight saving. A GMT+1 day
`D` is exactly this half-open interval in Unix seconds:

```
start = day_index(D) * 86400 - 3600      # D 00:00 GMT+1  ==  D-1 23:00 UTC
end   = start + 86400                    # D+1 00:00 GMT+1 (exclusive)
```

`day_index` is days since 1970-01-01, computed with a hand-rolled civil calendar
(`_days_from_civil`) so the contract never depends on a host clock or a tz
database. Consecutive windows tile perfectly: `end(D) == start(D+1)`.

Three timestamps follow from the window:

| Moment | Value | Meaning |
|---|---|---|
| `cutoff_at` | `start` | staking closes, the day begins |
| `settles_at` | `end` | the day is complete, `resolve_market` opens |
| `terminal_refund_at` | `end + 5 days` | the refund deadline |

All lifecycle time is read from `gl.message_raw['datetime']`, the consensus
transaction timestamp. Every validator re-executing the transaction sees the
identical string, so no node's wall clock can influence a phase decision.

---

## 2. The two sources

Sources are compile-time constants. A caller picks a catalog key; it can never
supply a URL, a price, a slug, a direction or a result.

### CRYPTO — BTC, ETH, SOL, XRP

**Source A — CoinGecko** (cross-exchange USD average)

```
https://api.coingecko.com/api/v3/coins/{id}/market_chart/range
    ?vs_currency=usd&from={start-3600}&to={end+3600}
```

ids: `bitcoin`, `ethereum`, `solana`, `ripple`.

The range is padded by one hour on each side so the window is fully covered even
if sampling drifts. The parser then discards the padding:

- **open** = the price of the *earliest* sample whose timestamp is `>= start`
- **close** = the price of the *latest* sample whose timestamp is `< end`

Selection is by timestamp, not array position, so array ordering cannot change
the outcome. If the first in-window sample is more than an hour after `start`,
or the last is more than two hours before `end`, the window is incomplete and
the read fails `EXTERNAL`.

**Source B — Binance** (BTCUSDT / ETHUSDT / SOLUSDT / XRPUSDT spot)

```
https://data-api.binance.vision/api/v3/klines
    ?symbol={PAIR}&interval=1h&startTime={start*1000}&endTime={(end-1)*1000}&limit=24
```

Two deliberate choices here:

- **`interval=1h`, not `1d`.** Binance daily bars are UTC-aligned. A UTC day is
  one hour out of step with a GMT+1 day, so a `1d` bar would settle the wrong
  window. The contract instead requires exactly 24 consecutive hourly klines,
  checks that the first kline opens exactly at `start` and the last opens
  exactly at `end - 3600`, then takes **open = first kline's open** and
  **close = last kline's close**. Anything other than 24 aligned bars fails
  `EXTERNAL`.
- **`data-api.binance.vision`, not `api.binance.com`.** The main host answers
  HTTP 451 to requests from restricted regions — including for public market
  data. Validators are geographically distributed, so that host would split
  consensus purely on validator location. The `.vision` host serves the same
  exchange data without the geo-block.

### STOCKS — AAPL, MSFT, NVDA, TSLA

**Source A — stockanalysis.com**

```
https://stockanalysis.com/api/symbol/s/{ticker_lower}/history
```

Returns roughly six months of daily bars as
`data.data[] = {t: "YYYY-MM-DD", o, c, h, l, v}`. The parser selects the row
whose `t` equals the target day and takes `o` and `c`.

**Source B — Nasdaq**

```
https://api.nasdaq.com/api/quote/{TICKER}/historical
    ?assetclass=stocks&fromdate={D}&todate={D+1}&limit=10
```

Returns `data.tradesTable.rows[] = {date: "MM/DD/YYYY", open: "$497.965",
close: "$493.78", ...}`. The parser selects the row whose `date` equals the
target day in US format and strips `$` and thousands separators.

`fromdate` and `todate` are **not** the same value: the endpoint rejects a
zero-length range with *"Provided date is less than from date"*. Asking for
`D..D+1` and then selecting the row dated `D` is the workaround.

Both stock feeds gate non-browser clients (Nasdaq blocks a default client
string; stockanalysis sits behind Cloudflare), so the contract sends a fixed
browser-like `User-Agent`, `Accept` and `Accept-Language` on every request.
These headers are part of the locked request, not caller input.

### Why the GMT+1 day is clean for US equities

A US regular session runs 09:30–16:00 New York time, which is 14:30–21:00 GMT+1
in summer and 15:30–22:00 GMT+1 in winter. Either way the entire session sits
inside the *same* GMT+1 calendar day, so the session dated `D` on the exchange
is exactly the session inside GMT+1 day `D`. No session is ever split across
two windows.

Weekends and market holidays have no session at all. Neither feed invents an
overnight print, so both simply have no row for that date and the read fails
`EXTERNAL` — which is retryable and eventually refunds. The contract never
fabricates a price for a day the market was closed.

---

## 3. Prices become exact integers

Every price is stored as an integer scaled by `PRICE_SCALE = 10**8`, truncated
toward zero. **No float is ever constructed from a feed number.**

JSON is parsed with `json.loads(text, parse_float=str)`, which hands the parser
the original number *text* rather than an IEEE-754 double. `dec_to_scaled` then
does pure integer arithmetic on the digits:

```
digits = int(integer_part + fraction_part)
power  = exponent - len(fraction_part) + 8
value  = digits * 10**power          if power >= 0
       = digits // 10**(-power)      otherwise
```

This matters for consensus: `80494.31000000` and `80494.31` are different bytes
but the same integer `8049431000000`. Two validators that receive differently
formatted responses still compute identical numbers.

---

## 4. Each source produces its own verdict

The verdict for a source is computed **only from that source's own open and
close**. The two sources never see each other's numbers.

### Kind A — daily direction

```
direction = UP if close > open else DOWN
```

A perfectly flat day resolves `DOWN`. There is no third directional outcome, so
the flat case has to fall somewhere, and it falls on the side that did not rise.

### Kind B — daily relative return

For each of the four assets in the category:

```
bps = ((close - open) * 10_000) // open
```

Because it is a ratio, `bps` is scale-free: a +1% move gives `100` whether the
asset trades at $1.40 or $80,000. The winner is the asset with the **strictly
greatest** `bps`. If two or more assets tie for first place on a source, that
source's verdict is `TIE`.

---

## 5. Two verdicts become one result

```
final = a_verdict                  if a_verdict == b_verdict and neither is TIE
      = INCONCLUSIVE               otherwise
```

Consequences, all deliberate:

- `UP` + `UP` → `UP`; `DOWN` + `DOWN` → `DOWN`
- `UP` + `DOWN` → `INCONCLUSIVE`, every stake refunded
- `ETH` + `ETH` → `ETH`; `ETH` + `XRP` → `INCONCLUSIVE`
- `TIE` on *either* source → `INCONCLUSIVE`, no winner can emerge
- an empty verdict from either source → `INCONCLUSIVE`

**A single source is never sufficient.** There is no code path in which one
feed's verdict becomes the stored result.

### Disagreement is normal, and it is not a bug

CoinGecko reports a cross-exchange USD average; Binance reports one USDT pair on
one venue. On a day with a large move both agree easily. On a *near-flat* day
they can genuinely differ in sign — a real run of `scripts/check_sources.py`
produced CoinGecko at −6 bps (DOWN) and Binance at +15 bps (UP) for the same BTC
day. The honest answer there is that the day had no clear direction, so the
contract refuses to pick one and refunds everyone. Expect this occasionally on
quiet days, particularly for Kind A crypto markets.

---

## 6. Why validators converge

`resolve_market` wraps the whole read in `gl.eq_principle.strict_eq`. The leader
runs the function and returns a string; each validator runs the same function
against **its own** HTTP responses and agrees only if its string is identical.

The function returns one canonical, pipe-delimited payload:

```
v1|kind|category|asset|source_a|source_b|day|A_SERIES|a_verdict|B_SERIES|b_verdict|final
```

where each `SERIES` is comma-joined `SYMBOL:open:close` using `PRICE_SCALE`
integers (one entry for Kind A, four for Kind B).

Every decision-bearing field in that string is normalized:

| Raw difference between two nodes | Why it disappears |
|---|---|
| `"80494.31000000"` vs `80494.31` | both become the integer `8049431000000` |
| JSON key order, whitespace, separators | never read; only named fields are extracted |
| extra padding samples outside the window | discarded by the `>= start` / `< end` filter |
| array ordering | open/close chosen by timestamp, not position |
| sample timestamps a few hundred ms apart | the hour bucket is what is compared, not the millisecond |
| a different number of intermediate hourly samples | only the first and last in-window values are used |
| dividend-adjusted vs raw close | both feeds' raw `open`/`close` fields are used, never `adjusted_close` |

What remains is a short string containing only the window's opening price, its
closing price, the verdicts those prices imply, and the result. Two honest
validators looking at the same completed day produce the same string, so
`strict_eq` agrees.

If they genuinely saw different prices, the strings differ, consensus fails, and
nothing is written. The market stays `READY_TO_SETTLE` and anyone can retry.

---

## 7. After consensus, nothing is trusted

`strict_eq` returning does not end the checks. The contract performs **zero**
further web requests and passes the agreed payload through `parse_agreed`,
which runs in deterministic code and re-derives everything:

1. field count is exactly 12 and the version tag is `v1`
2. `kind`, `category`, `asset`, `day` and both source names bind to *this*
   market — a payload for another market, day or asset is rejected
3. each series has the right number of entries, and the symbols match the
   catalog **in order**
4. every price is a positive integer
5. `a_verdict` is recomputed from `A_SERIES` and must match
6. `b_verdict` is recomputed from `B_SERIES` and must match
7. `final` is recomputed from the two verdicts and must match
8. a settled result must be `UP`/`DOWN` (Kind A) or a catalog symbol (Kind B)

Any failure raises `INVARIANT:` and the transaction reverts. Blanking one
source while keeping a directional `final` fails check 7. Forging a winner
outside the catalog fails check 8. Only after all eight checks pass is state
written — and the exact agreed string is stored alongside it, so the evidence
panel shows the very bytes consensus reached.

---

## 8. When resolution cannot happen

| Situation | Class | Effect |
|---|---|---|
| timeout, 408, 425, 429, 5xx, empty body | `TRANSIENT` | revert, stays `READY_TO_SETTLE`, retry later |
| 4xx, malformed JSON, incomplete window, no session that day, body over 60 KB, non-UTF-8 | `EXTERNAL` | revert, stays `READY_TO_SETTLE`, retry later |
| payload fails any `parse_agreed` check | `INVARIANT` | revert, never happens in honest execution |
| wrong phase, bad input, duplicate market, side switch | `EXPECTED` | revert, caller error |

Nothing is written on any of these. `resolve_market` is permissionless and
idempotent-until-successful, so anyone can keep retrying.

### The terminal refund

Once `now >= terminal_refund_at` (five days after the day closed),
`resolve_market` takes a different path: it makes **no web request at all**,
stores empty verdicts and an empty payload, sets the market `INCONCLUSIVE` with
`refund_all = true`, and every staker can withdraw exactly what they put in.

This path is fully deterministic — it has no external dependency, so it cannot
itself fail. It is the guarantee that stakes can never be locked forever by a
feed that went away permanently. It never invents a price, and it never produces
a direction or a winner.

---

## 9. Verifying it yourself

```bash
python scripts/check_sources.py            # both categories, last complete day
python scripts/check_sources.py --day 2026-09-18 --verbose
```

The script imports the parsers out of `contracts/GrokMarket.py`, so it exercises
exactly the code `resolve_market` runs. It prints each source's reconstructed
open, close, direction and bps, and whether the two agree. `scripts/demo_markets.py`
walks five full lifecycles — agreement, disagreement, relative return and the
terminal refund — with no node required.
