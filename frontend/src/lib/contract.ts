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

interface WriteContext {
  account: `0x${string}`;
  provider: unknown;
}

/** What a decided write returned. */
export interface WriteOutcome {
  hash: string;
  /** The contract method's return value, decoded to a string. */
  value: string;
}

/** Thrown when validators decided the call and the contract reverted it. */
export class ContractRevert extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractRevert";
  }
}

interface LeaderResult {
  execution_result?: string;
  result?: { status?: string; payload?: unknown };
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
 * Submits a write and waits for validators to decide it.
 *
 * A submitted transaction is not a successful one: the contract can still
 * revert it after consensus. So this waits for the decision, then reads the
 * leader's execution result and either returns the method's return value or
 * throws the contract's own revert message.
 */
async function send(
  ctx: WriteContext,
  functionName: string,
  args: unknown[],
  value: bigint,
): Promise<WriteOutcome> {
  if (!isConfigured) throw new NotConfiguredError();
  const client = writeClient(ctx.account, ctx.provider);
  const hash = String(
    await client.writeContract({
      address: env.contractAddress as `0x${string}`,
      functionName,
      args: args as never,
      value,
    }),
  ) as `0x${string}`;

  const receipt = (await client.waitForTransactionReceipt({
    hash: hash as never,
    status: "ACCEPTED" as never,
    interval: 3000,
    retries: 100,
  })) as unknown as { consensus_data?: { leader_receipt?: LeaderResult[] } };

  const leader = receipt.consensus_data?.leader_receipt?.[0];
  if (!leader) throw new ContractRevert("Validators did not return a result for this transaction.");
  if (leader.execution_result !== "SUCCESS") {
    throw new ContractRevert(decodeReturn(leader.result?.payload) || "The contract rejected this transaction.");
  }
  return { hash, value: decodeReturn(leader.result?.payload) };
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
