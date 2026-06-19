const express = require("express");
const { getDatabase } = require("../db/mongoClient");
const { requireAuth } = require("../middleware/authMiddleware");
const {
  createStudentProfile,
  deleteStudentProfileByUserId,
  ensureStudentProfileIndexes,
  findStudentProfileByUserId,
  toPublicStudentProfile,
  updateStudentProfileByUserId
} = require("../models/studentProfileModel");
const {
  validateCreateStudentProfilePayload,
  validateUpdateStudentProfilePayload
} = require("../validation/studentProfileSchemas");

function createStudentProfileRouter() {
  const router = express.Router();
  let studentProfileIndexesReady = false;

  async function ensureIndexes(database) {
    if (!studentProfileIndexesReady) {
      await ensureStudentProfileIndexes(database);
      studentProfileIndexesReady = true;
    }
  }

  router.post("/", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateCreateStudentProfilePayload(request.body);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      await ensureIndexes(database);

      const existingProfile = await findStudentProfileByUserId(database, request.auth.userId);
      if (existingProfile) {
        return response.status(409).json({
          success: false,
          data: null,
          error: "Student profile already exists for this user"
        });
      }

      const profile = await createStudentProfile(
        database,
        request.auth.userId,
        validationResult.data
      );

      return response.status(201).json({
        success: true,
        data: {
          profile: toPublicStudentProfile(profile)
        },
        error: null
      });
    } catch (error) {
      if (error && error.code === 11000) {
        return response.status(409).json({
          success: false,
          data: null,
          error: "Student profile already exists for this user"
        });
      }
      return next(error);
    }
  });

  router.get("/", requireAuth, async (request, response, next) => {
    try {
      const database = await getDatabase();
      const profile = await findStudentProfileByUserId(database, request.auth.userId);

      if (!profile) {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Student profile not found"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          profile: toPublicStudentProfile(profile)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.put("/", requireAuth, async (request, response, next) => {
    try {
      const validationResult = validateUpdateStudentProfilePayload(request.body);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const database = await getDatabase();
      const existingProfile = await findStudentProfileByUserId(database, request.auth.userId);

      if (!existingProfile) {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Student profile not found"
        });
      }

      const { _id: requestedProfileId, ...updates } = validationResult.data;
      if (requestedProfileId && requestedProfileId !== existingProfile._id.toString()) {
        return response.status(403).json({
          success: false,
          data: null,
          error: "You are not allowed to modify this student profile"
        });
      }

      const updatedProfile = await updateStudentProfileByUserId(
        database,
        request.auth.userId,
        updates
      );

      return response.status(200).json({
        success: true,
        data: {
          profile: toPublicStudentProfile(updatedProfile)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.delete("/", requireAuth, async (request, response, next) => {
    try {
      const database = await getDatabase();
      const deleteResult = await deleteStudentProfileByUserId(database, request.auth.userId);

      if (!deleteResult.deletedCount) {
        return response.status(404).json({
          success: false,
          data: null,
          error: "Student profile not found"
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
  createStudentProfileRouter
};
