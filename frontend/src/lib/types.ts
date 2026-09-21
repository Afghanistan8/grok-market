export type Kind = "A" | "B";
export type Category = "CRYPTO" | "STOCKS";

export type Phase =
  | "OPEN"
  | "WINDOW_LIVE"
  | "READY_TO_SETTLE"
  | "SETTLED_UP"
  | "SETTLED_DOWN"
  | "SETTLED_WINNER"
  | "INCONCLUSIVE";

export type MarketState = "UNRESOLVED" | "SETTLED" | "INCONCLUSIVE";

/** Wei amounts arrive as decimal strings: 6 GEN exceeds Number.MAX_SAFE_INTEGER. */
export type Wei = string;

export interface Market {
  found?: boolean;
  id: number;
  kind: Kind;
  category: Category;
  asset: string;
  universe: string[];
  target_day: string;
  target_day_index: number;
  created_at: number;
  cutoff_at: number;
  settles_at: number;
  terminal_refund_at: number;
  creator: string;
  pools: Record<string, Wei>;
  total_pool: Wei;
  leading: string;
  position_count: number;
  paid_out: Wei;
  state: MarketState;
  result: string;
  refund_all: boolean;
  resolved_at: number;
  phase: Phase;
  source_a: string;
  source_b: string;
  now: number;
}

export interface Page<T> {
  total: number;
  offset: number;
  scanned?: number;
  truncated?: boolean;
  items: T[];
}

export interface Position {
  found: boolean;
  market_id?: number;
  owner?: string;
  side: string;
  stake: Wei;
  claimed: boolean;
}

export interface Claimable {
  claimable: Wei;
  reason: string;
  side?: string;
  result?: string;
}

export interface PortfolioRow {
  market: Market;
  side: string;
  stake: Wei;
  claimed: boolean;
  claimable: Wei;
}

export interface EvidenceRow {
  symbol: string;
  a_open: number;
  a_close: number;
  a_bps: number;
  b_open: number;
  b_close: number;
  b_bps: number;
}

export interface Evidence {
  found: boolean;
  market_id?: number;
  kind?: Kind;
  category?: Category;
  target_day?: string;
  source_a?: string;
  source_b?: string;
  rows?: EvidenceRow[];
  a_verdict?: string;
  b_verdict?: string;
  final_result?: string;
  terminal_refund?: boolean;
  resolved_at?: number;
  payload?: string;
  price_scale?: number;
}

export interface ActivityItem {
  seq: number;
  kind: "CREATE" | "STAKE" | "REFUND" | "RESOLVE" | "CLAIM";
  market_id: number;
  actor: string;
  detail: string;
  amount: Wei;
  at: number;
}

export interface Stats {
  markets: number;
  open: number;
  window_live: number;
  ready_to_settle: number;
  settled: number;
  open_pool: Wei;
  activity: number;
  scanned: number;
  now: number;
}

export interface CategoryInfo {
  id: Category;
  assets: string[];
  source_a: string;
  source_b: string;
}

export interface Universe {
  kinds: { id: Kind; label: string }[];
  categories: CategoryInfo[];
  min_stake: Wei;
  max_stake: Wei;
  price_scale: number;
  utc_offset_seconds: number;
  max_forward_days: number;
  terminal_refund_delay: number;
  max_page: number;
}
