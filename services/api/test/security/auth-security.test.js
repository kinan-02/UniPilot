const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient } = require("../../src/db/mongoClient");

jest.setTimeout(30_000);

describe("auth security", () => {
  let mongoServer;
  let app;
  let accessToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_security_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "2";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const registerResponse = await request(app).post("/auth/register").send({
      email: "security-user@example.com",
      password: "StrongPass123!"
    });

    accessToken = registerResponse.body.data.accessToken;
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("GET /auth/me returns 401 when missing token", async () => {
    const response = await request(app).get("/auth/me");
    expect(response.status).toBe(401);
  });

  test("GET /auth/me returns 401 when token is invalid", async () => {
    const response = await request(app)
      .get("/auth/me")
      .set("Authorization", "Bearer invalid.jwt.token");

    expect(response.status).toBe(401);
  });

  test("GET /auth/me succeeds with valid token", async () => {
    const response = await request(app)
      .get("/auth/me")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.user.email).toBe("security-user@example.com");
  });

  test("auth routes enforce rate limiting with 429", async () => {
    await request(app).post("/auth/login").send({
      email: "security-user@example.com",
      password: "WrongPass123!"
    });

    await request(app).post("/auth/login").send({
      email: "security-user@example.com",
      password: "WrongPass123!"
    });

    const limitedResponse = await request(app).post("/auth/login").send({
      email: "security-user@example.com",
      password: "WrongPass123!"
    });

    expect(limitedResponse.status).toBe(429);
  });
});
