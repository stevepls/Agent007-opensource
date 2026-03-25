import { Worker, NativeConnection } from "@temporalio/worker";
import * as activities from "./activities";

async function run() {
  const address = process.env.TEMPORAL_ADDRESS || "localhost:7233";
  const taskQueue = process.env.TEMPORAL_TASK_QUEUE || "collegewise-payments";
  const namespace = process.env.TEMPORAL_NAMESPACE || "default";

  console.log(`[Worker] Connecting to Temporal at ${address}`);
  console.log(`[Worker] Namespace: ${namespace}, Task Queue: ${taskQueue}`);

  const connection = await NativeConnection.connect({ address });

  const worker = await Worker.create({
    connection,
    namespace,
    taskQueue,
    workflowsPath: require.resolve("./workflows"),
    activities,
  });

  console.log(`[Worker] Started — listening on queue "${taskQueue}"`);
  await worker.run();
}

run().catch((err) => {
  console.error("[Worker] Fatal error:", err);
  process.exit(1);
});
