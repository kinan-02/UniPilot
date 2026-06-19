const express = require("express");
const { getDatabase } = require("../db/mongoClient");
const {
  createUser,
  ensureUserIndexes,
  findUserByEmail,
  findUserById,
  toPublicUser
} = require("../models/userModel");
const { createAuthRateLimiter } = require("../middleware/authRateLimiter");
const { requireAuth } = require("../middleware/authMiddleware");
const { hashPassword, verifyPassword } = require("../security/password");
const { createAccessToken } = require("../security/jwt");
const {
  validateLoginPayload,
  validateRegisterPayload
} = require("../validation/authSchemas");

function createAuthRouter() {
  const router = express.Router();
  const authRateLimiter = createAuthRateLimiter();
  let userIndexesReady = false;

  router.post("/register", authRateLimiter, async (request, response, next) => {
    try {
      const validationResult = validateRegisterPayload(request.body);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const { email, password } = validationResult.data;
      const database = await getDatabase();

      if (!userIndexesReady) {
        await ensureUserIndexes(database);
        userIndexesReady = true;
      }

      const existingUser = await findUserByEmail(database, email);
      if (existingUser) {
        return response.status(409).json({
          success: false,
          data: null,
          error: "A user with this email already exists"
        });
      }

      const passwordHash = await hashPassword(password);
      const user = await createUser(database, {
        email,
        passwordHash
      });

      const accessToken = createAccessToken({
        userId: user._id.toString(),
        email: user.email
      });

      return response.status(201).json({
        success: true,
        data: {
          accessToken,
          user: toPublicUser(user)
        },
        error: null
      });
    } catch (error) {
      if (error && error.code === 11000) {
        return response.status(409).json({
          success: false,
          data: null,
          error: "A user with this email already exists"
        });
      }
      return next(error);
    }
  });

  router.post("/login", authRateLimiter, async (request, response, next) => {
    try {
      const validationResult = validateLoginPayload(request.body);
      if (!validationResult.success) {
        return response.status(400).json({
          success: false,
          data: null,
          error: validationResult.error.issues[0].message
        });
      }

      const { email, password } = validationResult.data;
      const database = await getDatabase();
      const user = await findUserByEmail(database, email);

      if (!user) {
        return response.status(401).json({
          success: false,
          data: null,
          error: "Invalid email or password"
        });
      }

      const passwordMatches = await verifyPassword(password, user.passwordHash);
      if (!passwordMatches) {
        return response.status(401).json({
          success: false,
          data: null,
          error: "Invalid email or password"
        });
      }

      const accessToken = createAccessToken({
        userId: user._id.toString(),
        email: user.email
      });

      return response.status(200).json({
        success: true,
        data: {
          accessToken,
          user: toPublicUser(user)
        },
        error: null
      });
    } catch (error) {
      return next(error);
    }
  });

  router.get("/me", requireAuth, async (request, response, next) => {
    try {
      const database = await getDatabase();
      const user = await findUserById(database, request.auth.userId);

      if (!user) {
        return response.status(401).json({
          success: false,
          data: null,
          error: "Authentication token is invalid or expired"
        });
      }

      return response.status(200).json({
        success: true,
        data: {
          user: toPublicUser(user)
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
  createAuthRouter
};
