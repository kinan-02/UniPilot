const { createAccessToken, verifyAccessToken } = require("../../src/security/jwt");

describe("jwt service", () => {
  const originalEnvironment = { ...process.env };

  beforeEach(() => {
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
  });

  afterEach(() => {
    process.env = { ...originalEnvironment };
  });

  test("createAccessToken signs a token containing user claims", () => {
    const token = createAccessToken({ userId: "507f1f77bcf86cd799439011", email: "user@example.com" });
    const payload = verifyAccessToken(token);

    expect(payload.sub).toBe("507f1f77bcf86cd799439011");
    expect(payload.email).toBe("user@example.com");
  });

  test("verifyAccessToken throws for malformed token", () => {
    expect(() => verifyAccessToken("malformed-token")).toThrow();
  });

  test("verifyAccessToken throws for expired token", async () => {
    process.env.JWT_EXPIRES_IN = "1ms";

    const token = createAccessToken({
      userId: "507f1f77bcf86cd799439011",
      email: "user@example.com"
    });

    await new Promise((resolve) => {
      setTimeout(resolve, 5);
    });

    expect(() => verifyAccessToken(token)).toThrow();
  });
});
