import { ConnectButton } from "@rainbow-me/rainbowkit";
import { Link } from "@tanstack/react-router";

import { FAUCET } from "../lib/env";

const NAV = [
  { to: "/markets", label: "Markets" },
  { to: "/create", label: "Create" },
  { to: "/portfolio", label: "Portfolio" },
  { to: "/activity", label: "Activity" },
  { to: "/how-it-works", label: "How it works" },
] as const;

export function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-zinc-900 bg-[#07070a]/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <Link to="/" className="flex shrink-0 items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-[2px] bg-amber-400" />
          <span className="font-mono text-sm tracking-[0.2em] text-zinc-100">GROK-MARKET</span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="rounded px-2.5 py-1.5 font-mono text-xs tracking-wide text-zinc-500 transition hover:text-zinc-100"
              activeProps={{ className: "text-amber-300" }}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <span className="chip hidden border-zinc-700/70 text-zinc-400 sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Bradbury · 4221
          </span>
          <a
            href={FAUCET}
            target="_blank"
            rel="noreferrer"
            className="chip hidden border-zinc-700/70 text-zinc-400 transition hover:text-amber-300 lg:inline-flex"
          >
            Faucet
          </a>
          <ConnectButton
            showBalance={false}
            accountStatus="address"
            chainStatus="none"
            label="Connect"
          />
        </div>
      </div>

      <nav className="flex gap-1 overflow-x-auto border-t border-zinc-900 px-4 py-2 md:hidden">
        {NAV.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className="shrink-0 rounded px-2.5 py-1 font-mono text-xs text-zinc-500"
            activeProps={{ className: "text-amber-300" }}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
