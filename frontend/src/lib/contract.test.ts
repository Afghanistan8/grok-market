/**
 * Source-level coverage for the shared write helper.
 *
 * Every contract write in the app goes through `writes.*` -> `send`, and `send`
 * must price the exact call with `estimateTransactionFeesForWrite` and submit
 * it with the returned fees. Only the network client is replaced here; the
 * helper, the fee plumbing and the SDK's own `isSuccessful` check are the real
 * code the browser runs.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const fake = vi.hoisted(() => ({
  estimateTransactionFeesForWrite: vi.fn(),
  writeContract: vi.fn(),
  waitForTransactionReceipt: vi.fn(),
  writeClient: vi.fn(),
}));

vi.mock("./genlayer", () => ({
  readClient: vi.fn(),
  writeClient: fake.writeClient,
}));

import { ContractRevert, writes, type WriteContext } from "./contract";
import { env } from "./env";

const CTX: WriteContext = {
  account: "0x299Cc62AC7Abc1FB4eda5D0B5E9395B4e40a4De3",
  provider: { request: vi.fn() },
};

/** A quote shaped like genlayer-js 2.0's TransactionFeeEstimate. */
function quote(feeValue: bigint) {
  return {
    distribution: { leaderTimeunitsAllocation: 200n, validatorTimeunitsAllocation: 400n, marker: feeValue },
    messageAllocations: [{ marker: feeValue }],
    feeValue,
    policy: { enabled: true },
  };
}

/** A decided studio receipt, as returned by waitForTransactionReceipt. */
function receipt(ok: boolean, payload: unknown) {
  return {
    status: "ACCEPTED",
    status_name: "ACCEPTED",
    txExecutionResultName: ok ? "FINISHED_WITH_RETURN" : "FINISHED_WITH_ERROR",
    consensus_data: {
      leader_receipt: [
        {
          execution_result: ok ? "SUCCESS" : "ERROR",
          result: { status: ok ? "return" : "rollback", payload },
        },
      ],
    },
  };
}

const CASES = [
  {
    name: "create",
    run: () => writes.createMarket(CTX, "A", "CRYPTO", "BTC", "2026-10-01"),
    functionName: "create_market",
    args: ["A", "CRYPTO", "BTC", "2026-10-01"],
    value: 0n,
    returned: { readable: "7" },
    decoded: "7",
  },
  {
    name: "stake",
    run: () => writes.takePosition(CTX, 7, "UP", 2n * 10n ** 18n),
    functionName: "take_position",
    args: [7, "UP"],
    value: 2n * 10n ** 18n,
    returned: { readable: '"STAKED:2000000000000000000"' },
    decoded: "STAKED:2000000000000000000",
  },
  {
    name: "resolve",
    run: () => writes.resolveMarket(CTX, 7),
    functionName: "resolve_market",
    args: [7],
    value: 0n,
    returned: { readable: '"UP"' },
    decoded: "UP",
  },
  {
    name: "claim",
    run: () => writes.claim(CTX, 7),
    functionName: "claim",
    args: [7],
    value: 0n,
    returned: { readable: "5000000000000000000" },
    decoded: "5000000000000000000",
  },
] as const;

beforeEach(() => {
  vi.clearAllMocks();
  fake.writeClient.mockReturnValue({
    estimateTransactionFeesForWrite: fake.estimateTransactionFeesForWrite,
    writeContract: fake.writeContract,
    waitForTransactionReceipt: fake.waitForTransactionReceipt,
  });
  fake.writeContract.mockResolvedValue("0xabc123");
});

describe.each(CASES)("$name uses the estimated fees", (c) => {
  it("prices this exact call before submitting it", async () => {
    fake.estimateTransactionFeesForWrite.mockResolvedValue(quote(111n));
    fake.waitForTransactionReceipt.mockResolvedValue(receipt(true, c.returned));

    await c.run();

    expect(fake.estimateTransactionFeesForWrite).toHaveBeenCalledTimes(1);
    expect(fake.estimateTransactionFeesForWrite).toHaveBeenCalledWith({
      address: env.contractAddress,
      functionName: c.functionName,
      args: c.args,
      value: c.value,
    });
    const estimatedAt = fake.estimateTransactionFeesForWrite.mock.invocationCallOrder[0];
    const writtenAt = fake.writeContract.mock.invocationCallOrder[0];
    expect(estimatedAt).toBeLessThan(writtenAt);
  });

  it("passes the returned fees into writeContract unchanged", async () => {
    const estimate = quote(222n);
    fake.estimateTransactionFeesForWrite.mockResolvedValue(estimate);
    fake.waitForTransactionReceipt.mockResolvedValue(receipt(true, c.returned));

    const outcome = await c.run();

    expect(fake.writeContract).toHaveBeenCalledTimes(1);
    const submitted = fake.writeContract.mock.calls[0][0];
    expect(submitted).toMatchObject({
      address: env.contractAddress,
      functionName: c.functionName,
      args: c.args,
      value: c.value,
    });
    // Same objects, not look-alikes: nothing is rebuilt between quote and submit.
    expect(submitted.fees.distribution).toBe(estimate.distribution);
    expect(submitted.fees.messageAllocations).toBe(estimate.messageAllocations);
    expect(submitted.fees.feeValue).toBe(222n);
    expect(outcome.fees.feeValue).toBe(222n);
  });

  it("waits for a decision and returns the contract's value", async () => {
    fake.estimateTransactionFeesForWrite.mockResolvedValue(quote(1n));
    fake.waitForTransactionReceipt.mockResolvedValue(receipt(true, c.returned));

    const outcome = await c.run();

    expect(fake.waitForTransactionReceipt).toHaveBeenCalledWith(
      expect.objectContaining({ hash: "0xabc123", waitUntil: "decided" }),
    );
    expect(outcome).toMatchObject({ hash: "0xabc123", value: c.decoded });
  });

  it("never submits an unpriced transaction", async () => {
    fake.estimateTransactionFeesForWrite.mockRejectedValue(
      new Error('The method "sim_getFeeConfig" does not exist / is not available.'),
    );

    await expect(c.run()).rejects.toThrow("sim_getFeeConfig");
    expect(fake.writeContract).not.toHaveBeenCalled();
  });

  it("surfaces the contract's revert message when execution fails", async () => {
    fake.estimateTransactionFeesForWrite.mockResolvedValue(quote(1n));
    fake.waitForTransactionReceipt.mockResolvedValue(
      receipt(false, "EXPECTED: market is not resolved yet"),
    );

    await expect(c.run()).rejects.toThrow(new ContractRevert("EXPECTED: market is not resolved yet"));
  });
});

describe("fee quotes are per transaction", () => {
  it("re-estimates for every write instead of reusing a quote", async () => {
    fake.estimateTransactionFeesForWrite
      .mockResolvedValueOnce(quote(10n))
      .mockResolvedValueOnce(quote(20n));
    fake.waitForTransactionReceipt.mockResolvedValue(receipt(true, { readable: '"STAKED:1"' }));

    await writes.takePosition(CTX, 1, "UP", 2n * 10n ** 18n);
    await writes.takePosition(CTX, 1, "UP", 3n * 10n ** 18n);

    expect(fake.estimateTransactionFeesForWrite).toHaveBeenCalledTimes(2);
    expect(fake.estimateTransactionFeesForWrite.mock.calls[1][0].value).toBe(3n * 10n ** 18n);
    expect(fake.writeContract.mock.calls.map((call) => call[0].fees.feeValue)).toEqual([10n, 20n]);
  });

  it("uses the connected wallet for every write", async () => {
    fake.estimateTransactionFeesForWrite.mockResolvedValue(quote(1n));
    fake.waitForTransactionReceipt.mockResolvedValue(receipt(true, { readable: '"UP"' }));

    await writes.resolveMarket(CTX, 3);

    expect(fake.writeClient).toHaveBeenCalledWith(CTX.account, CTX.provider);
  });
});
