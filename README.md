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

## What you can bet on

Two categories, four assets each:

| Category | Assets | Source A | Source B |
|---|---|---|---|
| **CRYPTO** | BTC, ETH, SOL, XRP | CoinGecko | Binance 1h klines |
| **STOCKS** | AAPL, MSFT, NVDA, TSLA | stockanalysis.com | Nasdaq |

Two market kinds, both settling on one **GMT+1 calendar day**:

- **Kind A — daily direction.** Pick one asset, predict whether its GMT+1 day
  closes `UP` or `DOWN`. A flat day counts as `DOWN`.
- **Kind B — daily relative return.** Pick which of the four assets in a
  category posts the strongest percentage return over that GMT+1 day.

Stakes are **2–6 GEN** per wallet per market. You can top up your side; you
cannot switch sides.

> **On hourly markets.** An earlier draft of this spec had Kind B running on a
> single GMT+1 *hour*. That was dropped after probing the feeds live: there is
> no pair of independent, keyless, intraday stock feeds that a contract can rely
> on. Yahoo hard rate-limits under the request volume that independent validators
> generate, and everything else requires an API key, which cannot live in a
> public contract. Daily data is solid from two independent sources for both
> categories, so every shipped market type keeps the two-source guarantee.

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

---

## Network

| Setting | Value |
|---|---|
| Network | GenLayer Testnet Bradbury |
| Chain ID | 4221 |
| RPC | `https://rpc-bradbury.genlayer.com` |
| Explorer | [explorer-bradbury.genlayer.com](https://explorer-bradbury.genlayer.com) |
| Faucet | [testnet-faucet.genlayer.foundation](https://testnet-faucet.genlayer.foundation) |
| Token | GEN, 18 decimals |

> **Point your wallet at `https://rpc-bradbury.genlayer.com`.**
>
> ChainList also lists a zkSync-OS host for chain 4221. That host rate limits
> `eth_sendRawTransaction` and answers with:
>
> ```
> error code -32005: transaction gas rate limit exceeded: node is at capacity
> ```
>
> Transactions simply never land. If your wallet already has that RPC saved,
> open MetaMask → Settings → Networks → GenLayer and replace the RPC URL. The
> app shows a persistent banner when it detects it.

---

## Running it

### Contract and tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/direct tests/consensus -q
```

318 tests. They run in-process against the real `py-genlayer` SDK — `gltest`
direct mode downloads the runner named in the contract header — so storage,
calldata, the equivalence principle and native transfers behave as they do on
chain.

### Check the live feeds

```bash
python scripts/check_sources.py
```

Fetches every locked source for the last complete GMT+1 day and reports each
one's reconstructed open, close, direction and basis-point return, and whether
the two agree. It imports the parsers out of `contracts/GrokMarket.py`, so it
exercises exactly the code `resolve_market` runs.

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

Environment (all optional — the app falls back to sane defaults so a missing
variable cannot brick a deploy):

| Variable | Default |
|---|---|
| `VITE_GROKMARKET_CONTRACT_ADDRESS` | empty — the app shows a "not configured" notice |
| `VITE_GENLAYER_RPC_URL` | `https://rpc-bradbury.genlayer.com` |
| `VITE_WALLETCONNECT_PROJECT_ID` | empty — injected wallets still work |

### Deploying the contract

```bash
gltest deploy --network testnet_bradbury      # or use the Studio at studio.genlayer.com
```

Then set `VITE_GROKMARKET_CONTRACT_ADDRESS` and redeploy the frontend.

### Vercel

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm run build` |
| Output directory | `dist` |
| Install command | `npm install` |

`frontend/vercel.json` proxies `/binance/*` and `/stocks/*` for the display-only
charts and adds the SPA rewrite. Those proxies are cosmetic — the contract calls
the origin APIs directly and never touches them.

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
