const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient } = require("../../src/db/mongoClient");

jest.setTimeout(30_000);

describe("student profile integration", () => {
  let mongoServer;
  let app;
  let accessToken;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_student_profile_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const registerResponse = await request(app).post("/auth/register").send({
      email: "profile-owner@example.com",
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

  test("POST /student-profile creates profile for authenticated user", async () => {
    const response = await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        institutionId: "uni-main",
        programType: "BSc",
        degreeId: "665f2b0f2a3f7b2a1a9a7f11",
        catalogYear: 2025,
        currentSemesterCode: "2025-1",
        preferences: {
          maxCreditsPerSemester: 18
        }
      });

    expect(response.status).toBe(201);
    expect(response.body.data.profile.institutionId).toBe("uni-main");
  });

  test("GET /student-profile returns profile of authenticated user", async () => {
    const response = await request(app)
      .get("/student-profile")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(response.status).toBe(200);
    expect(response.body.data.profile.programType).toBe("BSc");
  });

  test("PUT /student-profile updates profile of authenticated user", async () => {
    const response = await request(app)
      .put("/student-profile")
      .set("Authorization", `Bearer ${accessToken}`)
      .send({
        programType: "BSc-Honors",
        currentSemesterCode: "2025-2",
        preferences: {
          maxCreditsPerSemester: 21
        }
      });

    expect(response.status).toBe(200);
    expect(response.body.data.profile.programType).toBe("BSc-Honors");
    expect(response.body.data.profile.currentSemesterCode).toBe("2025-2");
  });

  test("DELETE /student-profile removes current user profile", async () => {
    const deleteResponse = await request(app)
      .delete("/student-profile")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(deleteResponse.status).toBe(200);

    const getResponse = await request(app)
      .get("/student-profile")
      .set("Authorization", `Bearer ${accessToken}`);

    expect(getResponse.status).toBe(404);
  });
});
