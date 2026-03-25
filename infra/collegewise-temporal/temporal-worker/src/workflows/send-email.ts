import { proxyActivities } from "@temporalio/workflow";
import type { SendNotificationInput, NotificationResult } from "../shared/types";
import type * as notificationActivities from "../activities/notification";

const notify = proxyActivities<typeof notificationActivities>({
  startToCloseTimeout: "20s",
  retry: {
    maximumAttempts: 3,
    initialInterval: "60s",
    backoffCoefficient: 2,
    maximumInterval: "5m",
  },
});

/**
 * SendNotification — standalone notification workflow.
 *
 * For ad-hoc notifications outside the payment cycle.
 * Delegates to Magento's notification API for templating and delivery.
 */
export async function sendNotificationWorkflow(
  input: SendNotificationInput
): Promise<NotificationResult> {
  return await notify.sendNotification(input);
}
