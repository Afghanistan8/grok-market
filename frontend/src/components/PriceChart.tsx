import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DAY } from "../lib/format";
import type { Market } from "../lib/types";

const BINANCE_PAIRS: Record<string, string> = {
  BTC: "BTCUSDT",
  ETH: "ETHUSDT",
  SOL: "SOLUSDT",
  XRP: "XRPUSDT",
};

interface Point {
  t: number;
  close: number;
}

/**
 * Display only. These candles come from a same-origin proxy purely so the page
 * has something to look at. They never decide an outcome: settlement happens
 * inside the contract, against the origin APIs, under the equivalence principle.
 */
async function loadSeries(market: Market): Promise<Point[]> {
  // Show the four days leading up to the market's day, or up to now if the
  // day is still in the future. Asking for a future range returns nothing.
  const now = Math.floor(Date.now() / 1000);
  const to = Math.min(market.settles_at + DAY, now);
  const from = to - 4 * DAY;

  if (market.category === "CRYPTO") {
    const symbol = BINANCE_PAIRS[market.kind === "A" ? market.asset : market.universe[0]];
    if (!symbol) return [];
    const url = `/binance/api/v3/klines?symbol=${symbol}&interval=1h&startTime=${from * 1000}&endTime=${to * 1000}&limit=96`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`chart unavailable (${response.status})`);
    const raw = (await response.json()) as [number, string, string, string, string][];
    return raw.map((k) => ({ t: Math.floor(k[0] / 1000), close: Number(k[4]) }));
  }

  const ticker = (market.kind === "A" ? market.asset : market.universe[0]).toLowerCase();
  const response = await fetch(`/stocks/api/symbol/s/${ticker}/history`);
  if (!response.ok) throw new Error(`chart unavailable (${response.status})`);
  const body = (await response.json()) as { data?: { data?: { t: string; c: number }[] } };
  const rows = body.data?.data ?? [];
  return rows
    .map((row) => ({ t: Math.floor(Date.parse(`${row.t}T00:00:00Z`) / 1000), close: row.c }))
    .filter((point) => point.t >= from - 10 * DAY && point.t <= to)
    .sort((a, b) => a.t - b.t);
}

export function PriceChart({ market }: { market: Market }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["chart", market.id],
    queryFn: () => loadSeries(market),
    staleTime: 120_000,
    retry: 1,
  });

  const label = market.kind === "A" ? market.asset : market.universe[0];

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between">
        <h3 className="label">{label} · reference chart</h3>
        <span className="chip border-zinc-800 text-zinc-600">display only</span>
      </div>

      <div className="mt-4 h-56">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <span className="label">loading</span>
          </div>
        ) : isError || !data || data.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center">
            <span className="text-xs text-zinc-600">
              {isError
                ? "Chart data is unavailable right now. This has no effect on settlement."
                : "No price data for this range yet. This has no effect on settlement."}
            </span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
              <defs>
                <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ffb020" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#ffb020" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1c1e27" vertical={false} />
              <XAxis
                dataKey="t"
                tickFormatter={(t: number) => new Date(t * 1000).toISOString().slice(5, 10)}
                stroke="#3f414d"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                minTickGap={28}
              />
              <YAxis
                domain={["dataMin", "dataMax"]}
                stroke="#3f414d"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={52}
                tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              />
              <Tooltip
                contentStyle={{
                  background: "#0d0e13",
                  border: "1px solid #1c1e27",
                  borderRadius: 6,
                  fontSize: 12,
                }}
                labelFormatter={(label) =>
                  new Date(Number(label) * 1000).toISOString().slice(0, 16).replace("T", " ")
                }
                formatter={(value) => [Number(value).toLocaleString(), "close"]}
              />
              <ReferenceArea
                x1={market.cutoff_at}
                x2={market.settles_at}
                fill="#ffb020"
                fillOpacity={0.07}
              />
              <Area
                type="monotone"
                dataKey="close"
                stroke="#ffb020"
                strokeWidth={1.5}
                fill="url(#fill)"
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <p className="mt-3 text-xs text-zinc-600">
        {market.cutoff_at > Math.floor(Date.now() / 1000)
          ? "This market's GMT+1 day has not started yet, so the chart shows recent prices. "
          : "The shaded band is the GMT+1 day this market settles on. "}
        Prices shown here are decoration — the contract fetches its own data from{" "}
        {market.source_a} and {market.source_b}.
      </p>
    </div>
  );
}
