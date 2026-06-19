const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient, getDatabase } = require("../../src/db/mongoClient");
const {
  TECHNION_SEED,
  seedTechnionCatalogForTests
} = require("../helpers/catalogTestHelpers");
const {
  buildCompletedCoursePayload,
  insertOfficialCompletedCourseForTests
} = require("../helpers/completedCourseTestHelpers");

jest.setTimeout(30_000);

describe("completed courses security", () => {
  let mongoServer;
  let app;
  let accessTokenA;
  let accessTokenB;
  let userIdA;
  let recordIdA;
  let officialRecordIdA;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_completed_courses_security_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponseA = await request(app).post("/auth/register").send({
      email: "completedA@example.com",
      password: "StrongPass123!"
    });
    accessTokenA = registerResponseA.body.data.accessToken;
    userIdA = registerResponseA.body.data.user.id;

    const registerResponseB = await request(app).post("/auth/register").send({
      email: "completedB@example.com",
      password: "StrongPass123!"
    });
    accessTokenB = registerResponseB.body.data.accessToken;

    const createResponseA = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessTokenA}`)
      .send(
        buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.foundations,
          semesterCode: "2023-1"
        })
      );
    recordIdA = createResponseA.body.data.completedCourse.id;

    const officialRecord = await insertOfficialCompletedCourseForTests(database, userIdA, {
      courseId: TECHNION_SEED.courseIds.machineLearning,
      semesterCode: "2023-2",
      grade: "A",
      creditsEarned: 3,
      attempt: 1
    });
    officialRecordIdA = officialRecord._id.toString();
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("GET /completed-courses returns 401 without token", async () => {
    const response = await request(app).get("/completed-courses");
    expect(response.status).toBe(401);
  });

  test("POST /completed-courses returns 401 without token", async () => {
    const response = await request(app)
      .post("/completed-courses")
      .send(buildCompletedCoursePayload());

    expect(response.status).toBe(401);
  });

  test("user B cannot read user A completed course by id", async () => {
    const response = await request(app)
      .get(`/completed-courses/${recordIdA}`)
      .set("Authorization", `Bearer ${accessTokenB}`);

    expect(response.status).toBe(404);
  });

  test("user B cannot update user A completed course", async () => {
    const response = await request(app)
      .put(`/completed-courses/${recordIdA}`)
      .set("Authorization", `Bearer ${accessTokenB}`)
      .send({ grade: "F" });

    expect(response.status).toBe(404);
  });

  test("user B cannot delete user A completed course", async () => {
    const response = await request(app)
      .delete(`/completed-courses/${recordIdA}`)
      .set("Authorization", `Bearer ${accessTokenB}`);

    expect(response.status).toBe(404);
  });

  test("user A list does not include user B records", async () => {
    const createResponseB = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessTokenB}`)
      .send(
        buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.foundations,
          semesterCode: "2024-2"
        })
      );

    const recordIdB = createResponseB.body.data.completedCourse.id;

    const response = await request(app)
      .get("/completed-courses")
      .set("Authorization", `Bearer ${accessTokenA}`);

    expect(response.status).toBe(200);
    const ids = response.body.data.completedCourses.map((record) => record.id);
    expect(ids).toContain(recordIdA);
    expect(ids).not.toContain(recordIdB);
  });

  test("POST rejects userId in request body", async () => {
    const response = await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessTokenB}`)
      .send({
        ...buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.machineLearning,
          semesterCode: "2024-1",
          attempt: 2
        }),
        userId: userIdA
      });

    expect(response.status).toBe(400);
  });

  test("PUT official record returns 403 for user A", async () => {
    const response = await request(app)
      .put(`/completed-courses/${officialRecordIdA}`)
      .set("Authorization", `Bearer ${accessTokenA}`)
      .send({ grade: "B" });

    expect(response.status).toBe(403);
  });

  test("DELETE official record returns 403 for user A", async () => {
    const response = await request(app)
      .delete(`/completed-courses/${officialRecordIdA}`)
      .set("Authorization", `Bearer ${accessTokenA}`);

    expect(response.status).toBe(403);
  });
});
