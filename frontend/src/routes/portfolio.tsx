import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { Empty, ErrorNote, Loading, PhaseBadge, Stat } from "../components/Primitives";
import { api, writes } from "../lib/contract";
import { isConfigured } from "../lib/env";
import { gen, kindLabel, marketTitle } from "../lib/format";
import { humanError } from "../lib/genlayer";
import { useWriteContext } from "../lib/useWallet";

export function PortfolioPage() {
  const { address, isConnected, getContext } = useWriteContext();
  const queryClient = useQueryClient();

  const positions = useQuery({
    queryKey: ["portfolio", address],
    queryFn: () => api.userPositions(address as string, 0, 50),
    enabled: isConfigured && Boolean(address),
  });

  const created = useQuery({
    queryKey: ["created", address],
    queryFn: () => api.userMarkets(address as string, 0, 50),
    enabled: isConfigured && Boolean(address),
  });

  const claim = useMutation({
    mutationFn: async (marketId: number) => writes.claim(await getContext(), marketId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio", address] });
    },
  });

  if (!isConnected) {
    return (
      <Empty
        title="Connect a wallet to see your positions"
        hint="Everything here is read straight from the contract — there is no account to create."
      />
    );
  }
  if (!isConfigured) return <Empty title="No contract configured" />;
  if (positions.isLoading) return <Loading label="Reading your positions" />;
  if (positions.isError) return <ErrorNote message={humanError(positions.error)} />;

  const rows = positions.data?.items ?? [];
  const staked = rows.reduce((sum, row) => sum + BigInt(row.stake), 0n);
  const claimable = rows.reduce((sum, row) => sum + BigInt(row.claimable), 0n);
  const openCount = rows.filter((row) => row.market.state === "UNRESOLVED").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl text-zinc-50">Portfolio</h1>
        <p className="mt-1 font-mono text-xs text-zinc-600">{address}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Positions" value={rows.length} />
        <Stat label="Live" value={openCount} sub="not yet settled" />
        <Stat label="Staked" value={`${gen(staked)} GEN`} />
        <Stat label="Claimable" value={`${gen(claimable)} GEN`} sub="ready to withdraw" />
      </div>

      {rows.length === 0 ? (
        <Empty
          title="No positions yet"
          hint={<Link to="/markets" className="text-amber-300">Find a market →</Link>}
        />
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-900 text-left">
                <th className="label px-5 py-2.5 font-normal">Market</th>
                <th className="label px-3 py-2.5 font-normal">Side</th>
                <th className="label px-3 py-2.5 text-right font-normal">Stake</th>
                <th className="label px-3 py-2.5 text-right font-normal">Claimable</th>
                <th className="label px-5 py-2.5 text-right font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const value = BigInt(row.claimable);
                return (
                  <tr key={row.market.id} className="border-b border-zinc-900/60 last:border-0">
                    <td className="px-5 py-3">
                      <Link
                        to="/markets/$id"
                        params={{ id: String(row.market.id) }}
                        className="text-zinc-100 hover:text-amber-300"
                      >
                        {marketTitle(row.market)}
                      </Link>
                      <div className="font-mono text-[11px] text-zinc-600">
                        {kindLabel(row.market.kind)} · {row.market.target_day}
                      </div>
                    </td>
                    <td className="numeric px-3 py-3 text-zinc-300">{row.side}</td>
                    <td className="numeric px-3 py-3 text-right text-zinc-300">
                      {gen(row.stake)}
                    </td>
                    <td className="numeric px-3 py-3 text-right">
                      <span className={value > 0n ? "text-emerald-300" : "text-zinc-600"}>
                        {gen(row.claimable)}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right">
                      {row.claimed ? (
                        <span className="font-mono text-[11px] text-zinc-600">claimed</span>
                      ) : value > 0n ? (
                        <button
                          type="button"
                          className="btn btn-primary px-3 py-1"
                          disabled={claim.isPending}
                          onClick={() => claim.mutate(row.market.id)}
                        >
                          Claim
                        </button>
                      ) : (
                        <PhaseBadge phase={row.market.phase} />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {claim.isError ? <ErrorNote message={humanError(claim.error)} /> : null}

      {created.data && created.data.items.length > 0 ? (
        <section className="space-y-3">
          <h2 className="label">Markets you opened</h2>
          <div className="panel divide-y divide-zinc-900">
            {created.data.items.map((market) => (
              <Link
                key={market.id}
                to="/markets/$id"
                params={{ id: String(market.id) }}
                className="flex items-center justify-between px-5 py-3 transition hover:bg-white/[0.02]"
              >
                <div>
                  <div className="text-sm text-zinc-200">{marketTitle(market)}</div>
                  <div className="font-mono text-[11px] text-zinc-600">
                    {market.category} · {market.target_day}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="numeric text-xs text-zinc-500">
                    {gen(market.total_pool)} GEN
                  </span>
                  <PhaseBadge phase={market.phase} />
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
