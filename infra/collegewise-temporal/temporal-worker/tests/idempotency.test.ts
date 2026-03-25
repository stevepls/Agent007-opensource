import { describe, it, expect } from "vitest";
import { chargeIdempotencyKey } from "../src/shared/idempotency";

describe("chargeIdempotencyKey", () => {
  it("returns a 32-char hex string", () => {
    const key = chargeIdempotencyKey(42, "2026-03-24");
    expect(key).toMatch(/^[a-f0-9]{32}$/);
  });

  it("is deterministic — same inputs produce same key", () => {
    const a = chargeIdempotencyKey(42, "2026-03-24");
    const b = chargeIdempotencyKey(42, "2026-03-24");
    expect(a).toBe(b);
  });

  it("different plan IDs produce different keys", () => {
    const a = chargeIdempotencyKey(42, "2026-03-24");
    const b = chargeIdempotencyKey(43, "2026-03-24");
    expect(a).not.toBe(b);
  });

  it("different dates produce different keys", () => {
    const a = chargeIdempotencyKey(42, "2026-03-24");
    const b = chargeIdempotencyKey(42, "2026-04-24");
    expect(a).not.toBe(b);
  });
});
