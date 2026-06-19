const { hashPassword, verifyPassword } = require("../../src/security/password");

describe("password security", () => {
  test("hashPassword returns a bcrypt hash and not plain text", async () => {
    const plainTextPassword = "StrongPass123!";
    const hashedPassword = await hashPassword(plainTextPassword);

    expect(hashedPassword).not.toBe(plainTextPassword);
    expect(hashedPassword.startsWith("$2")).toBe(true);
  });

  test("verifyPassword returns true for matching password", async () => {
    const plainTextPassword = "StrongPass123!";
    const hashedPassword = await hashPassword(plainTextPassword);

    const isValid = await verifyPassword(plainTextPassword, hashedPassword);
    expect(isValid).toBe(true);
  });

  test("verifyPassword returns false for non-matching password", async () => {
    const plainTextPassword = "StrongPass123!";
    const hashedPassword = await hashPassword(plainTextPassword);

    const isValid = await verifyPassword("WrongPassword1!", hashedPassword);
    expect(isValid).toBe(false);
  });
});
