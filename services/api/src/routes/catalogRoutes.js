const express = require("express");
const { getDatabase } = require("../db/mongoClient");
const { requireAuth } = require("../middleware/authMiddleware");
const { findCourseById, findCourses, toPublicCourse } = require("../models/courseModel");
const {
  findDegreeById,
  findDegrees,
  toPublicDegree
} = require("../models/degreeModel");
const {
  findDegreeRequirementsByDegreeId,
  toPublicDegreeRequirement
} = require("../models/degreeRequirementModel");
const {
  validateCatalogListQuery,
  validateCourseIdParam,
  validateCourseListQuery,
  validateDegreeIdParam
} = require("../validation/catalogQuerySchemas");

function createCatalogRouter() {
  const router = express.Router();

  router.get("/courses", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateCourseListQuery(request.query);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const { institutionId, catalogYear, page, limit } = validationResult.data;
      const database = await getDatabase();
      const listResult = await findCourses(database, {
        institutionId,
        catalogYear,
        page: page ?? 1,
        limit: limit ?? 50
      });

      return response.status(200).json({
        success: true,
        data: {
          courses: listResult.courses.map(toPublicCourse),
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

  router.get("/courses/:courseId", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateCourseIdParam(request.params);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const course = await findCourseById(database, validationResult.data.courseId);

      if (!course) {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Course not found"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          course: toPublicCourse(course)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.get("/degrees", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateCatalogListQuery(request.query);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const { institutionId, catalogYear } = validationResult.data;
      const database = await getDatabase();
      const degrees = await findDegrees(database, { institutionId, catalogYear });

      return response.status(200).json({
        success: true,
        data: {
          degrees: degrees.map(toPublicDegree)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.get("/degrees/:degreeId", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateDegreeIdParam(request.params);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const degree = await findDegreeById(database, validationResult.data.degreeId);

      if (!degree) {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Degree not found"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          degree: toPublicDegree(degree)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.get("/degrees/:degreeId/requirements", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateDegreeIdParam(request.params);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const degree = await findDegreeById(database, validationResult.data.degreeId);

      if (!degree) {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Degree not found"
        });
      }

      const requirements = await findDegreeRequirementsByDegreeId(
        database,
        validationResult.data.degreeId,
        { version: degree.version }
      );

      return response.status(200).json({
        success: true,
        data: {
          degreeId: degree._id.toString(),
          catalogYear: degree.catalogYear,
          catalogVersion: degree.catalogVersion,
          requirements: requirements.map(toPublicDegreeRequirement)
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
  createCatalogRouter
};
