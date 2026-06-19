const jwt = require("jsonwebtoken");

function getJwtSettings() {
  const jwtSecret = process.env.JWT_SECRET;

  if (!jwtSecret) {
    throw new Error("JWT_SECRET is required");
  }

  return {
    jwtSecret,
    expiresIn: process.env.JWT_EXPIRES_IN || "1h"
  };
}

function createAccessToken({ userId, email }) {
  const { jwtSecret, expiresIn } = getJwtSettings();

  return jwt.sign(
    {
      email
    },
    jwtSecret,
    {
      algorithm: "HS256",
      expiresIn,
      subject: String(userId)
    }
  );
}

function verifyAccessToken(token) {
  const { jwtSecret } = getJwtSettings();
  return jwt.verify(String(token), jwtSecret, {
    algorithms: ["HS256"]
  });
}

module.exports = {
  createAccessToken,
  verifyAccessToken
};
