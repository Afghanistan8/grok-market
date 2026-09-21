import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

import { env } from "./env";

type EthereumProvider = Parameters<typeof createClient>[0] extends { provider?: infer P }
  ? NonNullable<P>
  : never;

type ChainConfig = NonNullable<Parameters<typeof createClient>[0]>["chain"];

/** genlayer-js's studionet chain, pinned to the app's RPC. */
function chain(): ChainConfig {
  return {
    ...studionet,
    rpcUrls: { default: { http: [env.rpcUrl] } },
  } as unknown as ChainConfig;
}

/**
 * Read client. No account, no wallet — every view is a `gen_call`.
 *
 * The chain object always carries the app's RPC, so a wallet that still holds
 * the rate-limited zkSync-OS endpoint cannot poison reads.
 */
export function readClient() {
  return createClient({ chain: chain(), endpoint: env.rpcUrl });
}

/** Write client bound to the connected wallet. */
export function writeClient(account: `0x${string}`, provider: unknown) {
  return createClient({
    chain: chain(),
    endpoint: env.rpcUrl,
    account,
    provider: provider as EthereumProvider,
  });
}

export function describeError(error: unknown): string {
  if (!error) return "";
  if (typeof error === "string") return error;
  if (error instanceof Error) return `${error.message} ${JSON.stringify((error as never)["cause"] ?? "")}`;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

/**
 * Turns a contract revert into the message a person should actually read.
 * The contract prefixes every revert with its error class.
 */
export function humanError(error: unknown): string {
  const raw = describeError(error);

  const match = raw.match(/(EXPECTED|TRANSIENT|EXTERNAL|INVARIANT):\s*([^"'}\\]+)/);
  if (match) {
    const [, kind, message] = match;
    const text = message.trim();
    if (kind === "TRANSIENT") return `A price source was temporarily unavailable (${text}). Nothing changed — try again shortly.`;
    if (kind === "EXTERNAL") return `A price source could not be read (${text}). Nothing changed — the market stays resolvable.`;
    if (kind === "INVARIANT") return `Consensus produced an inconsistent payload (${text}). Nothing was written.`;
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  if (raw.toLowerCase().includes("user rejected")) return "You rejected the request in your wallet.";
  return raw.length > 220 ? `${raw.slice(0, 220)}...` : raw || "Something went wrong.";
}
