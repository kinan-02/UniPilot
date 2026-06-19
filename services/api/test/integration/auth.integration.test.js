const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient } = require("../../src/db/mongoClient");

jest.setTimeout(30_000);

describe("auth integration", () => {
  let mongoServer;
  let app;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("POST /auth/register creates a user and returns a token", async () => {
    const response = await request(app).post("/auth/register").send({
      email: "new-user@example.com",
      password: "StrongPass123!"
    });

    expect(response.status).toBe(201);
    expect(response.body.data.user.email).toBe("new-user@example.com");
    expect(response.body.data).toHaveProperty("accessToken");
    expect(response.body.data.user).not.toHaveProperty("passwordHash");
  });

  test("POST /auth/register rejects duplicate email", async () => {
    await request(app).post("/auth/register").send({
      email: "duplicate@example.com",
      password: "StrongPass123!"
    });

    const response = await request(app).post("/auth/register").send({
      email: "duplicate@example.com",
      password: "StrongPass123!"
    });

    expect(response.status).toBe(409);
  });

  test("POST /auth/login returns token for valid credentials", async () => {
    await request(app).post("/auth/register").send({
      email: "login-user@example.com",
      password: "StrongPass123!"
    });

    const response = await request(app).post("/auth/login").send({
      email: "login-user@example.com",
      password: "StrongPass123!"
    });

    expect(response.status).toBe(200);
    expect(response.body.data).toHaveProperty("accessToken");
    expect(response.body.data.user.email).toBe("login-user@example.com");
  });

  test("POST /auth/login rejects incorrect password", async () => {
    await request(app).post("/auth/register").send({
      email: "wrong-password@example.com",
      password: "StrongPass123!"
    });

    const response = await request(app).post("/auth/login").send({
      email: "wrong-password@example.com",
      password: "WrongPass123!"
    });

    expect(response.status).toBe(401);
  });

  test("GET /auth/me returns current user for valid token", async () => {
    const registerResponse = await request(app).post("/auth/register").send({
      email: "me-route@example.com",
      password: "StrongPass123!"
    });

    const accessToken = registerResponse.body.data.accessToken;

    const response = await request(app)
      .get("/auth/me")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.user.email).toBe("me-route@example.com");
  });
});
