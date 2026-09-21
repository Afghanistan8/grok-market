/**
 * Two genlayer-js release lines, on purpose:
 *
 * - Writes use genlayer-js 2.0 (the consensus v0.6 release family). Every
 *   transaction is priced with `estimateTransactionFeesForWrite` and submitted
 *   with the returned fees. See `send` in ./contract.ts.
 * - Reads use genlayer-js 1.1.8. On stable studionet the 2.0 client's `gen_call`
 *   fails with "execution failed", so a 2.0-only app could not show the board.
 */
import { createClient as createReadClient } from "genlayer-js-legacy";
import { studionet as legacyStudionet } from "genlayer-js-legacy/chains";
import { createClient as createWriteClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

import { env } from "./env";

type ReadChain = NonNullable<Parameters<typeof createReadClient>[0]>["chain"];
type WriteConfig = NonNullable<Parameters<typeof createWriteClient>[0]>;
type WriteChain = WriteConfig["chain"];
type EthereumProvider = NonNullable<WriteConfig["provider"]>;

/** Read client. No account, no wallet — every view is a `gen_call`. */
export function readClient() {
  const chain = {
    ...legacyStudionet,
    rpcUrls: { default: { http: [env.rpcUrl] } },
  } as unknown as ReadChain;
  return createReadClient({ chain, endpoint: env.rpcUrl });
}

/** Write client bound to the connected wallet, on the v0.6 SDK. */
export function writeClient(account: `0x${string}`, provider: unknown) {
  const chain = {
    ...studionet,
    rpcUrls: { default: { http: [env.rpcUrl] } },
  } as unknown as WriteChain;
  return createWriteClient({
    chain,
    endpoint: env.rpcUrl,
    account,
    provider: provider as EthereumProvider,
  });
}

export type WriteClient = ReturnType<typeof writeClient>;

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

  if (raw.includes("sim_getFeeConfig") || raw.includes("Fee policy estimation is not supported")) {
    return "This network does not provide transaction fee estimation, which consensus v0.6 writes require. Nothing was sent.";
  }

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
