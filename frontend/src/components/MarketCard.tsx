import { Link } from "@tanstack/react-router";

import { countdown, gen, gmt1, kindLabel, marketTitle } from "../lib/format";
import type { Market } from "../lib/types";
import { Chip, PhaseBadge } from "./Primitives";

function PoolBar({ market }: { market: Market }) {
  const entries = Object.entries(market.pools);
  const total = entries.reduce((sum, [, v]) => sum + BigInt(v), 0n);

  if (total === 0n) {
    return <div className="h-1.5 w-full rounded-full bg-zinc-800" />;
  }

  const tones = ["bg-amber-400", "bg-sky-400", "bg-fuchsia-400", "bg-emerald-400"];
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
      {entries.map(([key, value], index) => {
        const width = Number((BigInt(value) * 1000n) / total) / 10;
        if (width <= 0) return null;
        return (
          <div
            key={key}
            className={tones[index % tones.length]}
            style={{ width: `${width}%` }}
            title={`${key}: ${gen(value)} GEN`}
          />
        );
      })}
    </div>
  );
}

export function MarketCard({ market }: { market: Market }) {
  const closes = market.phase === "OPEN" ? market.cutoff_at : market.settles_at;
  const closesLabel = market.phase === "OPEN" ? "Closes in" : "Settles in";
  const showCountdown = market.phase === "OPEN" || market.phase === "WINDOW_LIVE";

  return (
    <Link
      to="/markets/$id"
      params={{ id: String(market.id) }}
      className="panel block p-4 transition hover:border-amber-400/40"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Chip>{market.category}</Chip>
        <Chip>{kindLabel(market.kind)}</Chip>
        <span className="ml-auto">
          <PhaseBadge phase={market.phase} />
        </span>
      </div>

      <div className="mt-3 flex items-baseline justify-between gap-3">
        <h3 className="text-lg text-zinc-100">{marketTitle(market)}</h3>
        <span className="numeric text-sm text-zinc-400">{market.target_day}</span>
      </div>

      <p className="mt-0.5 font-mono text-[11px] text-zinc-600">
        {gmt1(market.cutoff_at)} → {gmt1(market.settles_at)}
      </p>

      <div className="mt-4 space-y-2">
        <PoolBar market={market} />
        <div className="flex items-center justify-between text-xs">
          <span className="text-zinc-500">
            Pool <span className="numeric text-zinc-200">{gen(market.total_pool)} GEN</span>
          </span>
          {market.result ? (
            <span className="numeric text-zinc-300">
              {market.result === "INCONCLUSIVE" ? "refunded" : market.result}
            </span>
          ) : market.leading ? (
            <span className="text-zinc-500">
              leading <span className="numeric text-amber-300">{market.leading}</span>
            </span>
          ) : (
            <span className="text-zinc-600">no positions</span>
          )}
        </div>
        {showCountdown ? (
          <div className="flex items-center justify-between text-[11px] text-zinc-600">
            <span>{closesLabel}</span>
            <span className="numeric">{countdown(closes, market.now)}</span>
          </div>
        ) : null}
      </div>
    </Link>
  );
}
