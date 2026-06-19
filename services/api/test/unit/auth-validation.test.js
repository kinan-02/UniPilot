const {
  validateRegisterPayload,
  validateLoginPayload
} = require("../../src/validation/authSchemas");

describe("auth payload validation", () => {
  test("validateRegisterPayload accepts valid payload", () => {
    const result = validateRegisterPayload({
      email: "student@example.com",
      password: "StrongPass123!"
    });

    expect(result.success).toBe(true);
  });

  test("validateRegisterPayload rejects weak password", () => {
    const result = validateRegisterPayload({
      email: "student@example.com",
      password: "123"
    });

    expect(result.success).toBe(false);
  });

  test("validateRegisterPayload rejects passwords longer than bcrypt-safe length", () => {
    const result = validateRegisterPayload({
      email: "student@example.com",
      password: `${"A".repeat(71)}1!`
    });

    expect(result.success).toBe(false);
  });

  test("validateLoginPayload rejects invalid email format", () => {
    const result = validateLoginPayload({
      email: "not-an-email",
      password: "StrongPass123!"
    });

    expect(result.success).toBe(false);
  });

  test("validateRegisterPayload rejects unknown fields", () => {
    const result = validateRegisterPayload({
      email: "student@example.com",
      password: "StrongPass123!",
      role: "admin"
    });

    expect(result.success).toBe(false);
  });
});
