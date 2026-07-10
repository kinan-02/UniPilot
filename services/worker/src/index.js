const express = require("express");
const { startQueueConsumer } = require("./queueConsumer");
const { startWatchdogCron } = require("./watchdogCron");

const app = express();
const port = Number(process.env.WORKER_PORT) || 3002;

app.get("/health", (_req, res) => {
  res.status(200).json({
    service: "worker",
    status: "ok",
    timestamp: new Date().toISOString(),
    queue: process.env.WORKER_QUEUE_NAME || "ai_jobs",
  });
});

app.listen(port, "0.0.0.0", () => {
  console.log(`[worker] listening on port ${port}`);
  startQueueConsumer().catch((error) => {
    console.error("[worker] failed to start queue consumer:", error);
  });
  startWatchdogCron();
});
