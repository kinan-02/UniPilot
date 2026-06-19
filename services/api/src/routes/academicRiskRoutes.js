const express = require("express");
const { getDatabase } = require("../db/mongoClient");
const { requireAuth } = require("../middleware/authMiddleware");
const {
  ensureAcademicRiskIndexes,
  toPublicAcademicRiskAnalysis,
  toPublicAcademicRiskSummary
} = require("../models/academicRiskModel");
const {
  analyzeAndStoreAcademicRisks,
  getAcademicRiskAnalysisForUser,
  listAcademicRiskAnalysesForUser
} = require("../services/academicRiskService");
const {
  validateAcademicRiskIdParam,
  validateAcademicRiskListQuery,
  validateAnalyzeAcademicRiskPayload
} = require("../validation/academicRiskSchemas");

function createAcademicRiskRouter() {
  const router = express.Router();
  let academicRiskIndexesReady = false;

  async function ensureIndexes(database) {
    if (!academicRiskIndexesReady) {
      await ensureAcademicRiskIndexes(database);
      academicRiskIndexesReady = true;
    }
  }

  function handleAnalysisContextError(response, result) {
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
        error: "A degree must be selected on the student profile before analyzing academic risks"
      });
    }

    if (result.status === "degree_not_found") {
      return response.status(400).json({
        success: false,
        data: null,
        error: "Referenced degree was not found in the catalog"
      });
    }

    if (result.status === "plan_not_found") {
      return response.status(404).json({
        success: false,
        data: null,
        error: "Semester plan not found"
      });
    }

    return null;
  }

  router.post("/analyze", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateAnalyzeAcademicRiskPayload(request.body);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      await ensureIndexes(database);

      const result = await analyzeAndStoreAcademicRisks(
        database,
        request.auth.userId,
        validationResult.data
      );

      const errorResponse = handleAnalysisContextError(response, result);
      if (errorResponse) {
        return errorResponse;
      }

      return response.status(201).json({
        success: true,
        data: {
          academicRiskAnalysis: toPublicAcademicRiskAnalysis(result.analysis)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.get("/", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateAcademicRiskListQuery(request.query);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const { page, limit } = validationResult.data;
      const listResult = await listAcademicRiskAnalysesForUser(database, request.auth.userId, {
        page: page ?? 1,
        limit: limit ?? 50
      });

      return response.status(200).json({
        success: true,
        data: {
          academicRiskAnalyses: listResult.analyses.map(toPublicAcademicRiskSummary),
          pagination: {
            total: listResult.total,
            page: listResult.page,
            limit: listResult.limit
          }
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.get("/:id", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateAcademicRiskIdParam(request.params);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const result = await getAcademicRiskAnalysisForUser(
        database,
        request.auth.userId,
        validationResult.data.id
      );

      if (result.status === "not_found") {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Academic risk analysis not found"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          academicRiskAnalysis: toPublicAcademicRiskAnalysis(result.analysis)
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
  createAcademicRiskRouter
};
