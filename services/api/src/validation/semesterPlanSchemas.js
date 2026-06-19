const { z } = require("zod");

const semesterCodeSchema = z
  .string()
  .regex(/^\d{4}-[12]$/, "Semester code must match YYYY-1 or YYYY-2 format");

const objectIdSchema = z
  .string()
  .regex(/^[a-f0-9]{24}$/i, "Identifier must be a valid ObjectId");

function isHalfCreditIncrement(value) {
  return Math.abs(value * 2 - Math.round(value * 2)) < 1e-9;
}

const creditLoadSchema = z
  .number()
  .min(0, "Credits must be at least 0")
  .max(36, "Credits must be at most 36")
  .refine(isHalfCreditIncrement, {
    message: "Credits must be in 0.5 increments"
  });

const generateSemesterPlanSchema = z
  .object({
    semesterCode: semesterCodeSchema,
    maxCredits: creditLoadSchema.optional(),
    minCredits: creditLoadSchema.optional(),
    name: z.string().trim().min(1).max(120).optional()
  })
  .strict()
  .refine(
    (payload) =>
      payload.maxCredits === undefined ||
      payload.minCredits === undefined ||
      payload.minCredits <= payload.maxCredits,
    {
      message: "minCredits cannot be greater than maxCredits"
    }
  );

const semesterPlanListQuerySchema = z
  .object({
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional()
  })
  .strict();

const semesterPlanIdParamSchema = z.object({
  id: objectIdSchema
});

function validateGenerateSemesterPlanPayload(payload) {
  return generateSemesterPlanSchema.safeParse(payload);
}

function validateSemesterPlanListQuery(query) {
  return semesterPlanListQuerySchema.safeParse(query);
}

function validateSemesterPlanIdParam(params) {
  return semesterPlanIdParamSchema.strict().safeParse(params);
}

module.exports = {
  validateGenerateSemesterPlanPayload,
  validateSemesterPlanIdParam,
  validateSemesterPlanListQuery
};
