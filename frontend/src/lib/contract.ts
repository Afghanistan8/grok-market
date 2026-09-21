import { isSuccessful } from "genlayer-js";

import { env, isConfigured } from "./env";
import { readClient, writeClient } from "./genlayer";
import type {
  ActivityItem,
  Claimable,
  Evidence,
  Market,
  Page,
  PortfolioRow,
  Position,
  Stats,
  Universe,
} from "./types";

export const PAGE_SIZE = 50;

class NotConfiguredError extends Error {
  constructor() {
    super("No contract address is set in src/lib/env.ts");
    this.name = "NotConfiguredError";
  }
}

async function view<T>(functionName: string, args: unknown[] = []): Promise<T> {
  if (!isConfigured) throw new NotConfiguredError();
  const client = readClient();
  const result = await client.readContract({
    address: env.contractAddress as `0x${string}`,
    functionName,
    args: args as never,
  });
  return result as T;
}

/* ------------------------------------------------------------------ reads */

export const api = {
  universe: () => view<Universe>("get_supported_universe"),
  stats: () => view<Stats>("get_stats"),
  market: (id: number) => view<Market>("get_market", [id]),
  phase: (id: number) => view<string>("get_market_phase", [id]),
  markets: (offset = 0, limit = PAGE_SIZE) => view<Page<Market>>("get_markets", [offset, limit]),
  openMarkets: (offset = 0, limit = PAGE_SIZE) =>
    view<Page<Market>>("get_open_markets", [offset, limit]),
  byCategory: (category: string, offset = 0, limit = PAGE_SIZE) =>
    view<Page<Market>>("get_markets_by_category", [category, offset, limit]),
  byUniqueKey: (kind: string, category: string, asset: string, day: string) =>
    view<{ exists: boolean; market_id?: number }>("get_market_by_unique_key", [
      kind,
      category,
      asset,
      day,
    ]),
  position: (id: number, wallet: string) => view<Position>("get_position", [id, wallet]),
  claimable: (id: number, wallet: string) => view<Claimable>("get_claimable", [id, wallet]),
  marketPositions: (id: number, offset = 0, limit = PAGE_SIZE) =>
    view<Page<{ owner: string; side: string; stake: string; claimed: boolean }>>(
      "get_market_positions",
      [id, offset, limit],
    ),
  userMarkets: (wallet: string, offset = 0, limit = PAGE_SIZE) =>
    view<Page<Market>>("get_user_markets", [wallet, offset, limit]),
  userPositions: (wallet: string, offset = 0, limit = PAGE_SIZE) =>
    view<Page<PortfolioRow>>("get_user_positions", [wallet, offset, limit]),
  evidence: (id: number) => view<Evidence>("get_settlement_evidence", [id]),
  activity: (offset = 0, limit = PAGE_SIZE) =>
    view<Page<ActivityItem>>("get_activity", [offset, limit]),
};

/* ----------------------------------------------------------------- writes */

export interface WriteContext {
  account: `0x${string}`;
  provider: unknown;
}

/** What a decided write returned. */
export interface WriteOutcome {
  hash: string;
  /** The contract method's return value, decoded to a string. */
  value: string;
  /** The fee quote the transaction was submitted with. */
  fees: TransactionFees;
}

/** The fee fields passed into writeContract, taken unchanged from the estimate. */
export interface TransactionFees {
  distribution: unknown;
  messageAllocations?: unknown;
  feeValue: bigint;
}

/** Thrown when validators decided the call and the contract reverted it. */
export class ContractRevert extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractRevert";
  }
}

interface DecidedReceipt {
  consensus_data?: {
    leader_receipt?: { execution_result?: string; result?: { status?: string; payload?: unknown } }[];
  };
}

/** Studio receipts wrap return values as ``{ readable: "<json text>" }``. */
function decodeReturn(payload: unknown): string {
  if (payload && typeof payload === "object" && "readable" in payload) {
    const readable = String((payload as { readable: unknown }).readable);
    try {
      const parsed = JSON.parse(readable);
      return typeof parsed === "string" ? parsed : String(parsed);
    } catch {
      return readable;
    }
  }
  return payload === undefined || payload === null ? "" : String(payload);
}

/**
 * The one path every contract write takes (consensus v0.6 fee flow):
 *
 * 1. quote this exact call with ``estimateTransactionFeesForWrite``;
 * 2. submit it with ``writeContract``, passing the returned ``distribution``,
 *    ``messageAllocations`` and ``feeValue`` unchanged;
 * 3. wait until validators decide it, and treat it as done only if
 *    ``isSuccessful`` agrees: status ACCEPTED or FINALIZED *and* execution
 *    result FINISHED_WITH_RETURN. Otherwise the contract's own revert message
 *    is thrown.
 */
async function send(
  ctx: WriteContext,
  functionName: string,
  args: unknown[],
  value: bigint,
): Promise<WriteOutcome> {
  if (!isConfigured) throw new NotConfiguredError();
  const client = writeClient(ctx.account, ctx.provider);
  const request = {
    address: env.contractAddress as `0x${string}`,
    functionName,
    args: args as never,
    value,
  };

  const estimate = await client.estimateTransactionFeesForWrite(request);
  const fees: TransactionFees = {
    distribution: estimate.distribution,
    messageAllocations: estimate.messageAllocations,
    feeValue: estimate.feeValue,
  };

  const hash = String(await client.writeContract({ ...request, fees: fees as never }));

  const receipt = await client.waitForTransactionReceipt({
    hash: hash as never,
    waitUntil: "decided",
    interval: 3000,
    retries: 100,
  });

  const leader = (receipt as unknown as DecidedReceipt).consensus_data?.leader_receipt?.[0];
  const returned = decodeReturn(leader?.result?.payload);
  if (!isSuccessful(receipt as never)) {
    throw new ContractRevert(returned || "The contract rejected this transaction.");
  }
  return { hash, value: returned, fees };
}

export const writes = {
  createMarket: (ctx: WriteContext, kind: string, category: string, asset: string, day: string) =>
    send(ctx, "create_market", [kind, category, asset, day], 0n),

  /** Returns ``STAKED:<total wei>`` or ``REFUNDED:<reason>``. */
  takePosition: (ctx: WriteContext, marketId: number, side: string, amount: bigint) =>
    send(ctx, "take_position", [marketId, side], amount),

  resolveMarket: (ctx: WriteContext, marketId: number) =>
    send(ctx, "resolve_market", [marketId], 0n),

  claim: (ctx: WriteContext, marketId: number) => send(ctx, "claim", [marketId], 0n),
};

export { NotConfiguredError };
