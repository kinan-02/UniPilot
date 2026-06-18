const request = require("supertest");
const { createApp } = require("../src/app");

describe("GET /health", () => {
  test("returns service health payload", async () => {
    const app = createApp();
    const response = await request(app).get("/health");

    expect(response.status).toBe(200);
    expect(response.body).toEqual(
      expect.objectContaining({
        service: "api",
        status: "ok",
        dependencies: expect.any(Object)
      })
    );
    expect(typeof response.body.timestamp).toBe("string");
  });
});
