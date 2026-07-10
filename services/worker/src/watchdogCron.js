const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

async function runWeeklyWatchdogScan() {
  const apiBaseUrl = (process.env.API_SERVICE_URL || "http://api:8000").replace(/\/$/, "");
  const token = (process.env.INTERNAL_SERVICE_TOKEN || "").trim();
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["X-Internal-Service-Token"] = token;
  }

  const response = await fetch(`${apiBaseUrl}/internal/watchdog/weekly-scan`, {
    method: "POST",
    headers,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Weekly watchdog scan failed: ${response.status} ${body}`);
  }

  const payload = await response.json();
  console.log("[worker] weekly watchdog scan queued:", JSON.stringify(payload));
  return payload;
}

function startWatchdogCron() {
  const enabled = (process.env.WATCHDOG_WEEKLY_SCAN_ENABLED || "").trim() === "true";
  if (!enabled) {
    return;
  }

  const intervalMs = Number(process.env.WATCHDOG_WEEKLY_SCAN_INTERVAL_MS || WEEK_MS);
  const safeInterval = Number.isFinite(intervalMs) && intervalMs > 0 ? intervalMs : WEEK_MS;

  const tick = () => {
    runWeeklyWatchdogScan().catch((error) => {
      console.error("[worker] weekly watchdog scan error:", error);
    });
  };

  console.log(`[worker] watchdog weekly scan enabled (intervalMs=${safeInterval})`);
  setInterval(tick, safeInterval);
}

module.exports = {
  runWeeklyWatchdogScan,
  startWatchdogCron,
};
