import { useCallback } from "react";
import { useAccount, useSwitchChain } from "wagmi";

import { CHAIN_ID } from "./env";

export interface WriteContext {
  account: `0x${string}`;
  provider: unknown;
}

/**
 * Resolves the EIP-1193 provider genlayer-js needs, after making sure the
 * wallet is actually on chain 4221.
 */
export function useWriteContext() {
  const { address, connector, chainId, isConnected } = useAccount();
  const { switchChainAsync } = useSwitchChain();

  const getContext = useCallback(async (): Promise<WriteContext> => {
    if (!isConnected || !address || !connector) {
      throw new Error("Connect a wallet first.");
    }
    if (chainId !== CHAIN_ID) {
      await switchChainAsync({ chainId: CHAIN_ID });
    }
    const provider = await connector.getProvider();
    return { account: address, provider };
  }, [address, connector, chainId, isConnected, switchChainAsync]);

  return {
    getContext,
    address,
    isConnected,
    isWrongChain: isConnected && chainId !== CHAIN_ID,
  };
}
