import { defineChain } from "viem";
import { http, createConfig, injected } from "wagmi";
import { walletConnect } from "wagmi/connectors";

import { CHAIN_ID, EXPLORER, env } from "./env";

export const bradbury = defineChain({
  id: CHAIN_ID,
  name: "GenLayer Testnet Bradbury",
  nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 },
  rpcUrls: {
    default: { http: [env.rpcUrl] },
    public: { http: [env.rpcUrl] },
  },
  blockExplorers: {
    default: { name: "GenLayer Explorer", url: EXPLORER },
  },
  testnet: true,
});

const connectors = [
  injected({ shimDisconnect: true }),
  // WalletConnect is opt-in: without a project id, injected wallets still work.
  ...(env.walletConnectProjectId
    ? [
        walletConnect({
          projectId: env.walletConnectProjectId,
          showQrModal: true,
          metadata: {
            name: "Grok-Market",
            description: "Self-settling daily prediction markets on GenLayer",
            url: typeof window === "undefined" ? "https://localhost" : window.location.origin,
            icons: [],
          },
        }),
      ]
    : []),
];

export const wagmiConfig = createConfig({
  chains: [bradbury],
  connectors,
  transports: { [bradbury.id]: http(env.rpcUrl) },
  ssr: false,
});

declare module "wagmi" {
  interface Register {
    config: typeof wagmiConfig;
  }
}
