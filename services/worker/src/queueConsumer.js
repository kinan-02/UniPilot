const QUEUE_POLL_TIMEOUT_SECONDS = 5;
const PROCESS_RETRY_DELAY_MS = 2000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function processJob(jobId) {
  const apiBaseUrl = (process.env.API_SERVICE_URL || "http://api:8000").replace(/\/$/, "");
  const token = (process.env.INTERNAL_SERVICE_TOKEN || "").trim();
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["X-Internal-Service-Token"] = token;
  }

  const response = await fetch(`${apiBaseUrl}/internal/ai-jobs/${jobId}/process`, {
    method: "POST",
    headers,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Process failed for job ${jobId}: ${response.status} ${body}`);
  }

  return response.json();
}

function createRedisClient() {
  const redisUrl = (process.env.REDIS_URL || "").trim();
  if (!redisUrl) {
    return null;
  }

  // Lazy require so health server still starts if redis is temporarily unavailable.
  // eslint-disable-next-line global-require
  const Redis = require("ioredis");
  return new Redis(redisUrl, {
    maxRetriesPerRequest: null,
    enableReadyCheck: true,
  });
}

async function startQueueConsumer() {
  const queueName = (process.env.WORKER_QUEUE_NAME || "ai_jobs").trim() || "ai_jobs";
  const redis = createRedisClient();

  if (!redis) {
    console.warn("[worker] REDIS_URL not set — queue consumer disabled");
    return;
  }

  console.log(`[worker] consuming queue "${queueName}"`);

  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      const result = await redis.brpop(queueName, QUEUE_POLL_TIMEOUT_SECONDS);
      if (!result) {
        continue;
      }

      const jobId = String(result[1] || "").trim();
      if (!jobId) {
        continue;
      }

      console.log(`[worker] picked up job ${jobId}`);
      await processJob(jobId);
      console.log(`[worker] completed job ${jobId}`);
    } catch (error) {
      console.error("[worker] queue consumer error:", error);
      await sleep(PROCESS_RETRY_DELAY_MS);
    }
  }
}

module.exports = {
  startQueueConsumer,
  processJob,
};
