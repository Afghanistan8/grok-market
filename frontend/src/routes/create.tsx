import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { ErrorNote } from "../components/Primitives";
import { api, writes } from "../lib/contract";
import { isConfigured } from "../lib/env";
import { addDays, dayStart, gmt1, localTime, todayGmt1 } from "../lib/format";
import { humanError } from "../lib/genlayer";
import type { Category, Kind } from "../lib/types";
import { useWriteContext } from "../lib/useWallet";

const FALLBACK_ASSETS: Record<Category, string[]> = {
  CRYPTO: ["BTC", "ETH", "SOL", "XRP"],
  STOCKS: ["AAPL", "MSFT", "NVDA", "TSLA"],
};

export function CreatePage() {
  const navigate = useNavigate();
  const { getContext, isConnected } = useWriteContext();

  const universe = useQuery({
    queryKey: ["universe"],
    queryFn: api.universe,
    enabled: isConfigured,
    staleTime: Infinity,
  });

  const [category, setCategory] = useState<Category>("CRYPTO");
  const [kind, setKind] = useState<Kind>("A");
  const [asset, setAsset] = useState("BTC");
  const [day, setDay] = useState(() => addDays(todayGmt1(), 1));

  const assets = useMemo(() => {
    const found = universe.data?.categories.find((c) => c.id === category);
    return found?.assets ?? FALLBACK_ASSETS[category];
  }, [universe.data, category]);

  const existing = useQuery({
    queryKey: ["unique", kind, category, kind === "A" ? asset : "", day],
    queryFn: () => api.byUniqueKey(kind, category, kind === "A" ? asset : "", day),
    enabled: isConfigured && day.length === 10,
  });

  const cutoff = dayStart(day);
  const settles = cutoff + 86400;
  const refund = settles + 5 * 86400;
  const nowSeconds = Math.floor(Date.now() / 1000);

  const duplicate = existing.data?.exists === true;
  const inPast = cutoff <= nowSeconds;
  const tooFar = cutoff - nowSeconds > 366 * 86400;

  const create = useMutation({
    mutationFn: async () =>
      writes.createMarket(await getContext(), kind, category, kind === "A" ? asset : "", day),
    onSuccess: () => navigate({ to: "/markets" }),
  });

  const blocked = duplicate || inPast || tooFar || !isConnected;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl text-zinc-50">Open a market</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Anyone can list a market. There is no approval step and no listing fee beyond gas.
        </p>
      </div>

      <div className="panel space-y-5 p-6">
        <Field label="Category">
          <div className="grid grid-cols-2 gap-2">
            {(["CRYPTO", "STOCKS"] as const).map((option) => (
              <button
                key={option}
                type="button"
                className={`btn justify-center ${category === option ? "border-amber-400/70 text-amber-300" : ""}`}
                onClick={() => {
                  setCategory(option);
                  setAsset(FALLBACK_ASSETS[option][0]);
                }}
              >
                {option}
              </button>
            ))}
          </div>
        </Field>

        <Field
          label="Kind"
          hint={
            kind === "A"
              ? "Predict whether one asset closes up or down over the GMT+1 day."
              : "Predict which asset in the category posts the best percentage return that day."
          }
        >
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              className={`btn justify-center ${kind === "A" ? "border-amber-400/70 text-amber-300" : ""}`}
              onClick={() => setKind("A")}
            >
              Daily direction
            </button>
            <button
              type="button"
              className={`btn justify-center ${kind === "B" ? "border-amber-400/70 text-amber-300" : ""}`}
              onClick={() => setKind("B")}
            >
              Relative return
            </button>
          </div>
        </Field>

        {kind === "A" ? (
          <Field label="Asset">
            <div className="grid grid-cols-4 gap-2">
              {assets.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`btn justify-center ${asset === option ? "border-amber-400/70 text-amber-300" : ""}`}
                  onClick={() => setAsset(option)}
                >
                  {option}
                </button>
              ))}
            </div>
          </Field>
        ) : (
          <Field label="Universe" hint="Relative-return markets cover the whole category.">
            <div className="flex flex-wrap gap-2">
              {assets.map((option) => (
                <span key={option} className="chip border-zinc-700/70 text-zinc-400">
                  {option}
                </span>
              ))}
            </div>
          </Field>
        )}

        <Field label="Target day (GMT+1)">
          <input
            type="date"
            value={day}
            min={addDays(todayGmt1(), 1)}
            onChange={(event) => setDay(event.target.value)}
            className="w-full rounded-md border border-zinc-800 bg-black/40 px-3 py-2 text-sm text-zinc-100"
          />
        </Field>

        <div className="rounded-md border border-zinc-900 bg-black/30 p-4">
          <h3 className="label">Preview</h3>
          <dl className="mt-3 space-y-2 text-xs">
            <Preview label="Positions close" value={gmt1(cutoff)} sub={localTime(cutoff)} />
            <Preview
              label="Day runs"
              value={`${gmt1(cutoff)} → ${gmt1(settles)}`}
              sub="one full GMT+1 calendar day"
            />
            <Preview label="Resolvable from" value={gmt1(settles)} sub={localTime(settles)} />
            <Preview label="Terminal refund" value={gmt1(refund)} sub="5 days after settlement opens" />
          </dl>
        </div>

        {duplicate ? (
          <ErrorNote
            message={`A market for this ${kind === "A" ? "asset" : "category"} and day already exists (#${existing.data?.market_id}). Uniqueness is enforced on chain.`}
          />
        ) : null}
        {inPast ? <ErrorNote message="The target day must start in the future." /> : null}
        {tooFar ? <ErrorNote message="The target day cannot be more than 366 days ahead." /> : null}

        <button
          type="button"
          className="btn btn-primary w-full"
          disabled={blocked || create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Creating..." : isConnected ? "Create market" : "Connect a wallet"}
        </button>

        {create.isError ? <ErrorNote message={humanError(create.error)} /> : null}
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="mt-2">{children}</div>
      {hint ? <p className="mt-2 text-xs text-zinc-600">{hint}</p> : null}
    </div>
  );
}

function Preview({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="text-right">
        <div className="numeric text-zinc-200">{value}</div>
        <div className="text-[11px] text-zinc-600">{sub}</div>
      </dd>
    </div>
  );
}
