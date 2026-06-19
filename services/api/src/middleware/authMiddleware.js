const { verifyAccessToken } = require("../security/jwt");

function requireAuth(request, response, next) {
  const authorizationHeader = request.headers.authorization;
  const bearerToken = authorizationHeader && authorizationHeader.startsWith("Bearer ")
    ? authorizationHeader.slice(7)
    : null;

  if (!bearerToken) {
    return response.status(401).json({
      success: false,
      data: null,
      error: "Authentication token is required"
    });
  }

  try {
    const tokenPayload = verifyAccessToken(bearerToken);
    request.auth = {
      userId: tokenPayload.sub,
      email: tokenPayload.email
    };
    return next();
  } catch (_error) {
    return response.status(401).json({
      success: false,
      data: null,
      error: "Authentication token is invalid or expired"
    });
  }
}

module.exports = {
  requireAuth
};
