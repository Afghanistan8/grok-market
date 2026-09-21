/**
 * Grok-Market runs on GenLayer studionet only. The network is fixed here and is
 * not selectable at build time or at runtime.
 */

export const network = {
  chainId: 61999,
  name: "GenLayer Studio Network",
  short: "Studionet",
  rpcUrl: "https://studio.genlayer.com/api",
  explorer: "https://explorer-studio.genlayer.com",
  faucet: "https://studio.genlayer.com",
} as const;

/** The live deployment on studionet. */
const CONTRACT_ADDRESS = "0x1f774eb175CD0A1E82AB61422Fa231AD1bAC6742";

function read(key: string, fallback: string): string {
  const raw = import.meta.env[key as keyof ImportMetaEnv];
  if (typeof raw !== "string") return fallback;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

export const env = {
  // Overridable only so a redeploy of the contract does not need a code change.
  contractAddress: read("VITE_GROKMARKET_CONTRACT_ADDRESS", CONTRACT_ADDRESS) as `0x${string}`,
  rpcUrl: network.rpcUrl,
  walletConnectProjectId: read("VITE_WALLETCONNECT_PROJECT_ID", ""),
  defaultRpc: network.rpcUrl,
} as const;

export const CHAIN_ID = network.chainId;
export const EXPLORER = network.explorer;
export const FAUCET = network.faucet;

export const isConfigured = env.contractAddress.length > 0;
