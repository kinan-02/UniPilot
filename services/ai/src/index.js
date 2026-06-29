const express = require("express");
const { spawn } = require("child_process");
const path = require("path");

const app = express();
const port = Number(process.env.AI_SERVICE_PORT) || 3001;
const internalServiceToken = (process.env.INTERNAL_SERVICE_TOKEN || "").trim();
const academicWikiPath = (process.env.ACADEMIC_WIKI_PATH || "").trim();
const academicTechnionRawDir = (process.env.ACADEMIC_TECHNION_RAW_DIR || "").trim();
const academicDefaultSemester = (process.env.ACADEMIC_DEFAULT_SEMESTER_FILE || "").trim();
const academicCatalogJson = (process.env.ACADEMIC_CATALOG_JSON || "").trim();
const graphBridgeScript = path.join(__dirname, "graph_bridge.py");

function graphBridgeBasePayload(extra = {}) {
  return {
    md_dir_path: academicWikiPath,
    technion_raw_dir: academicTechnionRawDir,
    semester_filename: academicDefaultSemester || undefined,
    json_file_path: academicCatalogJson || undefined,
    ...extra,
  };
}

function isGraphConfigured() {
  return Boolean(academicWikiPath && (academicTechnionRawDir || academicCatalogJson));
}

let cachedGraphStats = null;

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

function callGraphBridge(payload) {
  return new Promise((resolve, reject) => {
    const proc = spawn("python3", [graphBridgeScript], {
      env: { ...process.env, PYTHONPATH: __dirname },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `graph_bridge exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout.trim()));
      } catch (err) {
        reject(new Error(`Invalid graph_bridge output: ${stdout || err.message}`));
      }
    });

    proc.stdin.write(JSON.stringify(payload));
    proc.stdin.end();
  });
}

async function refreshGraphStats() {
  if (!isGraphConfigured()) {
    cachedGraphStats = { configured: false };
    return cachedGraphStats;
  }

  try {
    const result = await callGraphBridge(graphBridgeBasePayload({ action: "stats" }));
    cachedGraphStats = result.success
      ? { configured: true, ...result.data }
      : { configured: true, error: result.error };
  } catch (err) {
    cachedGraphStats = { configured: true, error: err.message };
  }

  return cachedGraphStats;
}

refreshGraphStats().catch(() => {});

app.get("/health", async (_req, res) => {
  const stats = cachedGraphStats || (await refreshGraphStats());
  res.status(200).json({
    service: "ai",
    status: "ok",
    timestamp: new Date().toISOString(),
    academic_graph: stats,
  });
});

app.post("/retrieve", requireInternalServiceToken, async (req, res) => {
  const {
    intent,
    course_id: courseId,
    user_completed_courses: completed,
    wiki_slug: wikiSlug,
    search_query: searchQuery,
  } = req.body || {};

  if (!intent) {
    return res.status(400).json({
      success: false,
      data: null,
      error: "intent is required",
    });
  }

  if (!isGraphConfigured()) {
    return res.status(503).json({
      success: false,
      data: null,
      error: "Academic graph paths are not configured",
    });
  }

  try {
    const result = await callGraphBridge(
      graphBridgeBasePayload({
        action: "retrieve_context",
        intent,
        course_id: courseId,
        user_completed_courses: completed || [],
        wiki_slug: wikiSlug,
        search_query: searchQuery,
        semester_filename: req.body?.semester_filename,
      }),
    );

    if (!result.success) {
      return res.status(400).json(result);
    }

    return res.status(200).json(result);
  } catch (err) {
    return res.status(500).json({
      success: false,
      data: null,
      error: err.message,
    });
  }
});

app.post("/advise", requireInternalServiceToken, async (req, res) => {
  const { question, user_context: userContext } = req.body || {};

  if (!question || typeof question !== "string" || !question.trim()) {
    return res.status(400).json({
      success: false,
      data: null,
      error: "question is required",
    });
  }

  if (!isGraphConfigured()) {
    return res.status(503).json({
      success: false,
      data: null,
      error: "Academic graph paths are not configured",
    });
  }

  if (!process.env.OPENAI_API_KEY) {
    return res.status(503).json({
      success: false,
      data: null,
      error: "OPENAI_API_KEY is not configured",
    });
  }

  try {
    const result = await callGraphBridge(
      graphBridgeBasePayload({
        action: "advise",
        question: question.trim(),
        user_context: userContext || {},
      }),
    );

    if (!result.success) {
      return res.status(400).json(result);
    }

    return res.status(200).json(result);
  } catch (err) {
    return res.status(500).json({
      success: false,
      data: null,
      error: err.message,
    });
  }
});

app.post("/infer", requireInternalServiceToken, (_req, res) => {
  res.status(202).json({
    status: "queued",
    message: "AI inference stub is active in skeleton mode.",
  });
});

app.listen(port, "0.0.0.0", () => {
  console.log(`[ai] listening on port ${port}`);
});
