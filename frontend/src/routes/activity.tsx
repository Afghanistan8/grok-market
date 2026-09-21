import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { Empty, ErrorNote, Loading } from "../components/Primitives";
import { PAGE_SIZE, api } from "../lib/contract";
import { isConfigured } from "../lib/env";
import { gen, localTime, shortAddress } from "../lib/format";
import { humanError } from "../lib/genlayer";
import type { ActivityItem } from "../lib/types";

const TONE: Record<ActivityItem["kind"], string> = {
  CREATE: "text-sky-300 border-sky-400/30 bg-sky-400/10",
  STAKE: "text-amber-300 border-amber-400/30 bg-amber-400/10",
  REFUND: "text-zinc-300 border-zinc-500/30 bg-zinc-500/10",
  RESOLVE: "text-fuchsia-300 border-fuchsia-400/30 bg-fuchsia-400/10",
  CLAIM: "text-emerald-300 border-emerald-400/30 bg-emerald-400/10",
};

function describe(item: ActivityItem): string {
  switch (item.kind) {
    case "CREATE": {
      const [kind, category] = item.detail.split("/");
      const label = kind === "B" ? "relative-return" : "direction";
      return `opened a ${category ?? ""} ${label} market`;
    }
    case "STAKE":
      return `staked ${gen(item.amount)} GEN on ${item.detail}`;
    case "REFUND":
      return `was refunded ${gen(item.amount)} GEN (${item.detail})`;
    case "RESOLVE":
      return item.detail === "TERMINAL_REFUND"
        ? "triggered the terminal refund"
        : item.detail === "INCONCLUSIVE"
          ? "resolved it — the sources disagreed, so everyone is refunded"
          : `resolved it to ${item.detail}`;
    case "CLAIM":
      return BigInt(item.amount) > 0n
        ? `claimed ${gen(item.amount)} GEN`
        : "closed out a losing position";
    default:
      return item.detail;
  }
}

export function ActivityPage() {
  const [page, setPage] = useState(0);
  const query = useQuery({
    queryKey: ["activity", page],
    queryFn: () => api.activity(page * PAGE_SIZE, PAGE_SIZE),
    enabled: isConfigured,
    refetchInterval: 30_000,
  });

  if (!isConfigured) return <Empty title="No contract configured" />;

  const total = query.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl text-zinc-50">Activity</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every create, stake, resolution and claim, read straight from the contract. No indexer.
        </p>
      </div>

      {query.isLoading ? (
        <Loading />
      ) : query.isError ? (
        <ErrorNote message={humanError(query.error)} />
      ) : !query.data || query.data.items.length === 0 ? (
        <Empty title="Nothing has happened yet" />
      ) : (
        <div className="panel divide-y divide-zinc-900">
          {query.data.items.map((item) => (
            <div key={item.seq} className="flex flex-wrap items-center gap-3 px-5 py-3">
              <span className={`chip ${TONE[item.kind] ?? ""}`}>{item.kind}</span>
              <span className="font-mono text-xs text-zinc-500">{shortAddress(item.actor)}</span>
              <span className="text-sm text-zinc-300">{describe(item)}</span>
              <Link
                to="/markets/$id"
                params={{ id: String(item.market_id) }}
                className="font-mono text-xs text-zinc-600 hover:text-amber-300"
              >
                #{item.market_id}
              </Link>
              <span className="numeric ml-auto text-[11px] text-zinc-600">
                {localTime(item.at)}
              </span>
            </div>
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
            Newer
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
            Older
          </button>
        </div>
      ) : null}
    </div>
  );
}
