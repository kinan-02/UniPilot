const rateLimit = require("express-rate-limit");
const { RedisStore } = require("rate-limit-redis");
const Redis = require("ioredis");

let sharedRedisClient = null;

function createRedisStore() {
  if (!process.env.REDIS_URL || process.env.NODE_ENV === "test") {
    return null;
  }

  try {
    if (!sharedRedisClient) {
      sharedRedisClient = new Redis(process.env.REDIS_URL, {
        maxRetriesPerRequest: 1
      });

      sharedRedisClient.on("error", (error) => {
        console.error("[api] redis rate limit client error", error.message);
      });
    }

    return new RedisStore({
      prefix: "rl:auth:",
      sendCommand: (...argumentsList) => sharedRedisClient.call(argumentsList[0], ...argumentsList.slice(1))
    });
  } catch (_error) {
    return null;
  }
}

function createAuthRateLimiter() {
  const store = createRedisStore();
  const windowMs = Number(process.env.AUTH_RATE_LIMIT_WINDOW_MS || 60_000);
  const max = Number(process.env.AUTH_RATE_LIMIT_MAX || 5);

  return rateLimit({
    windowMs,
    max,
    standardHeaders: true,
    legacyHeaders: false,
    passOnStoreError: false,
    keyGenerator: (request) => `${request.ip}:${request.path}`,
    message: {
      success: false,
      data: null,
      error: "Too many authentication requests. Please try again later."
    },
    ...(store ? { store } : {})
  });
}

module.exports = {
  createAuthRateLimiter
};
