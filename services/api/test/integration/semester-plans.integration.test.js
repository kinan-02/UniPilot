const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient, getDatabase } = require("../../src/db/mongoClient");
const { createStudentProfile } = require("../../src/models/studentProfileModel");
const {
  TECHNION_SEED,
  seedTechnionCatalogForTests
} = require("../helpers/catalogTestHelpers");
const { buildCompletedCoursePayload } = require("../helpers/completedCourseTestHelpers");

jest.setTimeout(30_000);

describe("semester plans integration", () => {
  let mongoServer;
  let app;
  let accessToken;
  let noDegreeToken;
  let noProfileToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_semester_plans_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponse = await request(app).post("/auth/register").send({
      email: "semester-planner@example.com",
      password: "StrongPass123!"
    });
    accessToken = registerResponse.body.data.accessToken;

    await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        institutionId: TECHNION_SEED.institutionId,
        programType: "BSc",
        degreeId: TECHNION_SEED.degreeId,
        catalogYear: TECHNION_SEED.catalogYear,
        currentSemesterCode: "2025-1",
        preferences: { maxCreditsPerSemester: 12 }
      });

    const noDegreeRegister = await request(app).post("/auth/register").send({
      email: "semester-no-degree@example.com",
      password: "StrongPass123!"
    });
    noDegreeToken = noDegreeRegister.body.data.accessToken;
    await createStudentProfile(database, noDegreeRegister.body.data.user.id, {
      institutionId: TECHNION_SEED.institutionId,
      programType: "BSc",
      catalogYear: TECHNION_SEED.catalogYear,
      currentSemesterCode: "2025-1"
    });

    const noProfileRegister = await request(app).post("/auth/register").send({
      email: "semester-no-profile@example.com",
      password: "StrongPass123!"
    });
    noProfileToken = noProfileRegister.body.data.accessToken;
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("POST /semester-plans/generate creates and persists a deterministic plan", async () => {
    const response = await request(app)
      .post("/semester-plans/generate")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        semesterCode: "2025-2",
        maxCredits: 9
      });

    expect(response.status).toBe(201);
    expect(response.body.data.semesterPlan.plannerType).toBe("deterministic");
    expect(response.body.data.semesterPlan.explanation.rulesApplied.length).toBeGreaterThan(0);
    expect(response.body.data.semesterPlan.semesters[0].plannedCourses.length).toBeGreaterThan(0);
    expect(response.body.data.semesterPlan.semesters[0].plannedCourses[0].courseId).toBeTruthy();
  });

  test("GET /semester-plans returns planning history for the authenticated user", async () => {
    const response = await request(app)
      .get("/semester-plans")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.semesterPlans.length).toBeGreaterThanOrEqual(1);
    expect(response.body.data.pagination.total).toBeGreaterThanOrEqual(1);
  });

  test("GET /semester-plans/:id returns one owned plan", async () => {
    const listResponse = await request(app)
      .get("/semester-plans")
      .set("Authorization", `Bearer ${accessToken}`);

    const planId = listResponse.body.data.semesterPlans[0].id;

    const response = await request(app)
      .get(`/semester-plans/${planId}`)
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.semesterPlan.id).toBe(planId);
    expect(response.body.data.semesterPlan.explanation).toBeTruthy();
  });

  test("completed mandatory courses are not recommended again", async () => {
    await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(
        buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.foundations,
          semesterCode: "2024-1",
          grade: "A",
          creditsEarned: 3
        })
      );

    const response = await request(app)
      .post("/semester-plans/generate")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        semesterCode: "2025-2",
        maxCredits: 12
      });

    const recommendedIds = response.body.data.semesterPlan.semesters[0].plannedCourses.map(
      (course) => course.courseId
    );
    expect(recommendedIds).not.toContain(TECHNION_SEED.courseIds.foundations);
  });

  test("POST /semester-plans/generate returns 404 when profile does not exist", async () => {
    const response = await request(app)
      .post("/semester-plans/generate")
      .set("Authorization", `Bearer ${noProfileToken}`)
      .send({ semesterCode: "2025-2" });

    expect(response.status).toBe(404);
  });

  test("POST /semester-plans/generate returns 400 when profile has no degreeId", async () => {
    const response = await request(app)
      .post("/semester-plans/generate")
      .set("Authorization", `Bearer ${noDegreeToken}`)
      .send({ semesterCode: "2025-2" });

    expect(response.status).toBe(400);
    expect(response.body.error).toMatch(/degree must be selected/i);
  });
});
