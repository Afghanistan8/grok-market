import type { ReactNode } from "react";

import { PHASE_LABEL, PHASE_TONE } from "../lib/format";
import type { Phase } from "../lib/types";

export function PhaseBadge({ phase }: { phase: Phase }) {
  return (
    <span className={`chip ${PHASE_TONE[phase] ?? PHASE_TONE.INCONCLUSIVE}`}>
      {PHASE_LABEL[phase] ?? phase}
    </span>
  );
}

export function Chip({ children, tone = "" }: { children: ReactNode; tone?: string }) {
  return (
    <span className={`chip border-zinc-700/70 text-zinc-400 ${tone}`}>{children}</span>
  );
}

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="panel p-4">
      <div className="label">{label}</div>
      <div className="numeric mt-1.5 text-2xl text-zinc-100">{value}</div>
      {sub ? <div className="mt-0.5 text-xs text-zinc-500">{sub}</div> : null}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="panel px-6 py-14 text-center">
      <p className="text-sm text-zinc-300">{title}</p>
      {hint ? <p className="mt-2 text-xs text-zinc-500">{hint}</p> : null}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="panel flex items-center justify-center gap-3 px-6 py-14">
      <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
      <span className="label">{label}</span>
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
      {message}
    </div>
  );
}

export function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-end justify-between gap-4">
        <h2 className="label">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
