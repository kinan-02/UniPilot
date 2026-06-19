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

describe("graduation progress integration", () => {
  let mongoServer;
  let app;
  let accessToken;
  let noDegreeToken;
  let noProfileToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_graduation_progress_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponse = await request(app).post("/auth/register").send({
      email: "graduation-progress@example.com",
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
        currentSemesterCode: "2025-1"
      });

    const noDegreeRegister = await request(app).post("/auth/register").send({
      email: "graduation-no-degree@example.com",
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
      email: "graduation-no-profile@example.com",
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

  test("GET /graduation-progress returns not_started when there are no completed courses", async () => {
    const response = await request(app)
      .get("/graduation-progress")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.graduationProgress.completedCredits).toBe(0);
    expect(response.body.data.graduationProgress.totalRequiredCredits).toBe(155);
    expect(response.body.data.graduationProgress.statusSummary).toBe("not_started");
    expect(response.body.data.graduationProgress.remainingMandatoryCourses.length).toBeGreaterThan(0);
    expect(response.body.data.graduationProgress.missingRequirements.length).toBeGreaterThan(0);
  });

  test("GET /graduation-progress reflects completed mandatory and fractional elective credits", async () => {
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

    await request(app)
      .post("/completed-courses")
      .set("Authorization", `Bearer ${accessToken}`)
      .send(
        buildCompletedCoursePayload({
          courseId: TECHNION_SEED.courseIds.machineLearning,
          semesterCode: "2024-2",
          grade: "B+",
          creditsEarned: 3.5,
          attempt: 1
        })
      );

    const response = await request(app)
      .get("/graduation-progress")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);

    const progress = response.body.data.graduationProgress;
    expect(progress.completedCredits).toBe(6.5);
    expect(progress.completedMandatoryCourses.some((course) => course.courseId === TECHNION_SEED.courseIds.foundations)).toBe(true);
    expect(progress.remainingMandatoryCourses.some((course) => course.courseId === TECHNION_SEED.courseIds.foundations)).toBe(false);
    expect(progress.completedElectiveCredits).toBe(3.5);
    expect(progress.remainingElectiveCredits).toBe(2.5);
    expect(progress.statusSummary).toBe("in_progress");
    expect(progress.requirementProgress.length).toBe(4);
  });

  test("GET /graduation-progress returns 404 when profile does not exist", async () => {
    const response = await request(app)
      .get("/graduation-progress")
      .set("Authorization", `Bearer ${noProfileToken}`);

    expect(response.status).toBe(404);
    expect(response.body.error).toMatch(/student profile not found/i);
  });

  test("GET /graduation-progress returns 400 when profile has no degreeId", async () => {
    const response = await request(app)
      .get("/graduation-progress")
      .set("Authorization", `Bearer ${noDegreeToken}`);

    expect(response.status).toBe(400);
    expect(response.body.error).toMatch(/degree must be selected/i);
  });

  test("GET /graduation-progress returns 400 when profile degreeId is not in catalog", async () => {
    const database = await getDatabase();
    const invalidDegreeRegister = await request(app).post("/auth/register").send({
      email: "graduation-invalid-degree@example.com",
      password: "StrongPass123!"
    });

    await createStudentProfile(database, invalidDegreeRegister.body.data.user.id, {
      institutionId: TECHNION_SEED.institutionId,
      programType: "BSc",
      degreeId: "665f2b0f2a3f7b2a1a9a7fff",
      catalogYear: TECHNION_SEED.catalogYear,
      currentSemesterCode: "2025-1"
    });

    const response = await request(app)
      .get("/graduation-progress")
      .set("Authorization", `Bearer ${invalidDegreeRegister.body.data.accessToken}`);

    expect(response.status).toBe(400);
    expect(response.body.error).toMatch(/degree was not found in the catalog/i);
  });
});
