import { Link, Outlet } from "@tanstack/react-router";

import { ConfigBanner } from "../components/Banners";
import { Header } from "../components/Header";
import { EXPLORER, env, isConfigured } from "../lib/env";

export function RootLayout() {
  return (
    <div className="relative z-10 flex min-h-screen flex-col">
      <ConfigBanner />
      <Header />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-zinc-900 px-4 py-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[11px] text-zinc-600">
          <span>GROK-MARKET</span>
          <span>No admin key · No single oracle · Two independent feeds must agree</span>
          <Link to="/how-it-works" className="ml-auto transition hover:text-amber-300">
            How it works
          </Link>
          {isConfigured ? (
            <a
              href={`${EXPLORER}/address/${env.contractAddress}`}
              target="_blank"
              rel="noreferrer"
              className="transition hover:text-amber-300"
            >
              Contract
            </a>
          ) : null}
        </div>
      </footer>
    </div>
  );
}

export function NotFound() {
  return (
    <div className="panel px-6 py-16 text-center">
      <p className="label">404</p>
      <p className="mt-2 text-sm text-zinc-300">That page does not exist.</p>
      <Link to="/markets" className="btn mt-5">
        Go to markets
      </Link>
    </div>
  );
}
