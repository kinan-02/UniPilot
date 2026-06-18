const express = require("express");

function createApp() {
  const app = express();

  app.use(express.json());

  app.get("/health", (_req, res) => {
    res.status(200).json({
      service: "api",
      status: "ok",
      timestamp: new Date().toISOString(),
      dependencies: {
        mongo: process.env.MONGO_URI ? "configured" : "missing",
        redis: process.env.REDIS_URL ? "configured" : "missing",
        ai: process.env.AI_SERVICE_URL ? "configured" : "missing"
      }
    });
  });

  return app;
}

module.exports = { createApp };
