/**
 * Temporal Client — trigger workflows from outside the worker.
 *
 * Usage:
 *   npx ts-node src/client.ts cycle 42 2026-04-01
 *   npx ts-node src/client.ts cycle 42 2026-04-01 --dry-run
 *   npx ts-node src/client.ts email user@example.com "Subject" "Body text"
 *   npx ts-node src/client.ts cancel charge-cycle-42-2026-04-01
 *   npx ts-node src/client.ts payment-updated charge-cycle-42-2026-04-01
 */

import { Client, Connection } from "@temporalio/client";
import {
  recurringPaymentCycle,
  cancelCycleSignal,
  paymentMethodUpdatedSignal,
} from "./workflows/payment-cycle";
import { sendNotificationWorkflow } from "./workflows/send-email";

async function main() {
  const address = process.env.TEMPORAL_ADDRESS || "localhost:7233";
  const taskQueue = process.env.TEMPORAL_TASK_QUEUE || "collegewise-payments";
  const namespace = process.env.TEMPORAL_NAMESPACE || "default";

  const connection = await Connection.connect({ address });
  const client = new Client({ connection, namespace });

  const [command, ...args] = process.argv.slice(2);

  if (command === "cycle") {
    const planId = parseInt(args[0], 10);
    const chargeDate = args[1] || new Date().toISOString().split("T")[0];
    const dryRun = args.includes("--dry-run");

    const workflowId = `charge-cycle-${planId}-${chargeDate}`;
    console.log(
      `Starting RecurringPaymentCycle: plan=${planId}, date=${chargeDate}, dryRun=${dryRun}`
    );

    const handle = await client.workflow.start(recurringPaymentCycle, {
      args: [{
        paymentPlanId: planId,
        chargeDate,
        dryRun,
      }],
      taskQueue,
      workflowId,
    });

    console.log(`Workflow started: ${handle.workflowId}`);
    console.log("Waiting for result (this may take a while for real cycles)...");
    const result = await handle.result();
    console.log("Result:", JSON.stringify(result, null, 2));

  } else if (command === "notify") {
    const [type, planId, orderId, email] = args;

    console.log(`Starting SendNotification: type=${type}, plan=${planId}`);

    const handle = await client.workflow.start(sendNotificationWorkflow, {
      args: [{
        type,
        paymentPlanId: parseInt(planId, 10),
        orderId: parseInt(orderId, 10),
        customerId: 0,
        customerEmail: email,
        data: {},
      }],
      taskQueue,
      workflowId: `notify-${type}-${Date.now()}`,
    });

    console.log(`Workflow started: ${handle.workflowId}`);
    const result = await handle.result();
    console.log("Result:", JSON.stringify(result, null, 2));

  } else if (command === "cancel") {
    const workflowId = args[0];
    console.log(`Sending cancel signal to: ${workflowId}`);
    const handle = client.workflow.getHandle(workflowId);
    await handle.signal(cancelCycleSignal);
    console.log("Cancel signal sent.");

  } else if (command === "payment-updated") {
    const workflowId = args[0];
    console.log(`Sending paymentMethodUpdated signal to: ${workflowId}`);
    const handle = client.workflow.getHandle(workflowId);
    await handle.signal(paymentMethodUpdatedSignal);
    console.log("Signal sent.");

  } else {
    console.log("Usage:");
    console.log("  npx ts-node src/client.ts cycle <planId> <chargeDate> [--dry-run]");
    console.log("  npx ts-node src/client.ts notify <type> <planId> <orderId> <email>");
    console.log("  npx ts-node src/client.ts cancel <workflowId>");
    console.log("  npx ts-node src/client.ts payment-updated <workflowId>");
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Client error:", err);
  process.exit(1);
});
