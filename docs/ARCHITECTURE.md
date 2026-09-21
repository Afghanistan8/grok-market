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

Values the nondet block will need (`kind`, `category`, `asset`, `day_index`)
are copied into plain locals here. The closure captures those locals rather than
reaching back into storage, which keeps the block free of storage reads.

### Inside the block — non-deterministic

`fetch_payload()` is the only place `gl.nondet.web.get` is called. It is a
module-level function, and `resolve_market` hands a closure over it to
`gl.eq_principle.strict_eq`, which runs it on the leader and independently on
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

### Value attached to a reverted call stays with the contract

On GenLayer the GEN sent with a call is credited to the contract even when the
call reverts. This was observed on studionet: a stake rejected for switching
sides reverted, yet its 2 GEN stayed in the contract with no position recording
it, and so no way to claim it back.

`take_position` is therefore written so that it never reverts once value is
attached. `_stake_rejection` checks every rule without raising and returns the
reason or `""`. If there is a reason, the value goes straight back to the sender
with `emit_transfer` in the same transaction, a `REFUND` activity entry is
written, and the method returns `REFUNDED:<reason>`. Otherwise it records the
position and returns `STAKED:<total wei>`. Only a call carrying no value may
revert, because it has nothing to lose.

### Outbound transfers arrive after finality

`emit_transfer` does not move GEN inside the calling transaction. It queues a
separate transfer transaction that runs once the calling transaction finalizes;
on studionet that took roughly 40 seconds. This applies to both claim payouts and
stake refunds, and the UI says so.

---

## Permissions

| Method | Who can call it |
|---|---|
| `create_market` | anyone |
| `take_position` | anyone, while the market is `OPEN`; otherwise the stake is refunded |
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
| `EXPECTED:` | caller error — bad input, wrong phase, duplicate market, double claim, a stake sent with no value | unchanged |
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

Three harness details worth knowing:

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

Direct mode cannot reproduce two things that only real validators show: live
web data under consensus, and GEN actually moving. Both were checked on
studionet (see the README's "What has been verified on the live network"). That
live testing is what found the CoinGecko rate limit, the 23-hour sampling bug
and the value trapped by a reverted stake; each now has a regression test.

---

## Frontend

The app only reads views and submits wallet transactions. It computes no
outcomes.

- The network is fixed to studionet (chain 61999, `https://studio.genlayer.com/api`)
  and the contract address is fixed in `frontend/src/lib/env.ts`. Neither can be
  changed by an environment variable, so a hosted build can never silently point
  at a stale contract.
- Writes go through genlayer-js 1.1.8: `writeContract({ address, functionName,
  args, value })`. That version takes no `fees` argument; the fee-estimate API in
  GenLayer's current docs belongs to the consensus-v0.6 release candidate.
- A submitted transaction is not a successful one. Every write waits for
  `waitForTransactionReceipt({ status: "ACCEPTED" })`, then reads
  `consensus_data.leader_receipt[0]`: `execution_result` is `SUCCESS` or `ERROR`,
  and `result.payload` carries either the return value (as
  `{ readable: "<json>" }`) or the contract's revert message. The UI shows that
  outcome, including a `REFUNDED:` notice for a rejected stake.
- In a browser, genlayer-js hands `eth_sendTransaction` to the wallet, which
  fills in nonce, gas and gas price from its own RPC and broadcasts. wagmi adds
  and switches to chain 61999 on first write.
- Views return plain JSON objects with ordinary numbers; wei amounts come back
  as decimal strings.
- Charts and live prices are **display only**. They are fetched through a
  same-origin proxy purely for decoration and never influence settlement. The
  contract calls the origin APIs directly and never touches the proxy.
- All list views are paginated at 50 records, the contract's `MAX_PAGE`.
