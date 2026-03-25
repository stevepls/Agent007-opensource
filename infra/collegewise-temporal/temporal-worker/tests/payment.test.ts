import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { chargeIdempotencyKey } from "../src/shared/idempotency";

describe("executeCharge", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = {
      ...originalEnv,
      CW_MAGENTO_API_URL: "https://test.collegewise.com",
      CW_MAGENTO_API_TOKEN: "test-token",
    };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.restoreAllMocks();
  });

  it("dry run returns success without calling Magento", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    // Re-import to pick up env vars
    const { executeCharge } = await import("../src/activities/payment");
    const result = await executeCharge(42, "2026-03-24", true);

    expect(result.success).toBe(true);
    expect(result.transactionId).toContain("dry-run-");
    expect(result.idempotencyKey).toBe(chargeIdempotencyKey(42, "2026-03-24"));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("calls the correct Magento endpoint with idempotency key", async () => {
    const expectedKey = chargeIdempotencyKey(99, "2026-06-15");

    const mockResponse = {
      ok: true,
      json: async () => ({
        success: true,
        transaction_id: "txn-abc123",
        auth_code: "AUTH99",
        amount: 49.99,
      }),
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse as Response);

    const { executeCharge } = await import("../src/activities/payment");
    const result = await executeCharge(99, "2026-06-15", false);

    expect(globalThis.fetch).toHaveBeenCalledOnce();
    const [url, opts] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe(
      "https://test.collegewise.com/rest/V1/collegewise/payment-plans/99/charge"
    );
    expect((opts as RequestInit).method).toBe("POST");
    expect((opts as RequestInit).headers).toMatchObject({
      "X-Idempotency-Key": expectedKey,
      Authorization: "Bearer test-token",
    });

    expect(result.success).toBe(true);
    expect(result.transactionId).toBe("txn-abc123");
    expect(result.amount).toBe(49.99);
    expect(result.idempotencyKey).toBe(expectedKey);
  });

  it("throws on non-OK Magento response (Temporal will retry)", async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      text: async () => "Internal Server Error",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockResponse as Response);

    const { executeCharge } = await import("../src/activities/payment");
    await expect(executeCharge(42, "2026-03-24", false)).rejects.toThrow(
      /Magento charge API returned 500/
    );
  });
});
