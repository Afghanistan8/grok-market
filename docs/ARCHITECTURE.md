# Architecture

Grok-Market is one Python Intelligent Contract plus a read-only frontend. There
is no backend, no indexer, no keeper and no privileged account.

```
  wallet ──► GenLayer RPC ──► GrokMarket.py ──► gl.nondet.web.get ──► public feeds
    ▲                              │
    └────── views (gen_call) ──────┘
                 │
            frontend (Vite + React)
```

---

## The deterministic / non-deterministic split

This is the core structural rule of the contract, and it maps onto three
distinct regions of `resolve_market`.

### Before the block — deterministic

Loads the market, checks it is unresolved, reads consensus time from
`gl.message_raw['datetime']`, checks the window has closed, and handles the
terminal refund path. Everything here is a pure function of storage plus the
transaction timestamp, so every validator computes it identically.

Values the nondet block will need (`kind`, `category`, `asset`, `day_index`,
`win_start`, `win_end`) are copied into plain locals here. The closure captures
those locals rather than reaching back into storage, which keeps the block free
of storage reads.

### Inside the block — non-deterministic

`read_sources()` is the only place `gl.nondet.web.get` is called. It is passed
to `gl.eq_principle.strict_eq`, which runs it on the leader and independently on
every validator. The GenVM forbids storage writes, contract calls, message
emission and nested nondet blocks inside it, and the contract does none of them.

The function returns a single canonical string — never a dict, never an object —
because `strict_eq` compares return values for exact equality and a string is
the easiest thing to make byte-stable.

### After the block — deterministic again

```python
payload = gl.eq_principle.strict_eq(read_sources)
agreed = parse_agreed(payload, kind, category, asset, day_index)   # no network
self.evidence[...] = SettlementEvidence(...)                       # storage writes
```

**No web request happens after `strict_eq` returns.** The only input to the
state transition is the agreed string, and `parse_agreed` re-derives every
verdict from it before anything is persisted. See
[RESOLUTION.md](RESOLUTION.md) §7 for the eight checks.

---

## Why the payload is a flat string

`strict_eq` agrees when the leader's and validator's return values are equal.
Anything with ambiguous serialization — dict ordering, float formatting, nested
structures — risks two honest nodes disagreeing on representation rather than on
facts. A pipe-delimited string of integers and catalog symbols has exactly one
spelling per set of facts.

It also doubles as the audit record: the exact agreed string is stored in
`SettlementEvidence.payload`, and `get_settlement_evidence` derives the per-asset
rows the UI shows **by parsing that stored string**. What a user sees in the
evidence panel is therefore the literal bytes consensus reached, not a parallel
copy that could drift.

---

## Storage layout

Keyed lookups use `TreeMap`. `DynArray` is not used for keyed access, and in
fact is not used at all — the SDK forbids user instantiation of a bare
`DynArray`, so the evidence record stores scalars plus the payload string and
derives lists on read.

| Map | Key | Value | Purpose |
|---|---|---|---|
| `markets` | `u256` id | `MarketRecord` | the market itself |
| `positions` | `"{id}:{wallet}"` | `PositionRecord` | one position per wallet per market |
| `evidence` | `u256` id | `SettlementEvidence` | what consensus agreed |
| `unique_index` | `"{cat}\|{asset\|*}\|{day}"` | `u256` id | enforces one market per asset per day |
| `market_seq` | `u256` seq | `u256` id | newest-first pagination |
| `user_markets` | `"{wallet}:{seq}"` | `u256` id | markets a wallet created |
| `user_positions` | `"{wallet}:{seq}"` | `u256` id | markets a wallet staked in |
| `market_positions` | `"{id}:{seq}"` | position key | the book for one market |
| `activity` | `u256` seq | `ActivityRecord` | the activity feed |

Addresses are normalized to lowercase `0x` hex (`addr_key`) before being used in
a key, so a checksummed and a lowercase address always resolve to the same slot.

Kind B pools are four flat `u256` fields (`pool0`..`pool3`) indexed by position
in the category catalog rather than a nested structure — explicit, cheap and
deterministic.

### Money representation

All settlement math is integer. `1 GEN = 10**18` wei; prices are integers scaled
by `10**8`. Payout is `stake * total_pool // winner_pool`, floored, so the sum of
payouts can never exceed the pool. Any remainder is dust measured in wei and
stays in the contract.

Views return wei as **decimal strings**, not integers: 6 GEN is `6e18`, which is
far beyond `Number.MAX_SAFE_INTEGER`, and a JSON number would silently lose
precision in the browser. The frontend does `BigInt(value)`.

---

## Permissions

| Method | Who can call it |
|---|---|
| `create_market` | anyone |
| `take_position` | anyone, while the market is `OPEN` |
| `resolve_market` | anyone, once the window has closed |
| `claim` | the position owner only, once |

There is no owner, no pause switch, no admin resolve and no upgrade hook. The
contract stores no privileged address of any kind. `resolve_market` being open
to anyone is what makes the market settle without a keeper: whoever wants the
outcome recorded pays the gas.

---

## Phases

`state` is stored; `phase` is derived on read so the UI never has to infer it.

```
                     now < cutoff_at            OPEN
  cutoff_at <=       now < settles_at           WINDOW_LIVE
                     now >= settles_at          READY_TO_SETTLE
  state == SETTLED                              SETTLED_UP / SETTLED_DOWN / SETTLED_WINNER
  state == INCONCLUSIVE                         INCONCLUSIVE
```

---

## Error classes

Every revert message carries a prefix so callers and the UI can tell a retryable
problem from a permanent one.

| Prefix | Meaning | Market afterwards |
|---|---|---|
| `EXPECTED:` | caller error — bad input, wrong phase, duplicate market, side switch, double claim | unchanged |
| `TRANSIENT:` | source timeout, 408, 425, 429, 5xx, empty body | stays `READY_TO_SETTLE`, retryable |
| `EXTERNAL:` | source 4xx, malformed JSON, incomplete window, no session, oversized or non-UTF-8 body | stays `READY_TO_SETTLE`, retryable |
| `INVARIANT:` | the agreed payload is malformed or self-contradictory | must never happen in honest execution |

`TRANSIENT` and `EXTERNAL` are the two classes that leave a market resolvable
later. Both revert the entire transaction, so no partial state is ever written.

---

## Testing

Tests run through `gltest`'s **direct mode**, which downloads the real
`py-genlayer` runner named in the contract header and executes the contract
in-process against it. Storage, calldata encoding, the equivalence principle and
`gl.message_raw` all behave as they do on chain — this is not a hand written
stand-in for the VM.

- `tests/direct/` — calendar math (cross-checked against Python's `datetime`),
  exact decimal parsing (cross-checked against `Decimal`), the four source
  readers, verdict math, market lifecycle, payouts and claims.
- `tests/consensus/` — payload construction and the `parse_agreed` gate, plus
  leader/validator convergence.

Two harness details worth knowing:

- `VMContext.warp` does not carry `datetime` back into the already-imported
  `gl.message_raw` dict, so `tests/conftest.py` provides a `warp()` helper that
  patches that field as well. The contract deliberately reads
  `gl.message_raw['datetime']` rather than a host clock.
- Direct mode stubs `gl.vm.spawn_sandbox`, which is how `strict_eq` re-runs the
  function inside its validator, so `vm.run_validator()` cannot drive it.
  Convergence is instead tested the way it actually matters: snapshot state,
  resolve against one node's responses, roll back, resolve again against
  byte-different responses, and assert the two agreed payloads are identical.
- Direct mode has no `EthSend` handler, so native transfers are observed through
  `vm._gl_call_hook`. That same hook is used to simulate a *failing* transfer and
  prove the claim rolls back with `claimed` still false.

---

## Frontend

The app only reads views and submits wallet transactions. It computes no
outcomes.

- Charts and live prices are **display only**. They are fetched through a
  same-origin proxy purely for decoration and never influence settlement. The
  contract calls the origin APIs directly and would ignore the proxy entirely.
- All list views are paginated at 50 records, the contract's `MAX_PAGE`.
- Writes go through `genlayer-js`, which requires a fee estimate:
  `estimateTransactionFeesForWrite` then `writeContract({ ..., fees })`. Omitting
  `fees` is a common silent write failure.
- The wallet must be pointed at `https://rpc-bradbury.genlayer.com`. The
  zkSync-OS ChainList host for chain 4221 rate limits `eth_sendRawTransaction`
  with `-32005 transaction gas rate limit exceeded`, which surfaces as
  transactions that simply never land. The app detects that RPC and shows a
  persistent banner.
