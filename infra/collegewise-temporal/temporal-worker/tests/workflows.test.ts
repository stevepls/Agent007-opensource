import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { TestWorkflowEnvironment } from "@temporalio/testing";
import { Worker } from "@temporalio/worker";
import type { NotificationResult } from "../src/shared/types";

const TASK_QUEUE = "test-send-notification";

describe("sendNotificationWorkflow", () => {
  let env: TestWorkflowEnvironment;

  beforeAll(async () => {
    env = await TestWorkflowEnvironment.createLocal();
  });

  afterAll(async () => {
    await env?.teardown();
  });

  it("delegates to Magento notification API and returns result", async () => {
    const worker = await Worker.create({
      connection: env.nativeConnection,
      taskQueue: TASK_QUEUE,
      workflowsPath: require.resolve("../src/workflows"),
      activities: {
        sendNotification: async (): Promise<NotificationResult> => ({
          success: true,
          notificationId: "notif-wf-test",
        }),
      },
    });

    const result = await worker.runUntil(
      env.client.workflow.execute("sendNotificationWorkflow", {
        args: [
          {
            type: "payment_reminder",
            paymentPlanId: 42,
            orderId: 1001,
            customerId: 555,
            customerEmail: "user@example.com",
            data: { amount: 50.0 },
          },
        ],
        taskQueue: TASK_QUEUE,
        workflowId: "test-send-notification",
      })
    );

    expect(result.success).toBe(true);
    expect(result.notificationId).toBe("notif-wf-test");
  });
});
