const express = require("express");
const { getDatabase } = require("../db/mongoClient");
const { requireAuth } = require("../middleware/authMiddleware");
const { findCourseById } = require("../models/courseModel");
const {
  createCompletedCourse,
  deleteCompletedCourseByIdAndUserId,
  ensureCompletedCourseIndexes,
  findCompletedCourseByIdAndUserId,
  findCompletedCoursesByUserId,
  toPublicCompletedCourse,
  updateCompletedCourseByIdAndUserId
} = require("../models/completedCourseModel");
const {
  validateCompletedCourseIdParam,
  validateCompletedCourseListQuery,
  validateCreateCompletedCoursePayload,
  validateUpdateCompletedCoursePayload
} = require("../validation/completedCourseSchemas");

function createCompletedCourseRouter() {
  const router = express.Router();
  let completedCourseIndexesReady = false;

  async function ensureIndexes(database) {
    if (!completedCourseIndexesReady) {
      await ensureCompletedCourseIndexes(database);
      completedCourseIndexesReady = true;
    }
  }

  async function resolveCourseSummary(database, courseId) {
    const course = await findCourseById(database, courseId);
    if (!course) {
      return null;
    }

    return {
      number: course.number,
      title: course.title
    };
  }

  router.post("/", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateCreateCompletedCoursePayload(request.body);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      await ensureIndexes(database);

      const course = await findCourseById(database, validationResult.data.courseId);
      if (!course) {
        return response.status(400).json({
          success: false,
          data: null,
          error: "Referenced course was not found in the catalog"
        });
      }

      const record = await createCompletedCourse(database, request.auth.userId, {
        ...validationResult.data,
        source: "manual"
      });

      const courseSummary = await resolveCourseSummary(database, record.courseId);

      return response.status(201).json({
        success: true,
        data: {
          completedCourse: toPublicCompletedCourse(record, courseSummary)
        },
        error: null
      });
    } catch (error) {
      if (error && error.code === 11000) {
        return response.status(409).json({
          success: false,
          data: null,
          error: "A completed course record already exists for this course and attempt"
        });
      }
      return next(error);
    }
  });

  router.get("/", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateCompletedCourseListQuery(request.query);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const { page, limit } = validationResult.data;
      const listResult = await findCompletedCoursesByUserId(database, request.auth.userId, {
        page: page ?? 1,
        limit: limit ?? 50
      });

      const completedCourses = await Promise.all(
        listResult.records.map(async (record) => {
          const courseSummary = await resolveCourseSummary(database, record.courseId);
          return toPublicCompletedCourse(record, courseSummary);
        })
      );

      return response.status(200).json({
        success: true,
        data: {
          completedCourses,
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
      const validationResult = validateCompletedCourseIdParam(request.params);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const record = await findCompletedCourseByIdAndUserId(
        database,
        validationResult.data.id,
        request.auth.userId
      );

      if (!record) {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Completed course record not found"
        });
      }

      const courseSummary = await resolveCourseSummary(database, record.courseId);

      return response.status(200).json({
        success: true,
        data: {
          completedCourse: toPublicCompletedCourse(record, courseSummary)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.put("/:id", requireAuth, async (request, response, next) => {
    try {
      const paramValidation = validateCompletedCourseIdParam(request.params);
      if (!paramValidation.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: paramValidation.error.issues[0].message
        });
      }

      const bodyValidation = validateUpdateCompletedCoursePayload(request.body);
      if (!bodyValidation.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: bodyValidation.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const updateResult = await updateCompletedCourseByIdAndUserId(
        database,
        paramValidation.data.id,
        request.auth.userId,
        bodyValidation.data
      );

      if (updateResult.status === "not_found") {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Completed course record not found"
        });
      }

      if (updateResult.status === "not_editable") {
        return response.status(403).json({
          success: false,
          data: null,
          error: "Only manual completed course records can be updated"
        });
      }

      const courseSummary = await resolveCourseSummary(
        database,
        updateResult.record.courseId
      );

      return response.status(200).json({
        success: true,
        data: {
          completedCourse: toPublicCompletedCourse(updateResult.record, courseSummary)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.delete("/:id", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateCompletedCourseIdParam(request.params);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const deleteResult = await deleteCompletedCourseByIdAndUserId(
        database,
        validationResult.data.id,
        request.auth.userId
      );

      if (deleteResult.status === "not_found") {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Completed course record not found"
        });
      }

      if (deleteResult.status === "not_editable") {
        return response.status(403).json({
          success: false,
          data: null,
          error: "Only manual completed course records can be deleted"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          deleted: true
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
  createCompletedCourseRouter
};
