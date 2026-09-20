import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";

import { EvidencePanel } from "../components/EvidencePanel";
import { PriceChart } from "../components/PriceChart";
import { Chip, Empty, ErrorNote, Loading, PhaseBadge } from "../components/Primitives";
import { StakeTicket } from "../components/StakeTicket";
import { api, writes } from "../lib/contract";
import { isConfigured } from "../lib/env";
import { countdown, gen, gmt1, kindLabel, localTime, marketTitle } from "../lib/format";
import { humanError } from "../lib/genlayer";
import { useWriteContext } from "../lib/useWallet";

export function MarketDetailPage() {
  const { id } = useParams({ from: "/markets/$id" });
  const marketId = Number(id);
  const queryClient = useQueryClient();
  const { getContext, address, isConnected } = useWriteContext();

  const market = useQuery({
    queryKey: ["market", marketId],
    queryFn: () => api.market(marketId),
    enabled: isConfigured && Number.isFinite(marketId),
    refetchInterval: 20_000,
  });

  const position = useQuery({
    queryKey: ["position", marketId, address],
    queryFn: () => api.position(marketId, address as string),
    enabled: isConfigured && Boolean(address),
  });

  const claimable = useQuery({
    queryKey: ["claimable", marketId, address],
    queryFn: () => api.claimable(marketId, address as string),
    enabled: isConfigured && Boolean(address) && market.data?.state !== "UNRESOLVED",
  });

  const evidence = useQuery({
    queryKey: ["evidence", marketId],
    queryFn: () => api.evidence(marketId),
    enabled: isConfigured && market.data?.state !== "UNRESOLVED",
  });

  const book = useQuery({
    queryKey: ["book", marketId],
    queryFn: () => api.marketPositions(marketId, 0, 50),
    enabled: isConfigured && Number.isFinite(marketId),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["market", marketId] });
    queryClient.invalidateQueries({ queryKey: ["evidence", marketId] });
    queryClient.invalidateQueries({ queryKey: ["claimable", marketId] });
    queryClient.invalidateQueries({ queryKey: ["position", marketId] });
  };

  const resolve = useMutation({
    mutationFn: async () => writes.resolveMarket(await getContext(), marketId),
    onSuccess: invalidate,
  });

  const claim = useMutation({
    mutationFn: async () => writes.claim(await getContext(), marketId),
    onSuccess: invalidate,
  });

  if (!isConfigured) {
    return <Empty title="No contract configured" />;
  }
  if (market.isLoading) return <Loading label="Loading market" />;
  if (market.isError) return <ErrorNote message={humanError(market.error)} />;
  if (!market.data?.found) {
    return (
      <Empty
        title={`Market #${id} does not exist`}
        hint={<Link to="/markets" className="text-amber-300">Back to markets →</Link>}
      />
    );
  }

  const m = market.data;
  const canResolve = m.phase === "READY_TO_SETTLE";
  const pastDeadline = m.now >= m.terminal_refund_at;
  const claimValue = claimable.data ? BigInt(claimable.data.claimable) : 0n;

  return (
    <div className="space-y-6">
      <div>
        <Link to="/markets" className="font-mono text-xs text-zinc-600 hover:text-amber-300">
          ← markets
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Chip>{m.category}</Chip>
          <Chip>{kindLabel(m.kind)}</Chip>
          <PhaseBadge phase={m.phase} />
        </div>
        <h1 className="mt-3 text-3xl text-zinc-50">{marketTitle(m)}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {m.kind === "A"
            ? `Does ${m.asset} close up or down on the GMT+1 day of ${m.target_day}?`
            : `Which of ${m.universe.join(", ")} posts the best return on ${m.target_day}?`}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <PriceChart market={m} />

          <div className="panel p-5">
            <h3 className="label">Timeline · GMT+1</h3>
            <dl className="mt-3 space-y-2.5 text-sm">
              <Row
                label="Positions close"
                value={gmt1(m.cutoff_at)}
                sub={localTime(m.cutoff_at)}
                active={m.phase === "OPEN"}
              />
              <Row
                label="Day runs until"
                value={gmt1(m.settles_at)}
                sub={localTime(m.settles_at)}
                active={m.phase === "WINDOW_LIVE"}
              />
              <Row
                label="Resolvable from"
                value={gmt1(m.settles_at)}
                sub="anyone may call resolve"
                active={m.phase === "READY_TO_SETTLE"}
              />
              <Row
                label="Terminal refund"
                value={gmt1(m.terminal_refund_at)}
                sub="refunds everyone if no feed can be read"
                active={pastDeadline && m.state === "UNRESOLVED"}
              />
            </dl>
          </div>

          <div className="panel p-5">
            <div className="flex items-center justify-between">
              <h3 className="label">Book</h3>
              <span className="numeric text-xs text-zinc-500">
                {gen(m.total_pool)} GEN · {m.position_count} position
                {m.position_count === 1 ? "" : "s"}
              </span>
            </div>
            <div className="mt-4 space-y-2">
              {Object.entries(m.pools).map(([side, value]) => {
                const total = BigInt(m.total_pool);
                const share = total > 0n ? Number((BigInt(value) * 1000n) / total) / 10 : 0;
                const won = m.result === side;
                return (
                  <div key={side}>
                    <div className="flex justify-between text-xs">
                      <span className={won ? "text-emerald-300" : "text-zinc-400"}>
                        {side}
                        {won ? " · won" : ""}
                      </span>
                      <span className="numeric text-zinc-500">
                        {gen(value)} GEN · {share.toFixed(1)}%
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className={won ? "h-full bg-emerald-400" : "h-full bg-amber-400/70"}
                        style={{ width: `${share}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {book.data && book.data.items.length > 0 ? (
              <div className="mt-5 space-y-1.5 border-t border-zinc-900 pt-3">
                {book.data.items.slice(0, 8).map((row) => (
                  <div key={row.owner} className="flex justify-between font-mono text-[11px]">
                    <span className="text-zinc-600">
                      {row.owner.slice(0, 6)}...{row.owner.slice(-4)}
                    </span>
                    <span className="text-zinc-500">
                      {row.side} · {gen(row.stake)} GEN
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {evidence.data?.found ? <EvidencePanel evidence={evidence.data} /> : null}
        </div>

        <div className="space-y-4">
          <StakeTicket market={m} position={position.data} />

          {canResolve ? (
            <div className="panel p-5">
              <h3 className="label">Resolve</h3>
              <p className="mt-3 text-sm text-zinc-400">
                The GMT+1 day is complete. Anyone can settle this market — there is no keeper and
                no admin.
              </p>
              <p className="mt-2 text-xs text-zinc-600">
                The contract will fetch {m.source_a} and {m.source_b} itself and settle only if both
                independently agree.
                {pastDeadline
                  ? " Past the five-day deadline this now refunds every stake without fetching anything."
                  : ""}
              </p>
              <button
                type="button"
                className="btn btn-primary mt-4 w-full"
                disabled={!isConnected || resolve.isPending}
                onClick={() => resolve.mutate()}
              >
                {resolve.isPending
                  ? "Resolving..."
                  : isConnected
                    ? pastDeadline
                      ? "Trigger refund"
                      : "Resolve market"
                    : "Connect a wallet"}
              </button>
              {resolve.isError ? (
                <div className="mt-3">
                  <ErrorNote message={humanError(resolve.error)} />
                </div>
              ) : null}
            </div>
          ) : null}

          {claimValue > 0n ? (
            <div className="panel p-5">
              <h3 className="label">Claim</h3>
              <p className="numeric mt-2 text-2xl text-emerald-300">{gen(claimValue)} GEN</p>
              <p className="mt-1 text-xs text-zinc-500">
                {claimable.data?.reason === "refund"
                  ? "Refund — the sources did not agree, so your stake comes back in full."
                  : "Your share of the pool."}
              </p>
              <button
                type="button"
                className="btn btn-primary mt-4 w-full"
                disabled={!isConnected || claim.isPending}
                onClick={() => claim.mutate()}
              >
                {claim.isPending ? "Claiming..." : "Claim"}
              </button>
              {claim.isError ? (
                <div className="mt-3">
                  <ErrorNote message={humanError(claim.error)} />
                </div>
              ) : null}
            </div>
          ) : null}

          {position.data?.found ? (
            <div className="panel p-5">
              <h3 className="label">Your position</h3>
              <dl className="mt-3 space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <dt className="text-zinc-500">Side</dt>
                  <dd className="numeric text-zinc-200">{position.data.side}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500">Stake</dt>
                  <dd className="numeric text-zinc-200">{gen(position.data.stake)} GEN</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-zinc-500">Claimed</dt>
                  <dd className="numeric text-zinc-200">{position.data.claimed ? "yes" : "no"}</dd>
                </div>
              </dl>
            </div>
          ) : null}

          {m.phase === "OPEN" || m.phase === "WINDOW_LIVE" ? (
            <div className="panel p-5">
              <h3 className="label">{m.phase === "OPEN" ? "Closes in" : "Settles in"}</h3>
              <p className="numeric mt-2 text-2xl text-zinc-100">
                {countdown(m.phase === "OPEN" ? m.cutoff_at : m.settles_at, m.now)}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  sub,
  active,
}: {
  label: string;
  value: string;
  sub: string;
  active: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className={`text-xs ${active ? "text-amber-300" : "text-zinc-500"}`}>{label}</dt>
      <dd className="text-right">
        <div className="numeric text-xs text-zinc-200">{value}</div>
        <div className="text-[11px] text-zinc-600">{sub}</div>
      </dd>
    </div>
  );
}
