/**
 * Vite inlines VITE_* at build time. Every value here has a safe fallback so a
 * missing variable degrades the app instead of breaking a hosted deploy.
 */

/** ChainList also lists this host for chain 4221. It rate limits writes. */
export const BANNED_RPC_FRAGMENT = "zksync-os-testnet-genlayer.zksync.dev";

export interface NetworkPreset {
  key: string;
  chainId: number;
  name: string;
  short: string;
  rpcUrl: string;
  explorer: string;
  faucet: string;
  /** genlayer-js chain export name for this network. */
  chainExport: "testnetBradbury" | "studionet" | "testnetAsimov";
}

export const NETWORKS: Record<string, NetworkPreset> = {
  bradbury: {
    key: "bradbury",
    chainId: 4221,
    name: "GenLayer Testnet Bradbury",
    short: "Bradbury",
    rpcUrl: "https://rpc-bradbury.genlayer.com",
    explorer: "https://explorer-bradbury.genlayer.com",
    faucet: "https://testnet-faucet.genlayer.foundation",
    chainExport: "testnetBradbury",
  },
  studionet: {
    key: "studionet",
    chainId: 61999,
    name: "GenLayer Studio Network",
    short: "Studionet",
    rpcUrl: "https://studio.genlayer.com/api",
    explorer: "https://explorer-studio.genlayer.com",
    faucet: "https://studio.genlayer.com",
    chainExport: "studionet",
  },
  asimov: {
    key: "asimov",
    chainId: 4221,
    name: "GenLayer Testnet Asimov",
    short: "Asimov",
    rpcUrl: "https://rpc-asimov.genlayer.com",
    explorer: "https://explorer-asimov.genlayer.com",
    faucet: "https://testnet-faucet.genlayer.foundation",
    chainExport: "testnetAsimov",
  },
};

const DEFAULT_NETWORK = "bradbury";

function read(key: string, fallback: string): string {
  const raw = import.meta.env[key as keyof ImportMetaEnv];
  if (typeof raw !== "string") return fallback;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : fallback;
}

function resolveNetwork(): NetworkPreset {
  const requested = read("VITE_GENLAYER_NETWORK", DEFAULT_NETWORK).toLowerCase();
  return NETWORKS[requested] ?? NETWORKS[DEFAULT_NETWORK];
}

export const network = resolveNetwork();

function resolveRpc(preset: NetworkPreset): string {
  const configured = read("VITE_GENLAYER_RPC_URL", preset.rpcUrl);
  // Never let the rate-limited ChainList host through, however it got set.
  return configured.includes(BANNED_RPC_FRAGMENT) ? preset.rpcUrl : configured;
}

export const env = {
  contractAddress: read("VITE_GROKMARKET_CONTRACT_ADDRESS", "") as `0x${string}` | "",
  rpcUrl: resolveRpc(network),
  walletConnectProjectId: read("VITE_WALLETCONNECT_PROJECT_ID", ""),
  defaultRpc: network.rpcUrl,
} as const;

export const CHAIN_ID = network.chainId;
export const EXPLORER = network.explorer;
export const FAUCET = network.faucet;

export const isConfigured = env.contractAddress.length > 0;

/** Bradbury is the only network with the -32005 ChainList RPC problem. */
export const hasRpcHazard = network.key === "bradbury";
