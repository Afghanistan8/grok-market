import { isConfigured } from "../lib/env";

export function ConfigBanner() {
  if (isConfigured) return null;
  return (
    <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2.5">
      <p className="mx-auto max-w-6xl text-xs text-amber-200">
        <strong className="font-semibold">No contract address configured.</strong> Deploy{" "}
        <code className="rounded bg-black/40 px-1">contracts/GrokMarket.py</code> to studionet and
        set <code className="rounded bg-black/40 px-1">VITE_GROKMARKET_CONTRACT_ADDRESS</code>.
      </p>
    </div>
  );
}
