const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient, getDatabase } = require("../../src/db/mongoClient");
const {
  TECHNION_SEED,
  seedTechnionCatalogForTests
} = require("../helpers/catalogTestHelpers");
const { buildCompletedCoursePayload } = require("../helpers/completedCourseTestHelpers");

jest.setTimeout(30_000);

describe("completed courses integration", () => {
  let mongoServer;
  let app;
  let accessToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_completed_courses_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponse = await request(app).post("/auth/register").send({
      email: "completed-courses@example.com",
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

  test("POST /completed-courses creates manual transcript record", async () => {
    const response = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(
        buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.foundations,
          semesterCode: "2023-1",
          grade: "A",
          creditsEarned: 4
        })
      );

    expect(response.status).toBe(201);
    expect(response.body.data.completedCourse.courseId).toBe(TECHNION_SEED.courseIds.foundations);
    expect(response.body.data.completedCourse.source).toBe("manual");
    expect(response.body.data.completedCourse.courseTitle).toBeTruthy();
  });

  test("POST /completed-courses rejects unknown courseId", async () => {
    const response = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(
        buildCompletedCoursePayload({
          courseId: "665f2b0f2a3f7b2a1a9a7fff",
          semesterCode: "2023-2"
        })
      );

    expect(response.status).toBe(400);
    expect(response.body.error).toMatch(/not found in the catalog/i);
  });

  test("POST /completed-courses returns 409 for duplicate attempt", async () => {
    const payload = buildCompletedCoursePayload({
      courseId: TECHNION_SEED.courseIds.machineLearning,
      semesterCode: "2024-1",
      attempt: 1
    });

    const firstResponse = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(payload);

    expect(firstResponse.status).toBe(201);

    const duplicateResponse = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(payload);

    expect(duplicateResponse.status).toBe(409);
  });

  test("GET /completed-courses lists authenticated user records", async () => {
    const response = await request(app)
      .get("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.completedCourses.length).toBeGreaterThanOrEqual(2);
    expect(response.body.data.pagination.total).toBeGreaterThanOrEqual(2);
  });

  test("GET /completed-courses/:id returns one owned record", async () => {
    const listResponse = await request(app)
      .get("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`);

    const recordId = listResponse.body.data.completedCourses[0].id;

    const response = await request(app)
      .get(`/completed-courses/${recordId}`)
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.completedCourse.id).toBe(recordId);
  });

  test("PUT /completed-courses/:id updates manual record", async () => {
    const createResponse = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(
        buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.foundations,
          semesterCode: "2022-2",
          attempt: 2,
          grade: "B"
        })
      );

    const recordId = createResponse.body.data.completedCourse.id;

    const updateResponse = await request(app)
      .put(`/completed-courses/${recordId}`)
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        grade: "A-",
        creditsEarned: 4
      });

    expect(updateResponse.status).toBe(200);
    expect(updateResponse.body.data.completedCourse.grade).toBe("A-");
    expect(updateResponse.body.data.completedCourse.creditsEarned).toBe(4);
  });

  test("DELETE /completed-courses/:id deletes manual record", async () => {
    const createResponse = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(
        buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.machineLearning,
          semesterCode: "2022-1",
          attempt: 2
        })
      );

    const recordId = createResponse.body.data.completedCourse.id;

    const deleteResponse = await request(app)
      .delete(`/completed-courses/${recordId}`)
      .set("Authorization", `Bearer ${accessToken}`);

    expect(deleteResponse.status).toBe(200);
    expect(deleteResponse.body.data.deleted).toBe(true);

    const getResponse = await request(app)
      .get(`/completed-courses/${recordId}`)
      .set("Authorization", `Bearer ${accessToken}`);

    expect(getResponse.status).toBe(404);
  });
});
