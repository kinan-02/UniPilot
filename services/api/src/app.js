const express = require("express");
const { createAuthRouter } = require("./routes/authRoutes");
const { createCatalogRouter } = require("./routes/catalogRoutes");
const { createCompletedCourseRouter } = require("./routes/completedCourseRoutes");
const { createStudentProfileRouter } = require("./routes/studentProfileRoutes");

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

  app.use("/auth", createAuthRouter());
  app.use("/student-profile", createStudentProfileRouter());
  app.use("/completed-courses", createCompletedCourseRouter());
  app.use("/", createCatalogRouter());

  app.use((_request, response) => {
    response.status(404).json({
      success: false,
      data: null,
      error: "Route not found"
    });
  });

  app.use((error, _request, response, _next) => {
    console.error("[api] unhandled error", error);

    response.status(500).json({
      success: false,
      data: null,
      error: "Internal server error"
    });
  });

  return app;
}

module.exports = { createApp };
