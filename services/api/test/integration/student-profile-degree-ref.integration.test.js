const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient } = require("../../src/db/mongoClient");
const {
  TECHNION_SEED,
  seedTechnionCatalogForTests
} = require("../helpers/catalogTestHelpers");

jest.setTimeout(30_000);

describe("student profile degree reference integration", () => {
  let mongoServer;
  let app;
  let accessToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_profile_degree_ref_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await require("../../src/db/mongoClient").getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponse = await request(app).post("/auth/register").send({
      email: "degree-ref@example.com",
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

  test("POST /student-profile accepts a seeded degreeId", async () => {
    const response = await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        institutionId: "technion",
        programType: "BSc",
        degreeId: TECHNION_SEED.degreeId,
        catalogYear: 2025,
        currentSemesterCode: "2025-1"
      });

    expect(response.status).toBe(201);
    expect(response.body.data.profile.degreeId).toBe(TECHNION_SEED.degreeId);
  });

  test("POST /student-profile rejects unknown degreeId", async () => {
    const registerResponse = await request(app).post("/auth/register").send({
      email: "bad-degree@example.com",
      password: "StrongPass123!"
    });

    const response = await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${registerResponse.body.data.accessToken}`)
      .send({
        institutionId: "technion",
        programType: "BSc",
        degreeId: "665f2b0f2a3f7b2a1a9a7f11",
        catalogYear: 2025,
        currentSemesterCode: "2025-1"
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toMatch(/degree/i);
  });
});
