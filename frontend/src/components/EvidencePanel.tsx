import { bps, gmt1, scaledPrice } from "../lib/format";
import type { Evidence } from "../lib/types";

export function EvidencePanel({ evidence }: { evidence: Evidence }) {
  if (!evidence.found) return null;

  if (evidence.terminal_refund) {
    return (
      <div className="panel p-5">
        <h3 className="label">Settlement evidence</h3>
        <p className="mt-3 text-sm text-zinc-300">
          No source could be read within five days of the day closing, so the market took the
          terminal refund path.
        </p>
        <p className="mt-2 text-xs text-zinc-500">
          No price was fetched and none was invented. Every stake is withdrawable in full.
        </p>
      </div>
    );
  }

  const rows = evidence.rows ?? [];
  const agreed = evidence.final_result !== "INCONCLUSIVE";

  return (
    <div className="panel overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-900 px-5 py-3">
        <h3 className="label">Settlement evidence</h3>
        <span className="numeric text-xs text-zinc-500">
          resolved {evidence.resolved_at ? gmt1(evidence.resolved_at) : "—"}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-900 text-left">
              <th className="label px-5 py-2 font-normal">Asset</th>
              <th className="label px-3 py-2 font-normal">{evidence.source_a} open → close</th>
              <th className="label px-3 py-2 font-normal">{evidence.source_b} open → close</th>
              <th className="label px-5 py-2 text-right font-normal">Return</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol} className="border-b border-zinc-900/60 last:border-0">
                <td className="px-5 py-2.5 text-zinc-200">{row.symbol}</td>
                <td className="numeric px-3 py-2.5 text-zinc-400">
                  {scaledPrice(row.a_open)} → {scaledPrice(row.a_close)}
                  <span className={`ml-2 ${row.a_bps >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {bps(row.a_bps)}
                  </span>
                </td>
                <td className="numeric px-3 py-2.5 text-zinc-400">
                  {scaledPrice(row.b_open)} → {scaledPrice(row.b_close)}
                  <span className={`ml-2 ${row.b_bps >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {bps(row.b_bps)}
                  </span>
                </td>
                <td className="numeric px-5 py-2.5 text-right text-zinc-500">
                  {row.a_bps === row.b_bps ? "identical" : `${Math.abs(row.a_bps - row.b_bps)} bps apart`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-3 border-t border-zinc-900 px-5 py-4 sm:grid-cols-3">
        <div>
          <div className="label">{evidence.source_a} says</div>
          <div className="numeric mt-1 text-zinc-200">{evidence.a_verdict}</div>
        </div>
        <div>
          <div className="label">{evidence.source_b} says</div>
          <div className="numeric mt-1 text-zinc-200">{evidence.b_verdict}</div>
        </div>
        <div>
          <div className="label">Result</div>
          <div
            className={`numeric mt-1 ${agreed ? "text-emerald-300" : "text-zinc-400"}`}
          >
            {evidence.final_result}
          </div>
        </div>
      </div>

      <p className="border-t border-zinc-900 px-5 py-3 text-xs text-zinc-500">
        {agreed
          ? "Both sources independently produced the same verdict, so the market settled."
          : "The two sources did not independently agree, so no outcome was recorded and every stake is refundable."}
      </p>

      {evidence.payload ? (
        <details className="border-t border-zinc-900 px-5 py-3">
          <summary className="label cursor-pointer select-none">Agreed consensus payload</summary>
          <p className="mt-2 text-xs text-zinc-600">
            The exact string every validator had to reproduce byte for byte. Everything above is
            derived from it.
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-black/50 p-3 font-mono text-[11px] text-zinc-400">
            {evidence.payload}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
