const request = require("supertest");
const { MongoMemoryServer } = require("mongodb-memory-server");
const { createApp } = require("../../src/app");
const { closeMongoClient } = require("../../src/db/mongoClient");

jest.setTimeout(30_000);

describe("student profile security", () => {
  let mongoServer;
  let app;
  let accessTokenA;
  let accessTokenB;
  let profileIdA;
  let profileIdB;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();

    process.env.NODE_ENV = "test";
    process.env.MONGO_URI = mongoServer.getUri("unipilot_student_profile_security_test");
    process.env.JWT_SECRET = "test-jwt-secret";
    process.env.JWT_EXPIRES_IN = "1h";
    process.env.AUTH_RATE_LIMIT_MAX = "100";
    process.env.AUTH_RATE_LIMIT_WINDOW_MS = "60000";
    delete process.env.REDIS_URL;

    app = createApp();

    const registerResponseA = await request(app).post("/auth/register").send({
      email: "userA@example.com",
      password: "StrongPass123!"
    });
    accessTokenA = registerResponseA.body.data.accessToken;

    const registerResponseB = await request(app).post("/auth/register").send({
      email: "userB@example.com",
      password: "StrongPass123!"
    });
    accessTokenB = registerResponseB.body.data.accessToken;

    const createProfileResponseA = await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${accessTokenA}`)
      .send({
        institutionId: "uni-main-A",
        programType: "BSc-A",
        catalogYear: 2024,
        currentSemesterCode: "2024-1"
      });
    profileIdA = createProfileResponseA.body.data.profile.id;

    const createProfileResponseB = await request(app)
      .post("/student-profile")
      .set("Authorization", `Bearer ${accessTokenB}`)
      .send({
        institutionId: "uni-main-B",
        programType: "BSc-B",
        catalogYear: 2024,
        currentSemesterCode: "2024-1"
      });
    profileIdB = createProfileResponseB.body.data.profile.id;
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("GET /student-profile returns 401 when missing token", async () => {
    const response = await request(app).get("/student-profile");
    expect(response.status).toBe(401);
  });

  test("user A only reads own profile", async () => {
    const response = await request(app)
      .get("/student-profile")
      .set("Authorization", `Bearer ${accessTokenA}`);

    expect(response.status).toBe(200);
    expect(response.body.data.profile.id).toBe(profileIdA);
    expect(response.body.data.profile.id).not.toBe(profileIdB);
  });

  test("user A cannot update user B profile by id", async () => {
    const response = await request(app)
      .put("/student-profile")
      .set("Authorization", `Bearer ${accessTokenA}`)
      .send({
        _id: profileIdB,
        programType: "BSc-Honors"
      });

    expect(response.status).toBe(403);
  });

  test("deleting user A profile does not remove user B profile", async () => {
    const deleteResponse = await request(app)
      .delete("/student-profile")
      .set("Authorization", `Bearer ${accessTokenA}`);

    expect(deleteResponse.status).toBe(200);

    const userBProfileResponse = await request(app)
      .get("/student-profile")
      .set("Authorization", `Bearer ${accessTokenB}`);

    expect(userBProfileResponse.status).toBe(200);
    expect(userBProfileResponse.body.data.profile.id).toBe(profileIdB);
  });
});
