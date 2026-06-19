const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient } = require("../../src/db/mongoClient");
const { seedTechnionCatalogForTests } = require("../helpers/catalogTestHelpers");

jest.setTimeout(30_000);

describe("catalog security", () => {
  let mongoServer;
  let app;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_catalog_security_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await require("../../src/db/mongoClient").getDatabase();
    await seedTechnionCatalogForTests(database);
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("GET /courses returns 401 without token", async () => {
    const response = await request(app).get("/courses").query({
      institutionId: "technion",
      catalogYear: 2025
    });

    expect(response.status).toBe(401);
  });

  test("GET /courses/:courseId returns 401 without token", async () => {
    const response = await request(app).get("/courses/665f2b0f2a3f7b2a1a9a7c07");

    expect(response.status).toBe(401);
  });

  test("GET /degrees returns 401 without token", async () => {
    const response = await request(app).get("/degrees").query({
      institutionId: "technion",
      catalogYear: 2025
    });

    expect(response.status).toBe(401);
  });

  test("GET /degrees/:degreeId returns 401 without token", async () => {
    const response = await request(app).get("/degrees/665f2b0f2a3f7b2a1a9a7d01");

    expect(response.status).toBe(401);
  });

  test("GET /degrees/:degreeId/requirements returns 401 without token", async () => {
    const response = await request(app).get("/degrees/665f2b0f2a3f7b2a1a9a7d01/requirements");

    expect(response.status).toBe(401);
  });
});
