import type { Phase } from "./types";

export const GEN = 10n ** 18n;
export const DAY = 86400;
export const GMT_PLUS_ONE = 3600;
export const PRICE_SCALE = 100_000_000;

/** Wei string -> a short human amount. Never goes through Number. */
export function gen(wei: string | bigint, decimals = 2): string {
  const value = typeof wei === "bigint" ? wei : BigInt(wei || "0");
  const negative = value < 0n;
  const abs = negative ? -value : value;
  const whole = abs / GEN;
  const frac = abs % GEN;
  const fracText = frac.toString().padStart(18, "0").slice(0, decimals);
  const trimmed = decimals > 0 ? `.${fracText}` : "";
  return `${negative ? "-" : ""}${whole.toString()}${trimmed}`;
}

export function parseGen(input: string): bigint {
  const text = input.trim();
  if (!text) return 0n;
  const [whole, frac = ""] = text.split(".");
  const padded = (frac + "000000000000000000").slice(0, 18);
  return BigInt(whole || "0") * GEN + BigInt(padded || "0");
}

export function scaledPrice(value: number, decimals = 2): string {
  return (value / PRICE_SCALE).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function bps(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value / 100).toFixed(2)}%`;
}

export function shortAddress(address: string): string {
  if (!address || address.length < 10) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

/* ------------------------------------------------------------------ time */

/** Render a Unix instant in GMT+1, the offset every window is measured in. */
export function gmt1(epoch: number, withTime = true): string {
  const d = new Date((epoch + GMT_PLUS_ONE) * 1000);
  const date = d.toISOString().slice(0, 10);
  if (!withTime) return date;
  return `${date} ${d.toISOString().slice(11, 16)} GMT+1`;
}

export function localTime(epoch: number): string {
  return new Date(epoch * 1000).toLocaleString();
}

/** Start of a GMT+1 calendar day, in Unix seconds. */
export function dayStart(day: string): number {
  return Math.floor(Date.parse(`${day}T00:00:00Z`) / 1000) - GMT_PLUS_ONE;
}

export function todayGmt1(): string {
  return new Date(Date.now() + GMT_PLUS_ONE * 1000).toISOString().slice(0, 10);
}

export function addDays(day: string, count: number): string {
  const base = Date.parse(`${day}T00:00:00Z`) + count * DAY * 1000;
  return new Date(base).toISOString().slice(0, 10);
}

export function countdown(target: number, now: number): string {
  let delta = target - now;
  if (delta <= 0) return "now";
  const days = Math.floor(delta / DAY);
  delta -= days * DAY;
  const hours = Math.floor(delta / 3600);
  delta -= hours * 3600;
  const minutes = Math.floor(delta / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/* ----------------------------------------------------------------- labels */

export const PHASE_LABEL: Record<Phase, string> = {
  OPEN: "Open",
  WINDOW_LIVE: "Day running",
  READY_TO_SETTLE: "Ready to settle",
  SETTLED_UP: "Settled · UP",
  SETTLED_DOWN: "Settled · DOWN",
  SETTLED_WINNER: "Settled",
  INCONCLUSIVE: "Refunded",
};

export const PHASE_TONE: Record<Phase, string> = {
  OPEN: "text-amber-300 border-amber-400/30 bg-amber-400/10",
  WINDOW_LIVE: "text-sky-300 border-sky-400/30 bg-sky-400/10",
  READY_TO_SETTLE: "text-fuchsia-300 border-fuchsia-400/30 bg-fuchsia-400/10",
  SETTLED_UP: "text-emerald-300 border-emerald-400/30 bg-emerald-400/10",
  SETTLED_DOWN: "text-rose-300 border-rose-400/30 bg-rose-400/10",
  SETTLED_WINNER: "text-emerald-300 border-emerald-400/30 bg-emerald-400/10",
  INCONCLUSIVE: "text-zinc-400 border-zinc-500/30 bg-zinc-500/10",
};

export function kindLabel(kind: string): string {
  return kind === "A" ? "Daily direction" : "Relative return";
}

export function marketTitle(market: { kind: string; asset: string; category: string }): string {
  return market.kind === "A" ? market.asset : `${market.category} leader`;
}
