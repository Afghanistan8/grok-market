import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { MarketCard } from "../components/MarketCard";
import { Empty, Loading, Stat } from "../components/Primitives";
import { api } from "../lib/contract";
import { isConfigured, network } from "../lib/env";
import { gen } from "../lib/format";

const STEPS = [
  {
    title: "Anyone opens a market",
    body: "Pick an asset or a category and a future GMT+1 day. No listing committee, no approval.",
  },
  {
    title: "Stake 2–6 GEN",
    body: "Back a direction, or back the asset you think will lead its category. Top up your side until the day starts.",
  },
  {
    title: "The contract settles itself",
    body: "Anyone can trigger resolution. The contract fetches two independent feeds inside an equivalence-principle block and reads each one separately.",
  },
  {
    title: "Agreement pays, disagreement refunds",
    body: "Both feeds must reach the same verdict. If they differ, nobody wins and every stake goes back.",
  },
];

export function HomePage() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats, enabled: isConfigured });
  const open = useQuery({
    queryKey: ["open-markets", 0],
    queryFn: () => api.openMarkets(0, 6),
    enabled: isConfigured,
  });

  return (
    <div className="space-y-14">
      <section className="pt-6">
        <p className="label">{network.name}</p>
        <h1 className="mt-4 max-w-3xl text-4xl leading-tight text-zinc-50 sm:text-5xl">
          A prediction market with{" "}
          <span className="text-amber-400">nobody to trust</span> at settlement.
        </h1>
        <p className="mt-5 max-w-2xl text-zinc-400">
          Most markets resolve through an admin key or one oracle. Grok-Market removes that party.
          The contract fetches two independent public price feeds itself, reconstructs the same
          GMT+1 day from each one separately, and settles only when both agree. A single feed can
          never decide an outcome.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link to="/markets" className="btn btn-primary">
            Browse markets
          </Link>
          <Link to="/create" className="btn">
            Open a market
          </Link>
          <Link to="/how-it-works" className="btn">
            How settlement works
          </Link>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Open pool"
          value={stats.data ? `${gen(stats.data.open_pool)} GEN` : "—"}
          sub="staked in markets not yet settled"
        />
        <Stat label="Open markets" value={stats.data?.open ?? "—"} sub="accepting positions" />
        <Stat
          label="Day running"
          value={stats.data?.window_live ?? "—"}
          sub="window in progress"
        />
        <Stat
          label="Ready to settle"
          value={stats.data?.ready_to_settle ?? "—"}
          sub="anyone can resolve these"
        />
      </section>

      <section className="space-y-3">
        <div className="flex items-end justify-between">
          <h2 className="label">Open now</h2>
          <Link to="/markets" className="font-mono text-xs text-zinc-500 hover:text-amber-300">
            all markets →
          </Link>
        </div>
        {!isConfigured ? (
          <Empty
            title="No contract configured yet"
            hint="Set the contract address in src/lib/env.ts."
          />
        ) : open.isLoading ? (
          <Loading />
        ) : open.data && open.data.items.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {open.data.items.map((market) => (
              <MarketCard key={market.id} market={market} />
            ))}
          </div>
        ) : (
          <Empty
            title="No open markets"
            hint={<Link to="/create" className="text-amber-300">Open the first one →</Link>}
          />
        )}
      </section>

      <section className="space-y-4">
        <h2 className="label">How it works</h2>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => (
            <div key={step.title} className="panel p-5">
              <div className="numeric text-xs text-amber-400">0{index + 1}</div>
              <h3 className="mt-2 text-sm text-zinc-100">{step.title}</h3>
              <p className="mt-2 text-xs leading-relaxed text-zinc-500">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-6">
        <h2 className="label">What settles a market</h2>
        <div className="mt-4 grid gap-6 sm:grid-cols-2">
          <div>
            <p className="font-mono text-xs tracking-wider text-zinc-300">CRYPTO</p>
            <p className="mt-1 text-sm text-zinc-500">BTC · ETH · SOL · XRP</p>
            <p className="mt-2 text-xs text-zinc-600">
              Coinbase and Binance hourly candles, each rebuilt into the same GMT+1 day.
            </p>
          </div>
          <div>
            <p className="font-mono text-xs tracking-wider text-zinc-300">STOCKS</p>
            <p className="mt-1 text-sm text-zinc-500">AAPL · MSFT · NVDA · TSLA</p>
            <p className="mt-2 text-xs text-zinc-600">
              stockanalysis.com and Nasdaq daily sessions, matched on the same calendar date.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
