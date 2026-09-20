import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { writes } from "../lib/contract";
import { GEN, gen, parseGen } from "../lib/format";
import { humanError } from "../lib/genlayer";
import type { Market, Position } from "../lib/types";
import { useWriteContext } from "../lib/useWallet";
import { ErrorNote } from "./Primitives";

const MIN = 2n * GEN;
const MAX = 6n * GEN;

export function StakeTicket({
  market,
  position,
}: {
  market: Market;
  position?: Position;
}) {
  const { getContext, isConnected } = useWriteContext();
  const queryClient = useQueryClient();

  const sides = market.kind === "A" ? ["UP", "DOWN"] : market.universe;
  const locked = position?.found ? position.side : null;
  const [side, setSide] = useState<string>(locked ?? sides[0]);
  const [amount, setAmount] = useState("2");

  const held = position?.found ? BigInt(position.stake) : 0n;
  const value = parseGen(amount);
  const resulting = held + value;

  const mutation = useMutation({
    mutationFn: async () => {
      const ctx = await getContext();
      return writes.takePosition(ctx, market.id, locked ?? side, value);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["market", market.id] });
      queryClient.invalidateQueries({ queryKey: ["position", market.id] });
      setAmount("2");
    },
  });

  let problem: string | null = null;
  if (value <= 0n) problem = "Enter an amount.";
  else if (held === 0n && value < MIN) problem = "A first stake must be at least 2 GEN.";
  else if (resulting > MAX) problem = `That would take you to ${gen(resulting)} GEN. The cap is 6 GEN.`;

  if (market.phase !== "OPEN") {
    return (
      <div className="panel p-5">
        <h3 className="label">Stake</h3>
        <p className="mt-3 text-sm text-zinc-400">
          {market.phase === "WINDOW_LIVE"
            ? "The GMT+1 day is already running. Positions closed at the cutoff."
            : "This market is closed for new positions."}
        </p>
      </div>
    );
  }

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between">
        <h3 className="label">Take a position</h3>
        <span className="font-mono text-[11px] text-zinc-600">2–6 GEN</span>
      </div>

      <div className={`mt-4 grid gap-2 ${sides.length > 2 ? "grid-cols-2" : "grid-cols-2"}`}>
        {sides.map((option) => {
          const active = (locked ?? side) === option;
          const disabled = locked !== null && locked !== option;
          return (
            <button
              key={option}
              type="button"
              disabled={disabled}
              onClick={() => setSide(option)}
              className={`btn justify-center ${active ? "border-amber-400/70 text-amber-300" : ""} ${
                disabled ? "opacity-30" : ""
              }`}
            >
              {option}
            </button>
          );
        })}
      </div>

      {locked ? (
        <p className="mt-2 text-xs text-zinc-500">
          You hold {gen(held)} GEN on {locked}. You can top up this side; switching sides is not
          allowed.
        </p>
      ) : null}

      <label className="mt-4 block">
        <span className="label">Amount (GEN)</span>
        <input
          type="text"
          inputMode="decimal"
          value={amount}
          onChange={(event) => setAmount(event.target.value.replace(/[^0-9.]/g, ""))}
          className="mt-1.5 w-full rounded-md border border-zinc-800 bg-black/40 px-3 py-2 text-sm text-zinc-100"
        />
      </label>

      <div className="mt-2 flex gap-1.5">
        {["2", "3", "4", "6"].map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => setAmount(preset)}
            className="rounded border border-zinc-800 px-2 py-1 font-mono text-[11px] text-zinc-500 transition hover:text-amber-300"
          >
            {preset}
          </button>
        ))}
      </div>

      <dl className="mt-4 space-y-1 border-t border-zinc-900 pt-3 text-xs">
        <div className="flex justify-between">
          <dt className="text-zinc-500">Your total stake</dt>
          <dd className="numeric text-zinc-200">{gen(resulting)} GEN</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-zinc-500">Pool after</dt>
          <dd className="numeric text-zinc-200">
            {gen(BigInt(market.total_pool) + value)} GEN
          </dd>
        </div>
      </dl>

      <button
        type="button"
        disabled={!isConnected || problem !== null || mutation.isPending}
        onClick={() => mutation.mutate()}
        className="btn btn-primary mt-4 w-full"
      >
        {mutation.isPending ? "Confirming..." : isConnected ? "Stake" : "Connect a wallet"}
      </button>

      {problem && isConnected ? (
        <p className="mt-2 text-xs text-amber-300/80">{problem}</p>
      ) : null}
      {mutation.isError ? (
        <div className="mt-3">
          <ErrorNote message={humanError(mutation.error)} />
        </div>
      ) : null}
      {mutation.isSuccess ? (
        <p className="mt-3 text-xs text-emerald-300">Position submitted.</p>
      ) : null}
    </div>
  );
}
