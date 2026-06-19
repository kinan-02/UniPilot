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

describe("academic risks integration", () => {
  let mongoServer;
  let app;
  let accessToken;
  let planId;
  let noDegreeToken;
  let noProfileToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_academic_risks_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const database = await getDatabase();
    await seedTechnionCatalogForTests(database);

    const registerResponse = await request(app).post("/auth/register").send({
      email: "academic-risk@example.com",
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

    const generateResponse = await request(app)
      .post("/semester-plans/generate")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        semesterCode: "2025-2",
        maxCredits: 12
      });
    planId = generateResponse.body.data.semesterPlan.id;

    const noDegreeRegister = await request(app).post("/auth/register").send({
      email: "risk-no-degree@example.com",
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
      email: "risk-no-profile@example.com",
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

  test("POST /academic-risks/analyze analyzes a persisted semester plan", async () => {
    const response = await request(app)
      .post("/academic-risks/analyze")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({ planId });

    expect(response.status).toBe(201);
    expect(response.body.data.academicRiskAnalysis.analyzerType).toBe("deterministic");
    expect(response.body.data.academicRiskAnalysis.planId).toBe(planId);
    expect(response.body.data.academicRiskAnalysis.summary).toHaveProperty("totalRisks");
    expect(response.body.data.academicRiskAnalysis.risks.every((risk) => risk.source === "rule")).toBe(true);
  });

  test("POST /academic-risks/analyze supports ad-hoc proposed course analysis", async () => {
    const response = await request(app)
      .post("/academic-risks/analyze")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        semesterCode: "2025-2",
        courseIds: [TECHNION_SEED.courseIds.foundations, TECHNION_SEED.courseIds.machineLearning],
        maxCredits: 6
      });

    expect(response.status).toBe(201);
    expect(response.body.data.academicRiskAnalysis.analysisSource).toBe("adhoc_courses");
    expect(
      response.body.data.academicRiskAnalysis.risks.some((risk) => risk.riskType === "unmet_prerequisites")
    ).toBe(true);
  });

  test("GET /academic-risks returns analysis history", async () => {
    const response = await request(app)
      .get("/academic-risks")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.academicRiskAnalyses.length).toBeGreaterThanOrEqual(2);
    expect(response.body.data.pagination.total).toBeGreaterThanOrEqual(2);
  });

  test("GET /academic-risks/:id returns one owned analysis", async () => {
    const listResponse = await request(app)
      .get("/academic-risks")
      .set("Authorization", `Bearer ${accessToken}`);

    const analysisId = listResponse.body.data.academicRiskAnalyses[0].id;

    const response = await request(app)
      .get(`/academic-risks/${analysisId}`)
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.academicRiskAnalysis.id).toBe(analysisId);
    expect(response.body.data.academicRiskAnalysis.risks).toBeTruthy();
  });

  test("detects completed course in ad-hoc plan", async () => {
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
      .post("/academic-risks/analyze")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        semesterCode: "2025-2",
        courseIds: [TECHNION_SEED.courseIds.foundations]
      });

    expect(
      response.body.data.academicRiskAnalysis.risks.some(
        (risk) => risk.riskType === "course_already_completed"
      )
    ).toBe(true);
  });

  test("POST /academic-risks/analyze returns 404 when profile does not exist", async () => {
    const response = await request(app)
      .post("/academic-risks/analyze")
      .set("Authorization", `Bearer ${noProfileToken}`)
      .send({ planId });

    expect(response.status).toBe(404);
  });

  test("POST /academic-risks/analyze returns 400 when profile has no degreeId", async () => {
    const response = await request(app)
      .post("/academic-risks/analyze")
      .set("Authorization", `Bearer ${noDegreeToken}`)
      .send({ planId });

    expect(response.status).toBe(400);
    expect(response.body.error).toMatch(/degree must be selected/i);
  });

  test("POST /academic-risks/analyze returns 404 for invalid planId", async () => {
    const response = await request(app)
      .post("/academic-risks/analyze")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({ planId: "665f2b0f2a3f7b2a1a9a7fff" });

    expect(response.status).toBe(404);
  });
});
