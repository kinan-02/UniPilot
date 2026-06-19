const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient } = require("../../src/db/mongoClient");
const {
  TECHNION_SEED,
  seedTechnionCatalogForTests
} = require("../helpers/catalogTestHelpers");

jest.setTimeout(30_000);

describe("catalog integration", () => {
  let mongoServer;
  let app;
  let accessToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_catalog_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await require("../../src/db/mongoClient").getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponse = await request(app).post("/auth/register").send({
      email: "catalog-reader@example.com",
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

  test("GET /courses returns seeded Technion courses", async () => {
    const response = await request(app)
      .get("/courses")
      .query({
        institutionId: TECHNION_SEED.institutionId,
        catalogYear: TECHNION_SEED.catalogYear
      })
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.courses.length).toBeGreaterThanOrEqual(10);
    expect(response.body.data.pagination.total).toBeGreaterThanOrEqual(10);
  });

  test("GET /courses/:courseId returns a seeded course", async () => {
    const response = await request(app)
      .get(`/courses/${TECHNION_SEED.courseIds.machineLearning}`)
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.course.number).toBe("02360363");
    expect(response.body.data.course.sourceRefs.length).toBeGreaterThan(0);
  });

  test("GET /degrees returns seeded Technion degree", async () => {
    const response = await request(app)
      .get("/degrees")
      .query({
        institutionId: TECHNION_SEED.institutionId,
        catalogYear: TECHNION_SEED.catalogYear
      })
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.degrees[0].code).toBe("CS-BSC");
  });

  test("GET /degrees/:degreeId/requirements returns requirement set", async () => {
    const response = await request(app)
      .get(`/degrees/${TECHNION_SEED.degreeId}/requirements`)
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.requirements.length).toBe(4);
    expect(response.body.data.catalogVersion).toBe("2025.1");
  });
});
