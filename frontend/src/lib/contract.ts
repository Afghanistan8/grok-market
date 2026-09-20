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
    super("VITE_GROKMARKET_CONTRACT_ADDRESS is not set");
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

async function send(
  ctx: WriteContext,
  functionName: string,
  args: unknown[],
  value: bigint,
): Promise<string> {
  if (!isConfigured) throw new NotConfiguredError();
  const client = writeClient(ctx.account, ctx.provider);
  const hash = await client.writeContract({
    address: env.contractAddress as `0x${string}`,
    functionName,
    args: args as never,
    value,
  });
  return String(hash);
}

export const writes = {
  createMarket: (ctx: WriteContext, kind: string, category: string, asset: string, day: string) =>
    send(ctx, "create_market", [kind, category, asset, day], 0n),

  takePosition: (ctx: WriteContext, marketId: number, side: string, amount: bigint) =>
    send(ctx, "take_position", [marketId, side], amount),

  resolveMarket: (ctx: WriteContext, marketId: number) =>
    send(ctx, "resolve_market", [marketId], 0n),

  claim: (ctx: WriteContext, marketId: number) => send(ctx, "claim", [marketId], 0n),
};

export { NotConfiguredError };
