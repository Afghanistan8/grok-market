# Grok-Market — specification

The rules this repository is built to. Where the original brief and reality
diverged, the divergence and its evidence are recorded here rather than quietly
resolved.

---

## 1. Product

A permissionless prediction market on GenLayer. It is deployed on studionet
(chain 61999); see the recorded deviations below for why not Bradbury.

Two categories, fixed at compile time:

| Category | Assets |
|---|---|
| CRYPTO | BTC, ETH, SOL, XRP |
| STOCKS | AAPL, MSFT, NVDA, TSLA |

Two market kinds, both settling on a single **GMT+1 calendar day**:

- **Kind A — daily direction.** One asset; predict `UP` or `DOWN` for that day's
  candle. Flat resolves `DOWN`.
- **Kind B — daily relative return.** One category; predict which of its four
  assets posts the greatest `(close - open) / open` over that day, computed
  independently per source from that source's own open and close.

Stake is 2–6 GEN per wallet per market. Top-ups on the held side are allowed;
switching sides is not.

### Recorded deviation: no hourly markets

The original brief specified Kind B on a single GMT+1 **hour**. That was
dropped after probing every candidate feed live:

| Feed | Result |
|---|---|
| Stooq (brief's stock source) | dead — JS anti-bot wall on `.com` and `.pl` |
| Yahoo Finance | hard `429` after a handful of requests |
| marketdata.app | `401` for MSFT/NVDA/TSLA; only AAPL works keyless |
| EODHD / FMP / Twelve Data / Alpha Vantage / StockData | require an API key |

No two independent keyless intraday stock feeds exist, and an API key cannot
live in a public contract. Daily data *is* available from two independent
keyless sources per category, so both kinds were moved to a daily window. Every
shipped market type keeps the two-source guarantee rather than shipping one
category that can never settle.

### Recorded deviation: Coinbase instead of CoinGecko

The brief named CoinGecko as crypto source A. On live data it failed twice:
its public API rate-limited a real resolution on studionet validators
(`TRANSIENT: source http 429`), and as a sampled index it measured a different
span from Binance, which split ETH and SOL on 2026-09-20. Coinbase Exchange
hourly candles replace it: keyless, independent of Binance, no 429 across 25
back-to-back requests, and measuring the same two instants as Binance. Across
six live days all 24 crypto asset-days agreed.

### Recorded deviation: studionet instead of Bradbury

Bradbury rejects contract deploys at `eth_estimateGas`, including a 289-byte
control contract, so the CLI falls back to 200 000 gas and the transaction fails
`intrinsic gas too low`. studio-dev executes no Python contract at all
(`invalid_contract runner absent`, reproduced with GenLayer's own documentation
example). The contract and frontend therefore target studionet.

---

## 2. Non-negotiable properties

1. The contract fetches live HTTP itself via `gl.nondet.web.get`.
2. All non-determinism lives inside `gl.eq_principle.strict_eq`.
3. **No web request happens after `strict_eq` returns.**
4. Only fields present in the agreed payload are persisted.
5. All lifecycle time comes from `gl.message_raw['datetime']`, never a host clock.
6. A single source can never produce `UP`, `DOWN` or a winner.
7. Callers cannot pass prices, URLs, slugs, pairs, directions, winners or results
   into `resolve_market`. It takes a market id and nothing else.
8. No LLM decides a price. Settlement parses structured API bytes.
9. No owner, no pause, no admin resolve, no upgrade hook, no privileged address.
10. Integer math only in settlement, payouts and stored prices. No floats.

---

## 3. Constants

```
DAY                   = 86400
HOUR                  = 3600
GMT_PLUS_ONE          = 3600      fixed +1h, never DST, never a tz database
GEN                   = 10**18
MIN_STAKE             = 2 * GEN
MAX_STAKE             = 6 * GEN
MAX_FORWARD_DAYS      = 366
TERMINAL_REFUND_DELAY = 5 * DAY
MAX_PAGE              = 50
MAX_SOURCE_BYTES      = 60000
PRICE_SCALE           = 10**8
```

---

## 4. Time model

For a GMT+1 calendar day `D`:

```
cutoff_at          = D 00:00 GMT+1  ==  day_index(D) * 86400 - 3600
settles_at         = cutoff_at + 86400
terminal_refund_at = settles_at + 5 * 86400
```

Civil date arithmetic is hand-rolled (`_is_leap`, `_days_from_civil`,
`_civil_from_days`, `parse_day_string`) and the ISO-8601 parser is hand-rolled
(`parse_iso_utc`), so the contract depends on no timezone data and no host
clock.

Phases are derived, not stored:

```
OPEN · WINDOW_LIVE · READY_TO_SETTLE · SETTLED_UP · SETTLED_DOWN ·
SETTLED_WINNER · INCONCLUSIVE
```

---

## 5. Sources

Compile-time catalogs. See [docs/RESOLUTION.md](docs/RESOLUTION.md) for the full
URL templates and window rules.

| Category | A | B |
|---|---|---|
| CRYPTO | Coinbase Exchange `candles` `granularity=3600`, exactly 24 aligned candles | Binance `klines` `interval=1h`, exactly 24 aligned bars |
| STOCKS | `stockanalysis.com/api/symbol/s/{t}/history` | `api.nasdaq.com/.../historical?fromdate=D&todate=D+1` |

Constraints discovered by probing, now encoded in the contract:

- **Binance `interval=1d` is unusable.** Daily bars are UTC-aligned and a UTC
  day is one hour out of step with a GMT+1 day. 24 hourly klines are
  reconstructed instead, with the first and last open times checked exactly.
- **`api.binance.com` answers 451 from restricted regions**, including for
  public market data. Validators are geographically distributed, so that host
  would split consensus on validator location alone. The contract uses
  `data-api.binance.vision`, the unrestricted public market-data host.
- **Both stock feeds gate non-browser clients.** The contract pins a
  browser-like `User-Agent`, `Accept` and `Accept-Language` on every request.
  Nasdaq additionally rejects `fromdate == todate`, so the request asks for
  `D..D+1` and the parser selects the row dated `D`.
- **Both crypto sources must measure the same two instants**: the price at the
  window start and the price at the window end. Comparing different spans
  splits verdicts on quiet days.

---

## 6. Outcome rules

Per source, from that source's own prices only:

```
Kind A:  direction = UP if close > open else DOWN
Kind B:  bps       = ((close - open) * 10000) // open
         winner    = strictly greatest bps, else TIE
```

Combined:

```
final = a_verdict if a_verdict == b_verdict and neither is TIE else INCONCLUSIVE
```

A `TIE` on either source can never produce a winner. An empty verdict from
either source can never settle.

---

## 7. Consensus payload

```
v1|kind|category|asset|source_a|source_b|day|A_SERIES|a_verdict|B_SERIES|b_verdict|final
```

`SERIES` is comma-joined `SYMBOL:open:close` with `PRICE_SCALE` integers — one
entry for Kind A, four for Kind B. Exactly 12 fields.

After `strict_eq` returns, `parse_agreed` re-validates in deterministic code
with no network access:

1. field count and version
2. kind, category, asset, day and both source names bind to this market
3. series length and symbols match the catalog in order
4. every price is a positive integer
5. `a_verdict` recomputed from `A_SERIES` matches
6. `b_verdict` recomputed from `B_SERIES` matches
7. `final` recomputed from the two verdicts matches
8. a settled result is `UP`/`DOWN` or a catalog symbol

Any failure raises `INVARIANT:` and reverts.

---

## 8. Methods

| Method | Caller | Notes |
|---|---|---|
| `create_market(kind, category, asset, target_day)` | anyone | rejects unknown catalog keys, past or in-progress days, >366 days ahead, duplicates, and stock markets on a Saturday or Sunday |
| `take_position(market_id, side)` | anyone while OPEN | payable; first stake ≥ 2 GEN, total ≤ 6 GEN, no side switch. Returns `STAKED:<total>`; a rejected stake that carries value is refunded and returns `REFUNDED:<reason>` instead of reverting |
| `resolve_market(market_id)` | anyone once settlement-eligible | no price arguments |
| `claim(market_id)` | position owner only, once | transfers first, then flips `claimed` |

Payouts:

```
refund_all / INCONCLUSIVE        -> original stake
winning side                     -> stake * total_pool // winner_pool
losing side                      -> 0
winner_pool == 0                 -> refund everyone
```

Floor division means payouts can never exceed the pool; dust in wei remains.

`claim` calls `emit_transfer` **before** setting `claimed`. If the send reverts,
the whole transaction rolls back and the owner can retry.

---

## 9. Views

Pure, paginated at `MAX_PAGE = 50`, and complete enough that the frontend needs
no indexer:

```
get_supported_universe   get_market            get_market_phase
get_position             get_claimable         get_markets
get_open_markets         get_markets_by_category
get_market_by_unique_key get_user_markets      get_user_positions
get_market_positions     get_settlement_evidence
get_activity             get_stats
```

Wei values are returned as decimal **strings** — 6 GEN exceeds JavaScript's
safe integer range.

---

## 10. Error classes

| Prefix | Meaning | Market afterwards |
|---|---|---|
| `EXPECTED:` | bad input, wrong phase, duplicate, side switch | unchanged |
| `TRANSIENT:` | timeout, 408, 425, 429, 5xx, empty body | `READY_TO_SETTLE`, retryable |
| `EXTERNAL:` | 4xx, malformed, incomplete window, no session, oversized, non-UTF-8 | `READY_TO_SETTLE`, retryable |
| `INVARIANT:` | agreed payload malformed or self-contradictory | never in honest execution |

---

## 11. Terminal refund

Once `now >= terminal_refund_at`, `resolve_market` makes **no web request**,
stores empty verdicts and an empty payload, and sets the market `INCONCLUSIVE`
with `refund_all = true`. Fully deterministic, so it cannot itself fail. It
never fabricates a price, a direction or a winner.

---

## 12. Frontend rules

- Reads contract views and submits wallet transactions. It computes no outcomes.
- Charts and live prices are display-only and never decide anything.
- Locked to studionet (chain 61999). The network and contract address are fixed
  in code and cannot be overridden by environment variables.
- WalletConnect project id is optional; injected wallets work without it.
- Lists paginate at 50.
- Writes wait for validators to decide the transaction and show the real
  outcome: success, the contract's revert message, or a refund notice.

---

## 13. Definition of done

- `python -m pytest tests/direct tests/consensus -q` passes — 327 tests
- `cd frontend && npm run typecheck` passes
- A reviewer can explain from `docs/RESOLUTION.md` alone why two validators
  fetching live data converge on the same `final_result`
- `resolve_market` cannot persist a direction or winner unless both sources
  independently produced that same verdict
- The stake path moves real GEN via `@gl.public.write.payable` and `emit_transfer`
- The UI can create, stake, resolve and claim against the live deployment

---

## 14. Non-goals

No order book or AMM. No short selling beyond the binary side pools. No
user-created assets. No LLM judging prices. No admin multisig. No backend
writing outcomes. No reference to any other prediction-market product in code,
comments, commits, docs or UI.
