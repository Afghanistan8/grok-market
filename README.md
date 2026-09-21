# Grok-Market

A permissionless daily prediction market that settles itself.

Most prediction markets resolve through an admin key or a single oracle.
Grok-Market removes that party entirely. When anyone calls `resolve_market`, the
Intelligent Contract fetches **two independent public price feeds from inside a
GenLayer equivalence-principle block**, reconstructs the target GMT+1 day from
each feed separately, and derives an outcome from each feed's own prices.

If the two feeds disagree, nobody wins and every stake is refunded. A single
feed can never produce a direction or a winner.

There is no owner, no pause switch, no admin resolve and no upgrade hook.

---

## Live

| | |
|---|---|
| App | [grok-market-theta.vercel.app](https://grok-market-theta.vercel.app) |
| Contract | `0x7b5701387e5154D1942cd2cE3B39cA51b39a39FF` |
| Network | GenLayer Studio Network (studionet) |
| Chain ID | 61999 |
| RPC | `https://studio.genlayer.com/api` |
| Faucet | built into [studio.genlayer.com](https://studio.genlayer.com) |

The frontend is locked to studionet. The chain, RPC and contract address are
fixed in `frontend/src/lib/env.ts`, so it needs no environment variables to
build or deploy.

### What has been verified on the live network

Every item below was run against real studionet validators, not simulated:

| Path | Result |
|---|---|
| Deploy, views | contract deploys; `get_supported_universe` and `get_stats` return the locked catalog |
| `create_market`, all four kinds | crypto and stock, direction and relative-return, created through genlayer-js |
| Weekend stock market | rejected: `EXPECTED: stock markets cannot target a Saturday or Sunday` |
| `take_position` with 2 GEN | position and pool recorded, GEN held by the contract |
| Rejected stake (side switch, over cap) | returns `REFUNDED:<reason>`; the GEN comes back to the wallet in a transfer after finality |
| Resolution fetch, crypto direction | Coinbase + Binance, `MAJORITY_AGREE` |
| Resolution fetch, crypto relative-return | 8 live requests per validator, `MAJORITY_AGREE` |
| Resolution fetch, stock direction and relative-return | stockanalysis + Nasdaq, `MAJORITY_AGREE`, prices identical to the cent |
| Browser-wallet write path | a MetaMask-style EIP-1193 wallet (gas estimate, sign, broadcast) created a market and staked |

The resolution fetch was exercised on a throwaway copy of the contract with one
extra test method, because a real market cannot be resolved until its GMT+1 day
has ended. The copy runs the same `fetch_payload` and `parse_agreed` code.

---

## What you can bet on

Two categories, four assets each:

| Category | Assets | Source A | Source B |
|---|---|---|---|
| **CRYPTO** | BTC, ETH, SOL, XRP | Coinbase Exchange hourly candles | Binance hourly klines |
| **STOCKS** | AAPL, MSFT, NVDA, TSLA | stockanalysis.com daily history | Nasdaq daily history |

Two market kinds, both settling on one **GMT+1 calendar day**:

- **Kind A — daily direction.** Pick one asset, predict whether its GMT+1 day
  closes `UP` or `DOWN`. A flat day counts as `DOWN`.
- **Kind B — daily relative return.** Pick which of the four assets in a
  category posts the strongest percentage return over that GMT+1 day.

Stock markets cannot target a Saturday or Sunday, since there is no session to
settle on. Holidays are not known to the contract; a holiday market simply
cannot resolve and refunds everyone after five days.

Stakes are **2–6 GEN** per wallet per market. You can top up your side; you
cannot switch sides. A stake the contract cannot accept (over the cap, wrong
side, sent after the cutoff) is **refunded in the same transaction** rather than
reverted — see "Why rejected stakes refund" below.

---

## Lifecycle

```
create_market ──► OPEN ──► WINDOW_LIVE ──► READY_TO_SETTLE ──► SETTLED / INCONCLUSIVE ──► claim
                    │           │                  │
              stake 2-6 GEN   day is           anyone may
              until cutoff    running          resolve, free
                                               to retry on failure
```

| Moment | When |
|---|---|
| staking closes | `D 00:00 GMT+1` |
| the day runs | `D 00:00` → `D+1 00:00 GMT+1` |
| `resolve_market` opens | `D+1 00:00 GMT+1` |
| terminal refund | 5 days later |

If both feeds agree, the market settles and the winning side splits the whole
pool pro-rata. If they disagree, or either source ties for first in a Kind B
market, the market settles `INCONCLUSIVE` and everyone withdraws their stake.

If a feed is unreachable, resolution reverts and the market stays retryable.
Five days after the day closed, `resolve_market` stops asking the web anything
at all and refunds every stake. It never invents a price.

GEN sent out by the contract (claims and refunds) arrives as its own
transaction once the triggering transaction finalizes, typically within a
minute or two.

---

## Findings that shaped the design

These came from testing against live data and live validators. Each one is
covered by a regression test.

**CoinGecko was replaced by Coinbase.** CoinGecko rate-limits the public API
after a handful of requests. On studionet the validators share an outbound IP,
and a real resolution failed with `TRANSIENT: source http 429`. Coinbase
answered 25 back-to-back requests without a single 429. Coinbase is also a
single venue with hourly candles, so it measures exactly the same two instants
as Binance.

**Both crypto sources measure the same instants.** An earlier version compared
CoinGecko's last sample *before* the day ended (23 hours) with Binance's close
at the end of the day (24 hours). On 2026-09-20 that split ETH and SOL against
Binance on live data. Both sources now report the price at the window start and
the price at the window end.

**Why rejected stakes refund.** GEN attached to a call is credited to the
contract even when the call reverts: a side-switch stake on the first deploy
left 2 GEN in the contract with no position to claim it by. So `take_position`
never reverts once value is attached. It checks every rule first, and either
records the position (`STAKED:<total wei>`) or sends the GEN back
(`REFUNDED:<reason>`). A call carrying no value still reverts normally.

**Why studionet.** studio-dev (chain 61997) currently executes no Python
contract at all: a 13-line control contract and GenLayer's own documentation
example both fail with `invalid_contract runner absent`. Bradbury (chain 4221)
rejects deploys at `eth_estimateGas`, including for a 289-byte control contract,
so the CLI falls back to 200 000 gas and fails `intrinsic gas too low`.

Use the **stable** `genlayer` CLI for studionet. The `0.40.0-rc` CLI sends
consensus-v0.6 transactions that studionet answers with `NO_MAJORITY` and zero
votes.

---

## Running it

### Contract and tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/direct tests/consensus -q
genvm-lint check contracts/GrokMarket.py
```

327 tests. They run in-process against the real `py-genlayer` SDK — `gltest`
direct mode downloads the runner named in the contract header — so storage,
calldata and the equivalence principle behave as they do on chain.

`genvm-lint check` passes lint. Its separate validate step currently reports
`Failed to load SDK` because it looks for the runner as a `.tar` file while the
release it downloads ships it as a directory; the runner hash itself is present
in every current GenVM release, and the contract deploys and executes on
studionet with it.

### Check the live feeds

```bash
python scripts/check_sources.py
python scripts/check_sources.py --day 2026-09-18 --category STOCKS
```

Fetches every locked source for a GMT+1 day and reports each one's
reconstructed open, close, direction and basis-point return, and whether the two
agree. It imports the parsers out of `contracts/GrokMarket.py`, so it exercises
exactly the code `resolve_market` runs.

A `SPLIT` result is not a failure — it means the two feeds genuinely disagreed
on a near-flat day, and the contract would refund rather than pick a side.

### Walk five lifecycles

```bash
python scripts/demo_markets.py
```

Agreement, disagreement, relative return and the terminal refund, printed step
by step. No node, wallet or faucet needed.

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run typecheck
npm run build
```

`VITE_WALLETCONNECT_PROJECT_ID` is the only variable the app reads, and it is
optional: injected wallets such as MetaMask work without it.

Writes wait for validators to decide the transaction and then show the real
outcome — the contract's own revert message, or a refund notice — rather than
treating a submitted transaction as a successful one.

### Deploying the contract

```bash
genlayer network set studionet      # the stable genlayer CLI, not the 0.40 RC
genlayer deploy --contract contracts/GrokMarket.py
```

Then update `CONTRACT_ADDRESS` in `frontend/src/lib/env.ts` and redeploy the
frontend.

### Vercel

| Setting | Value |
|---|---|
| Root directory | `frontend` |

`frontend/vercel.json` sets the Vite framework, the build command, the `dist`
output folder, the SPA rewrite, and the `/binance/*` and `/stocks/*` proxies for
the display-only charts. Those proxies are cosmetic — the contract calls the
origin APIs directly and never touches them.

---

## Repository

```
contracts/GrokMarket.py   the Intelligent Contract
docs/ARCHITECTURE.md      deterministic vs non-deterministic split, storage, errors
docs/RESOLUTION.md        exact URLs, window reconstruction, why validators converge
scripts/check_sources.py  live source prover
scripts/demo_markets.py   five lifecycles against the real SDK
tests/direct/             deterministic unit tests
tests/consensus/          payload binding and leader/validator convergence
frontend/                 Vite + React + TanStack + wagmi + genlayer-js
SPEC.md                   the build specification
```

Start with [docs/RESOLUTION.md](docs/RESOLUTION.md) — it is self contained and
explains why two validators fetching live data reach the same result.

---

## What this deliberately is not

No order book or AMM. No short selling beyond the binary side pools. No
user-supplied assets, URLs or prices. No LLM deciding a price — settlement
parses structured API bytes, because an LLM is the wrong tool for reading a
number. No admin multisig. No backend writing outcomes on chain.
