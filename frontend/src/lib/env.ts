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

/**
 * The live deployment on studionet. Fixed in code on purpose: an environment
 * variable could silently point a hosted build at a stale contract.
 */
const CONTRACT_ADDRESS = "0x7b5701387e5154D1942cd2cE3B39cA51b39a39FF";

function read(key: string, fallback: string): string {
  const raw = import.meta.env[key as keyof ImportMetaEnv];
  if (typeof raw !== "string") return fallback;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

export const env = {
  contractAddress: CONTRACT_ADDRESS as `0x${string}`,
  rpcUrl: network.rpcUrl,
  walletConnectProjectId: read("VITE_WALLETCONNECT_PROJECT_ID", ""),
  defaultRpc: network.rpcUrl,
} as const;

export const CHAIN_ID = network.chainId;
export const EXPLORER = network.explorer;
export const FAUCET = network.faucet;

export const isConfigured = env.contractAddress.length > 0;
