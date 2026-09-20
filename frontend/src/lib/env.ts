/**
 * Vite inlines VITE_* at build time. Every value here has a safe fallback so a
 * missing variable degrades the app instead of breaking a hosted deploy.
 */

const DEFAULT_RPC = "https://rpc-bradbury.genlayer.com";

/** ChainList also lists this host for chain 4221. It rate limits writes. */
export const BANNED_RPC_FRAGMENT = "zksync-os-testnet-genlayer.zksync.dev";

function read(key: string, fallback: string): string {
  const raw = import.meta.env[key as keyof ImportMetaEnv];
  if (typeof raw !== "string") return fallback;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

function normalizeRpc(url: string): string {
  if (url.includes(BANNED_RPC_FRAGMENT)) return DEFAULT_RPC;
  return url;
}

export const env = {
  contractAddress: read("VITE_GROKMARKET_CONTRACT_ADDRESS", "") as `0x${string}` | "",
  rpcUrl: normalizeRpc(read("VITE_GENLAYER_RPC_URL", DEFAULT_RPC)),
  walletConnectProjectId: read("VITE_WALLETCONNECT_PROJECT_ID", ""),
  defaultRpc: DEFAULT_RPC,
} as const;

export const CHAIN_ID = 4221;
export const EXPLORER = "https://explorer-bradbury.genlayer.com";
export const FAUCET = "https://testnet-faucet.genlayer.foundation";

export const isConfigured = env.contractAddress.length > 0;
