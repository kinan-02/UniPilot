const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient, getDatabase } = require("../../src/db/mongoClient");
const {
  TECHNION_SEED,
  seedTechnionCatalogForTests
} = require("../helpers/catalogTestHelpers");

jest.setTimeout(30_000);

describe("semester plans security", () => {
  let mongoServer;
  let app;
  let accessTokenA;
  let accessTokenB;
  let planIdA;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_semester_plans_security_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponseA = await request(app).post("/auth/register").send({
      email: "semesterA@example.com",
      password: "StrongPass123!"
    });
    accessTokenA = registerResponseA.body.data.accessToken;

    await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${accessTokenA}`)
      .send({
        institutionId: TECHNION_SEED.institutionId,
        programType: "BSc",
        degreeId: TECHNION_SEED.degreeId,
        catalogYear: TECHNION_SEED.catalogYear,
        currentSemesterCode: "2025-1"
      });

    const generateResponseA = await request(app)
      .post("/semester-plans/generate")
      .set("Authorization", `Bearer ${accessTokenA}`)
      .send({ semesterCode: "2025-2" });
    planIdA = generateResponseA.body.data.semesterPlan.id;

    const registerResponseB = await request(app).post("/auth/register").send({
      email: "semesterB@example.com",
      password: "StrongPass123!"
    });
    accessTokenB = registerResponseB.body.data.accessToken;

    await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${accessTokenB}`)
      .send({
        institutionId: TECHNION_SEED.institutionId,
        programType: "BSc",
        degreeId: TECHNION_SEED.degreeId,
        catalogYear: TECHNION_SEED.catalogYear,
        currentSemesterCode: "2025-1"
      });
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("POST /semester-plans/generate returns 401 without token", async () => {
    const response = await request(app)
      .post("/semester-plans/generate")
      .send({ semesterCode: "2025-2" });

    expect(response.status).toBe(401);
  });

  test("GET /semester-plans returns 401 without token", async () => {
    const response = await request(app).get("/semester-plans");
    expect(response.status).toBe(401);
  });

  test("user B cannot read user A semester plan by id", async () => {
    const response = await request(app)
      .get(`/semester-plans/${planIdA}`)
      .set("Authorization", `Bearer ${accessTokenB}`);

    expect(response.status).toBe(404);
  });

  test("POST rejects userId in request body", async () => {
    const response = await request(app)
      .post("/semester-plans/generate")
      .set("Authorization", `Bearer ${accessTokenB}`)
      .send({
        semesterCode: "2025-2",
        userId: "665f2b0f2a3f7b2a1a9a7fff"
      });

    expect(response.status).toBe(400);
  });
});
