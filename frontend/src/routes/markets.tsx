import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { MarketCard } from "../components/MarketCard";
import { Empty, ErrorNote, Loading } from "../components/Primitives";
import { PAGE_SIZE, api } from "../lib/contract";
import { isConfigured } from "../lib/env";
import { humanError } from "../lib/genlayer";
import type { Market, Phase } from "../lib/types";

const CATEGORIES = ["ALL", "CRYPTO", "STOCKS"] as const;
const KINDS = [
  { id: "ALL", label: "All kinds" },
  { id: "A", label: "Daily direction" },
  { id: "B", label: "Relative return" },
] as const;
const PHASES = [
  { id: "ALL", label: "Any phase" },
  { id: "OPEN", label: "Open" },
  { id: "WINDOW_LIVE", label: "Day running" },
  { id: "READY_TO_SETTLE", label: "Ready to settle" },
  { id: "SETTLED", label: "Settled" },
  { id: "INCONCLUSIVE", label: "Refunded" },
] as const;
const SORTS = [
  { id: "newest", label: "Newest" },
  { id: "pool", label: "Biggest pool" },
  { id: "soonest", label: "Settling soonest" },
] as const;

function matchesPhase(market: Market, filter: string): boolean {
  if (filter === "ALL") return true;
  if (filter === "SETTLED") return market.state === "SETTLED";
  return market.phase === (filter as Phase);
}

export function MarketsPage() {
  const [category, setCategory] = useState<string>("ALL");
  const [kind, setKind] = useState<string>("ALL");
  const [asset, setAsset] = useState<string>("ALL");
  const [phase, setPhase] = useState<string>("ALL");
  const [sort, setSort] = useState<string>("newest");
  const [page, setPage] = useState(0);

  const query = useQuery({
    queryKey: ["markets", page],
    queryFn: () => api.markets(page * PAGE_SIZE, PAGE_SIZE),
    enabled: isConfigured,
  });

  const assets = useMemo(() => {
    const found = new Set<string>();
    for (const market of query.data?.items ?? []) {
      if (market.asset) found.add(market.asset);
    }
    return ["ALL", ...Array.from(found).sort()];
  }, [query.data]);

  const visible = useMemo(() => {
    let items = (query.data?.items ?? []).filter(
      (market) =>
        (category === "ALL" || market.category === category) &&
        (kind === "ALL" || market.kind === kind) &&
        (asset === "ALL" || market.asset === asset) &&
        matchesPhase(market, phase),
    );
    if (sort === "pool") {
      items = [...items].sort((a, b) => (BigInt(b.total_pool) > BigInt(a.total_pool) ? 1 : -1));
    } else if (sort === "soonest") {
      items = [...items].sort((a, b) => a.settles_at - b.settles_at);
    }
    return items;
  }, [query.data, category, kind, asset, phase, sort]);

  const total = query.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl text-zinc-50">Markets</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {total} market{total === 1 ? "" : "s"} on chain · showing {visible.length}
          </p>
        </div>
      </div>

      <div className="panel flex flex-wrap gap-3 p-3">
        <Select label="Category" value={category} onChange={setCategory} options={CATEGORIES.map((c) => ({ id: c, label: c === "ALL" ? "All categories" : c }))} />
        <Select label="Kind" value={kind} onChange={setKind} options={KINDS.map((k) => ({ id: k.id, label: k.label }))} />
        <Select label="Asset" value={asset} onChange={setAsset} options={assets.map((a) => ({ id: a, label: a === "ALL" ? "All assets" : a }))} />
        <Select label="Phase" value={phase} onChange={setPhase} options={PHASES.map((p) => ({ id: p.id, label: p.label }))} />
        <Select label="Sort" value={sort} onChange={setSort} options={SORTS.map((s) => ({ id: s.id, label: s.label }))} />
      </div>

      {!isConfigured ? (
        <Empty
          title="No contract configured"
          hint="Set the contract address in src/lib/env.ts."
        />
      ) : query.isLoading ? (
        <Loading label="Reading the board" />
      ) : query.isError ? (
        <ErrorNote message={humanError(query.error)} />
      ) : visible.length === 0 ? (
        <Empty
          title={total === 0 ? "No markets yet" : "Nothing matches those filters"}
          hint={total === 0 ? "Be the first to open one." : "Try widening the filters."}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {visible.map((market) => (
            <MarketCard key={market.id} market={market} />
          ))}
        </div>
      )}

      {pages > 1 ? (
        <div className="flex items-center justify-center gap-3">
          <button
            type="button"
            className="btn"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            Previous
          </button>
          <span className="numeric text-xs text-zinc-500">
            {page + 1} / {pages}
          </span>
          <button
            type="button"
            className="btn"
            disabled={page + 1 >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { id: string; label: string }[];
}) {
  return (
    <label className="flex-1 basis-40">
      <span className="label">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-md border border-zinc-800 bg-black/40 px-2.5 py-1.5 text-xs text-zinc-200"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
