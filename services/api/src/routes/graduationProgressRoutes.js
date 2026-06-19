const express = require("express");
const { getDatabase } = require("../db/mongoClient");
const { requireAuth } = require("../middleware/authMiddleware");
const { getGraduationProgressForUser } = require("../services/graduationProgressService");

function createGraduationProgressRouter() {
  const router = express.Router();

  router.get("/", requireAuth, async (request, response, next) => {
    try {
      const database = await getDatabase();
      const result = await getGraduationProgressForUser(database, request.auth.userId);

      if (result.status === "profile_not_found") {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Student profile not found"
        });
      }

      if (result.status === "degree_not_selected") {
        return response.status(400).json({
          success: false,
          data: null,
          error: "A degree must be selected on the student profile before graduation progress can be calculated"
        });
      }

      if (result.status === "degree_not_found") {
        return response.status(400).json({
          success: false,
          data: null,
          error: "Referenced degree was not found in the catalog"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          graduationProgress: result.progress
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  return router;
}

module.exports = {
  createGraduationProgressRouter
};
