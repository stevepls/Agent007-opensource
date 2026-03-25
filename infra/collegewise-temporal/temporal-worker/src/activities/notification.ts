import type { SendNotificationInput, NotificationResult } from "../shared/types";

const MAGENTO_BASE_URL = process.env.CW_MAGENTO_API_URL || "https://collegewise.com";
const MAGENTO_API_TOKEN = process.env.CW_MAGENTO_API_TOKEN || "";

/**
 * Send a notification via Magento's notification API.
 *
 * Magento owns email templates, branding, and SMTP delivery.
 * The worker just tells Magento *what* happened and *who* to notify —
 * Magento decides how to render and send it.
 */
export async function sendNotification(
  input: SendNotificationInput
): Promise<NotificationResult> {
  const url = `${MAGENTO_BASE_URL}/rest/V1/collegewise/notifications`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${MAGENTO_API_TOKEN}`,
    },
    body: JSON.stringify({
      type: input.type,
      payment_plan_id: input.paymentPlanId,
      order_id: input.orderId,
      customer_id: input.customerId,
      customer_email: input.customerEmail,
      data: input.data,
    }),
    signal: AbortSignal.timeout(15_000),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `Magento notification API returned ${response.status}: ${body}`
    );
  }

  const result = await response.json();

  return {
    success: result.success ?? true,
    notificationId: result.notification_id,
    error: result.error,
  };
}
