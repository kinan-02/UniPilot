const { z } = require("zod");

const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters long")
  .max(128, "Password must be at most 128 characters long")
  .regex(/[A-Z]/, "Password must include at least one uppercase letter")
  .regex(/[a-z]/, "Password must include at least one lowercase letter")
  .regex(/[0-9]/, "Password must include at least one number")
  .regex(/[^A-Za-z0-9]/, "Password must include at least one special character");

const registerSchema = z
  .object({
    email: z.string().email("Email must be valid").max(254, "Email must be at most 254 characters"),
    password: passwordSchema
  })
  .strict();

const loginSchema = z
  .object({
    email: z.string().email("Email must be valid").max(254, "Email must be at most 254 characters"),
    password: z.string().min(1, "Password is required")
  })
  .strict();

function validateRegisterPayload(payload) {
  return registerSchema.safeParse(payload);
}

function validateLoginPayload(payload) {
  return loginSchema.safeParse(payload);
}

module.exports = {
  validateLoginPayload,
  validateRegisterPayload
};
