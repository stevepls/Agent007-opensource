import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { TestWorkflowEnvironment } from "@temporalio/testing";
import { Worker } from "@temporalio/worker";
import type {
  PaymentPlan,
  ChargeResult,
  NotificationResult,
  SendNotificationInput,
} from "../src/shared/types";
import { chargeIdempotencyKey } from "../src/shared/idempotency";

const TASK_QUEUE = "test-payment-cycle";

const MOCK_PLAN: PaymentPlan = {
  id: 42,
  orderId: 1001,
  customerId: 555,
  customerEmail: "jane@example.com",
  customerName: "Jane Doe",
  amount: 99.95,
  currency: "USD",
  frequency: "monthly",
  nextPaymentDate: "2026-03-24",
  status: "active",
};

function makeWorker(
  env: TestWorkflowEnvironment,
  overrides: {
    determineEligibility?: (...args: any[]) => Promise<PaymentPlan | null>;
    executeCharge?: (...args: any[]) => Promise<ChargeResult>;
    recordChargeResult?: (...args: any[]) => Promise<void>;
    sendNotification?: (input: SendNotificationInput) => Promise<NotificationResult>;
  } = {}
) {
  return Worker.create({
    connection: env.nativeConnection,
    taskQueue: TASK_QUEUE,
    workflowsPath: require.resolve("../src/workflows"),
    activities: {
      determineEligibility:
        overrides.determineEligibility ?? (async () => MOCK_PLAN),
      executeCharge:
        overrides.executeCharge ??
        (async (planId: number, chargeDate: string): Promise<ChargeResult> => ({
          success: true,
          transactionId: "txn-test-001",
          amount: 99.95,
          idempotencyKey: chargeIdempotencyKey(planId, chargeDate),
        })),
      recordChargeResult:
        overrides.recordChargeResult ?? (async () => {}),
      sendNotification:
        overrides.sendNotification ??
        (async (): Promise<NotificationResult> => ({
          success: true,
          notificationId: "notif-test",
        })),
    },
  });
}

describe("recurringPaymentCycle", () => {
  let env: TestWorkflowEnvironment;

  beforeAll(async () => {
    env = await TestWorkflowEnvironment.createLocal();
  });

  afterAll(async () => {
    await env?.teardown();
  });

  it("skips entire cycle when plan is not eligible", async () => {
    const worker = await makeWorker(env, {
      determineEligibility: async () => null,
    });

    const result = await worker.runUntil(
      env.client.workflow.execute("recurringPaymentCycle", {
        args: [{
          paymentPlanId: 42,
          chargeDate: "2026-03-24",
          reminderDaysBefore: [],
        }],
        taskQueue: TASK_QUEUE,
        workflowId: "test-cycle-ineligible",
      })
    );

    expect(result.charged).toBe(false);
    expect(result.phase).toBe("eligibility");
  });

  it("sends reminders then charges successfully", async () => {
    const notifications: SendNotificationInput[] = [];

    const worker = await makeWorker(env, {
      sendNotification: async (input): Promise<NotificationResult> => {
        notifications.push(input);
        return { success: true, notificationId: "notif-test" };
      },
    });

    const result = await worker.runUntil(
      env.client.workflow.execute("recurringPaymentCycle", {
        args: [{
          paymentPlanId: 42,
          chargeDate: new Date(Date.now() - 1000).toISOString().split("T")[0],
          reminderDaysBefore: [1],
          retryChargeDaysAfter: [],
        }],
        taskQueue: TASK_QUEUE,
        workflowId: "test-cycle-success",
      })
    );

    expect(result.charged).toBe(true);
    expect(result.transactionId).toBe("txn-test-001");
    expect(result.phase).toBe("charge");

    const types = notifications.map((n) => n.type);
    expect(types).toContain("payment_reminder");
    expect(types).toContain("payment_receipt");
  });

  it("passes structured data to notifications, not raw email content", async () => {
    const notifications: SendNotificationInput[] = [];

    const worker = await makeWorker(env, {
      sendNotification: async (input): Promise<NotificationResult> => {
        notifications.push(input);
        return { success: true };
      },
    });

    await worker.runUntil(
      env.client.workflow.execute("recurringPaymentCycle", {
        args: [{
          paymentPlanId: 42,
          chargeDate: new Date(Date.now() - 1000).toISOString().split("T")[0],
          reminderDaysBefore: [1],
          retryChargeDaysAfter: [],
        }],
        taskQueue: TASK_QUEUE,
        workflowId: "test-cycle-structured-data",
      })
    );

    // Reminder notification should have structured data
    const reminder = notifications.find((n) => n.type === "payment_reminder");
    expect(reminder).toBeDefined();
    expect(reminder!.paymentPlanId).toBe(42);
    expect(reminder!.orderId).toBe(1001);
    expect(reminder!.customerEmail).toBe("jane@example.com");
    expect(reminder!.data.amount).toBe(99.95);
    expect(reminder!.data.days_before).toBe(1);

    // Receipt notification should have transaction data
    const receipt = notifications.find((n) => n.type === "payment_receipt");
    expect(receipt).toBeDefined();
    expect(receipt!.data.transaction_id).toBe("txn-test-001");
  });

  it("retries charge and sends retry notification on first failure", async () => {
    let callCount = 0;
    const notifications: SendNotificationInput[] = [];

    const worker = await makeWorker(env, {
      executeCharge: async (
        planId: number,
        chargeDate: string
      ): Promise<ChargeResult> => {
        callCount++;
        if (callCount === 1) throw new Error("Gateway timeout");
        return {
          success: true,
          transactionId: "txn-retry-ok",
          amount: 99.95,
          idempotencyKey: chargeIdempotencyKey(planId, chargeDate),
        };
      },
      sendNotification: async (input): Promise<NotificationResult> => {
        notifications.push(input);
        return { success: true };
      },
    });

    const result = await worker.runUntil(
      env.client.workflow.execute("recurringPaymentCycle", {
        args: [{
          paymentPlanId: 42,
          chargeDate: new Date(Date.now() - 1000).toISOString().split("T")[0],
          reminderDaysBefore: [],
          retryChargeDaysAfter: [0],
        }],
        taskQueue: TASK_QUEUE,
        workflowId: "test-cycle-retry-success",
      })
    );

    expect(result.charged).toBe(true);
    expect(result.phase).toBe("retry-1");
    expect(callCount).toBe(2);

    const types = notifications.map((n) => n.type);
    expect(types).toContain("payment_failed_retry");
    expect(types).toContain("payment_receipt");

    const retryNotif = notifications.find((n) => n.type === "payment_failed_retry");
    expect(retryNotif!.data.error).toContain("Gateway timeout");
    expect(retryNotif!.data.attempt_number).toBe(1);
  });

  it("sends final failure notification after all retries exhausted", async () => {
    const notifications: SendNotificationInput[] = [];
    const recorded: boolean[] = [];

    const worker = await makeWorker(env, {
      executeCharge: async () => {
        throw new Error("Card declined");
      },
      recordChargeResult: async (
        _planId: number,
        _date: string,
        _txn: string | null,
        success: boolean
      ) => {
        recorded.push(success);
      },
      sendNotification: async (input): Promise<NotificationResult> => {
        notifications.push(input);
        return { success: true };
      },
    });

    const result = await worker.runUntil(
      env.client.workflow.execute("recurringPaymentCycle", {
        args: [{
          paymentPlanId: 42,
          chargeDate: new Date(Date.now() - 1000).toISOString().split("T")[0],
          reminderDaysBefore: [],
          retryChargeDaysAfter: [0, 0],
        }],
        taskQueue: TASK_QUEUE,
        workflowId: "test-cycle-all-fail",
      })
    );

    expect(result.charged).toBe(false);
    expect(result.phase).toBe("exhausted");

    expect(recorded).toEqual([false, false, false]);

    const types = notifications.map((n) => n.type);
    expect(types).toContain("payment_failed_retry");
    expect(types).toContain("payment_failed_final");

    const finalNotif = notifications.find((n) => n.type === "payment_failed_final");
    expect(finalNotif!.data.total_attempts).toBe(3);
  });

  it("charge succeeds even when notification fails", async () => {
    const worker = await makeWorker(env, {
      sendNotification: async (input): Promise<NotificationResult> => {
        if (input.type === "payment_receipt") {
          throw new Error("Magento notification API down");
        }
        return { success: true };
      },
    });

    const result = await worker.runUntil(
      env.client.workflow.execute("recurringPaymentCycle", {
        args: [{
          paymentPlanId: 42,
          chargeDate: new Date(Date.now() - 1000).toISOString().split("T")[0],
          reminderDaysBefore: [],
        }],
        taskQueue: TASK_QUEUE,
        workflowId: "test-cycle-notif-fails",
      })
    );

    expect(result.charged).toBe(true);
  });

  it("can be cancelled mid-cycle via signal", async () => {
    const worker = await makeWorker(env);

    const handle = await env.client.workflow.start("recurringPaymentCycle", {
      args: [{
        paymentPlanId: 42,
        chargeDate: "2099-01-01",
        reminderDaysBefore: [30],
      }],
      taskQueue: TASK_QUEUE,
      workflowId: "test-cycle-cancel",
    });

    await new Promise((r) => setTimeout(r, 500));
    await handle.signal("cancelCycle");

    const result = await worker.runUntil(handle.result());

    expect(result.charged).toBe(false);
    expect(result.phase).toBe("cancelled");
  });
});
