const express = require("express");

const app = express();
const port = Number(process.env.AI_SERVICE_PORT) || 3001;
const internalServiceToken = (process.env.INTERNAL_SERVICE_TOKEN || "").trim();

app.use(express.json());

function requireInternalServiceToken(req, res, next) {
  if (!internalServiceToken) {
    return next();
  }

  const provided = String(req.get("x-internal-service-token") || "").trim();
  if (provided !== internalServiceToken) {
    return res.status(401).json({
      success: false,
      data: null,
      error: "Unauthorized internal service request",
    });
  }

  return next();
}

app.get("/health", (_req, res) => {
  res.status(200).json({
    service: "ai",
    status: "ok",
    timestamp: new Date().toISOString()
  });
});

app.post("/infer", requireInternalServiceToken, (_req, res) => {
  res.status(202).json({
    status: "queued",
    message: "AI inference stub is active in skeleton mode."
  });
});

app.listen(port, "0.0.0.0", () => {
  console.log(`[ai] listening on port ${port}`);
});
