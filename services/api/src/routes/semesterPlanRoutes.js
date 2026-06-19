const express = require("express");
const { getDatabase } = require("../db/mongoClient");
const { requireAuth } = require("../middleware/authMiddleware");
const { ensureSemesterPlanIndexes, toPublicSemesterPlan, toPublicSemesterPlanSummary } = require("../models/semesterPlanModel");
const {
  generateAndStoreSemesterPlan,
  getSemesterPlanForUser,
  listSemesterPlansForUser
} = require("../services/semesterPlanService");
const {
  validateGenerateSemesterPlanPayload,
  validateSemesterPlanIdParam,
  validateSemesterPlanListQuery
} = require("../validation/semesterPlanSchemas");

function createSemesterPlanRouter() {
  const router = express.Router();
  let semesterPlanIndexesReady = false;

  async function ensureIndexes(database) {
    if (!semesterPlanIndexesReady) {
      await ensureSemesterPlanIndexes(database);
      semesterPlanIndexesReady = true;
    }
  }

  function handlePlanningContextError(response, result) {
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
        error: "A degree must be selected on the student profile before generating a semester plan"
      });
    }

    if (result.status === "degree_not_found") {
      return response.status(400).json({
        success: false,
        data: null,
        error: "Referenced degree was not found in the catalog"
      });
    }

    return null;
  }

  router.post("/generate", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateGenerateSemesterPlanPayload(request.body);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      await ensureIndexes(database);

      const result = await generateAndStoreSemesterPlan(
        database,
        request.auth.userId,
        validationResult.data
      );

      const errorResponse = handlePlanningContextError(response, result);
      if (errorResponse) {
        return errorResponse;
      }

      return response.status(201).json({
        success: true,
        data: {
          semesterPlan: toPublicSemesterPlan(result.plan)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.get("/", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateSemesterPlanListQuery(request.query);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const { page, limit } = validationResult.data;
      const listResult = await listSemesterPlansForUser(database, request.auth.userId, {
        page: page ?? 1,
        limit: limit ?? 50
      });

      return response.status(200).json({
        success: true,
        data: {
          semesterPlans: listResult.plans.map(toPublicSemesterPlanSummary),
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
      const validationResult = validateSemesterPlanIdParam(request.params);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const result = await getSemesterPlanForUser(
        database,
        request.auth.userId,
        validationResult.data.id
      );

      if (result.status === "not_found") {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Semester plan not found"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          semesterPlan: toPublicSemesterPlan(result.plan)
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
  createSemesterPlanRouter
};
