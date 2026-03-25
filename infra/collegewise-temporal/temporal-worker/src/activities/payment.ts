import type { ChargeResult } from "../shared/types";
import { chargeIdempotencyKey } from "../shared/idempotency";

const MAGENTO_BASE_URL = process.env.CW_MAGENTO_API_URL || "https://collegewise.com";
const MAGENTO_API_TOKEN = process.env.CW_MAGENTO_API_TOKEN || "";

/**
 * Trigger a recurring charge via the Magento REST API.
 *
 * Magento owns the Authorize.net integration and is the system of record.
 * This activity just tells Magento "process this charge" and reads back
 * the result. The idempotency key is passed so Magento can reject
 * duplicate attempts on its side.
 */
export async function executeCharge(
  paymentPlanId: number,
  chargeDate: string,
  dryRun: boolean = false
): Promise<ChargeResult> {
  const idempotencyKey = chargeIdempotencyKey(paymentPlanId, chargeDate);

  if (dryRun) {
    console.log(
      `[DRY RUN] Would call Magento to charge plan ${paymentPlanId} for ${chargeDate} (key: ${idempotencyKey})`
    );
    return {
      success: true,
      transactionId: `dry-run-${idempotencyKey}`,
      amount: 0,
      idempotencyKey,
    };
  }

  // TODO: Adjust the endpoint path to match your Magento custom API route
  // for processing a recurring payment plan charge.
  const url = `${MAGENTO_BASE_URL}/rest/V1/collegewise/payment-plans/${paymentPlanId}/charge`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${MAGENTO_API_TOKEN}`,
      "X-Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ chargeDate, idempotencyKey }),
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `Magento charge API returned ${response.status}: ${body}`
    );
  }

  const data = await response.json();

  return {
    success: data.success ?? true,
    transactionId: data.transaction_id,
    authCode: data.auth_code,
    errorCode: data.error_code,
    errorMessage: data.error_message,
    amount: data.amount,
    idempotencyKey,
  };
}
