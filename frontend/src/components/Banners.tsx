import { useEffect, useState } from "react";
import { useAccount } from "wagmi";

import { BANNED_RPC_FRAGMENT, CHAIN_ID, env, hasRpcHazard, isConfigured } from "../lib/env";

/**
 * A wallet that saved the zkSync-OS endpoint for chain 4221 will keep answering
 * `-32005 transaction gas rate limit exceeded` on every write, so this warning
 * is persistent rather than dismissible.
 */
export function RpcBanner() {
  const { connector, isConnected } = useAccount();
  const [badRpc, setBadRpc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Only Bradbury has a ChainList entry that answers -32005.
    if (!hasRpcHazard || !isConnected || !connector) {
      setBadRpc(null);
      return;
    }
    (async () => {
      try {
        const provider = (await connector.getProvider()) as {
          request?: (args: { method: string }) => Promise<unknown>;
        };
        const chainId = (await provider.request?.({ method: "eth_chainId" })) as string | undefined;
        if (cancelled || !chainId) return;
        if (parseInt(chainId, 16) !== CHAIN_ID) return;

        // MetaMask does not expose its RPC URL, so probe the endpoint the app
        // would use and surface the rate limit if that is what answers.
        const response = await fetch(env.rpcUrl, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_chainId", params: [] }),
        });
        const body = await response.json();
        if (!cancelled && JSON.stringify(body).includes("-32005")) {
          setBadRpc(env.rpcUrl);
        }
      } catch {
        // A probe failure is not itself evidence of a bad RPC.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [connector, isConnected]);

  if (!badRpc) return null;

  return (
    <div className="border-b border-rose-500/30 bg-rose-500/10 px-4 py-2.5">
      <p className="mx-auto max-w-6xl text-xs text-rose-200">
        <strong className="font-semibold">Your RPC is rate limiting transactions.</strong> Open
        MetaMask → Settings → Networks → GenLayer and set the RPC URL to{" "}
        <code className="rounded bg-black/40 px-1">{env.defaultRpc}</code>. The ChainList entry
        that points at <code className="rounded bg-black/40 px-1">{BANNED_RPC_FRAGMENT}</code>{" "}
        answers <code>-32005</code> and your transactions will never land.
      </p>
    </div>
  );
}

export function ConfigBanner() {
  if (isConfigured) return null;
  return (
    <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2.5">
      <p className="mx-auto max-w-6xl text-xs text-amber-200">
        <strong className="font-semibold">No contract address configured.</strong> Deploy{" "}
        <code className="rounded bg-black/40 px-1">contracts/GrokMarket.py</code> and
        set <code className="rounded bg-black/40 px-1">VITE_GROKMARKET_CONTRACT_ADDRESS</code>.
        Until then the board stays empty.
      </p>
    </div>
  );
}
