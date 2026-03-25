import {
  proxyActivities,
  sleep,
  defineSignal,
  setHandler,
} from "@temporalio/workflow";
import type {
  ChargeRecurringInput,
  PaymentPlan,
  NotificationResult,
} from "../shared/types";
import type * as dbActivities from "../activities/database";
import type * as paymentActivities from "../activities/payment";
import type * as notificationActivities from "../activities/notification";

const db = proxyActivities<typeof dbActivities>({
  startToCloseTimeout: "10s",
  retry: { maximumAttempts: 3 },
});

const payment = proxyActivities<typeof paymentActivities>({
  startToCloseTimeout: "45s",
  retry: {
    maximumAttempts: 3,
    initialInterval: "30s",
    backoffCoefficient: 2,
    maximumInterval: "5m",
  },
});

const notify = proxyActivities<typeof notificationActivities>({
  startToCloseTimeout: "20s",
  retry: {
    maximumAttempts: 3,
    initialInterval: "60s",
    backoffCoefficient: 2,
    maximumInterval: "10m",
  },
});

// -------------------------------------------------------------------------
// Signals
// -------------------------------------------------------------------------

export const cancelCycleSignal = defineSignal("cancelCycle");
export const paymentMethodUpdatedSignal = defineSignal("paymentMethodUpdated");

// -------------------------------------------------------------------------
// Configuration
// -------------------------------------------------------------------------

export interface PaymentCycleInput {
  paymentPlanId: number;
  chargeDate: string;
  dryRun?: boolean;
  reminderDaysBefore?: number[];
  retryChargeDaysAfter?: number[];
}

const DEFAULT_REMINDER_DAYS = [7, 3, 1];
const DEFAULT_RETRY_DAYS = [1, 3, 5];

export interface PaymentCycleResult {
  charged: boolean;
  transactionId?: string;
  reason?: string;
  phase: string;
  notificationsSent: string[];
}

// -------------------------------------------------------------------------
// Workflow
// -------------------------------------------------------------------------

/**
 * RecurringPaymentCycle — single durable workflow managing the full
 * lifecycle of one billing cycle for a payment plan.
 *
 * The worker orchestrates *when* things happen. Magento handles *how*:
 * - Charges go through Magento's charge endpoint (Authorize.net)
 * - Notifications go through Magento's notification API (templates + SMTP)
 *
 * This keeps templates, branding, and delivery in Magento where they
 * belong, while Temporal guarantees the schedule, retries, and ordering.
 */
export async function recurringPaymentCycle(
  input: PaymentCycleInput
): Promise<PaymentCycleResult> {
  const {
    paymentPlanId,
    chargeDate,
    dryRun = false,
    reminderDaysBefore = DEFAULT_REMINDER_DAYS,
    retryChargeDaysAfter = DEFAULT_RETRY_DAYS,
  } = input;

  let cancelled = false;
  let paymentMethodWasUpdated = false;
  const notificationsSent: string[] = [];

  setHandler(cancelCycleSignal, () => {
    cancelled = true;
  });
  setHandler(paymentMethodUpdatedSignal, () => {
    paymentMethodWasUpdated = true;
  });

  // ----- Step 1: Verify plan eligibility --------------------------------

  const plan = await db.determineEligibility(paymentPlanId, chargeDate);
  if (!plan) {
    return {
      charged: false,
      reason: "Plan not eligible for charge on this date",
      phase: "eligibility",
      notificationsSent,
    };
  }

  // ----- Step 2: Pre-charge reminder notifications ----------------------

  const chargeDateMs = new Date(chargeDate).getTime();

  for (const daysBefore of [...reminderDaysBefore].sort((a, b) => b - a)) {
    if (cancelled) break;

    const reminderDateMs = chargeDateMs - daysBefore * 86_400_000;
    const nowMs = Date.now();

    if (reminderDateMs > nowMs) {
      await sleep(reminderDateMs - nowMs);
    }

    if (cancelled) break;

    const stillActive = await db.determineEligibility(paymentPlanId, chargeDate);
    if (!stillActive) {
      return {
        charged: false,
        reason: "Plan became inactive during reminder phase",
        phase: "reminder",
        notificationsSent,
      };
    }

    try {
      await notify.sendNotification({
        type: "payment_reminder",
        paymentPlanId: plan.id,
        orderId: plan.orderId,
        customerId: plan.customerId,
        customerEmail: plan.customerEmail,
        data: {
          customer_name: plan.customerName,
          amount: plan.amount,
          currency: plan.currency,
          charge_date: chargeDate,
          days_before: daysBefore,
        },
      });
      notificationsSent.push(`reminder-${daysBefore}d`);
    } catch {
      // Reminder failure is non-critical
    }
  }

  if (cancelled) {
    return {
      charged: false,
      reason: "Cycle cancelled via signal",
      phase: "cancelled",
      notificationsSent,
    };
  }

  // ----- Step 3: Wait until charge date ---------------------------------

  const nowMs = Date.now();
  if (chargeDateMs > nowMs) {
    await sleep(chargeDateMs - nowMs);
  }

  if (cancelled) {
    return {
      charged: false,
      reason: "Cycle cancelled before charge",
      phase: "cancelled",
      notificationsSent,
    };
  }

  // ----- Step 4: Attempt charge (with retries on schedule) --------------

  const attempts = [0, ...retryChargeDaysAfter];
  let lastError = "";

  for (let i = 0; i < attempts.length; i++) {
    if (cancelled) break;

    if (i > 0) {
      const waitDays = attempts[i] - attempts[i - 1];
      await sleep(waitDays * 86_400_000);

      if (cancelled) break;

      if (paymentMethodWasUpdated) {
        paymentMethodWasUpdated = false;
      }
    }

    try {
      const chargeResult = await payment.executeCharge(
        paymentPlanId,
        chargeDate,
        dryRun
      );

      await db.recordChargeResult(
        paymentPlanId,
        chargeDate,
        chargeResult.transactionId ?? null,
        true,
        chargeResult.amount,
        null
      );

      try {
        await notify.sendNotification({
          type: "payment_receipt",
          paymentPlanId: plan.id,
          orderId: plan.orderId,
          customerId: plan.customerId,
          customerEmail: plan.customerEmail,
          data: {
            customer_name: plan.customerName,
            amount: chargeResult.amount,
            currency: plan.currency,
            transaction_id: chargeResult.transactionId ?? "",
            charge_date: chargeDate,
          },
        });
        notificationsSent.push("receipt");
      } catch {
        // Non-critical
      }

      return {
        charged: true,
        transactionId: chargeResult.transactionId,
        phase: i === 0 ? "charge" : `retry-${i}`,
        notificationsSent,
      };
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);

      await db.recordChargeResult(
        paymentPlanId,
        chargeDate,
        null,
        false,
        plan.amount,
        lastError
      );

      if (i < attempts.length - 1) {
        const nextRetryDays = attempts[i + 1] - attempts[i];
        try {
          await notify.sendNotification({
            type: "payment_failed_retry",
            paymentPlanId: plan.id,
            orderId: plan.orderId,
            customerId: plan.customerId,
            customerEmail: plan.customerEmail,
            data: {
              customer_name: plan.customerName,
              amount: plan.amount,
              currency: plan.currency,
              charge_date: chargeDate,
              error: lastError,
              next_retry_days: nextRetryDays,
              attempt_number: i + 1,
            },
          });
          notificationsSent.push(`retry-notice-${i + 1}`);
        } catch {
          // Non-critical
        }
      }
    }
  }

  // ----- Step 5: All retries exhausted ----------------------------------

  try {
    await notify.sendNotification({
      type: "payment_failed_final",
      paymentPlanId: plan.id,
      orderId: plan.orderId,
      customerId: plan.customerId,
      customerEmail: plan.customerEmail,
      data: {
        customer_name: plan.customerName,
        amount: plan.amount,
        currency: plan.currency,
        charge_date: chargeDate,
        error: lastError,
        total_attempts: attempts.length,
      },
    });
    notificationsSent.push("final-failure");
  } catch {
    // Non-critical
  }

  return {
    charged: false,
    reason: `All charge attempts failed. Last error: ${lastError}`,
    phase: "exhausted",
    notificationsSent,
  };
}
