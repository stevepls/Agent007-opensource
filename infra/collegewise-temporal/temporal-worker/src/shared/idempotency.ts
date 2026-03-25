import { createHash } from "crypto";

/**
 * Generate a deterministic idempotency key for a payment charge.
 * Same plan + same charge date = same key, preventing double-charges
 * even if Temporal replays the activity.
 */
export function chargeIdempotencyKey(
  paymentPlanId: number,
  chargeDate: string
): string {
  const raw = `charge:${paymentPlanId}:${chargeDate}`;
  return createHash("sha256").update(raw).digest("hex").slice(0, 32);
}
