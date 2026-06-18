const express = require("express");

const app = express();
const port = Number(process.env.AI_SERVICE_PORT) || 3001;

app.use(express.json());

app.get("/health", (_req, res) => {
  res.status(200).json({
    service: "ai",
    status: "ok",
    timestamp: new Date().toISOString()
  });
});

app.post("/infer", (_req, res) => {
  res.status(202).json({
    status: "queued",
    message: "AI inference stub is active in skeleton mode."
  });
});

app.listen(port, "0.0.0.0", () => {
  console.log(`[ai] listening on port ${port}`);
});
