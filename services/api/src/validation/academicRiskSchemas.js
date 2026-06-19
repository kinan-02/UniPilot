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

const analyzeByPlanSchema = z
  .object({
    planId: objectIdSchema
  })
  .strict();

const analyzeAdhocSchema = z
  .object({
    semesterCode: semesterCodeSchema,
    courseIds: z.array(objectIdSchema).min(1, "At least one courseId is required").max(20),
    maxCredits: creditLoadSchema.optional(),
    minCredits: creditLoadSchema.optional()
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

const analyzeAcademicRiskSchema = z.union([analyzeByPlanSchema, analyzeAdhocSchema]);

const academicRiskListQuerySchema = z
  .object({
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional()
  })
  .strict();

const academicRiskIdParamSchema = z.object({
  id: objectIdSchema
});

function validateAnalyzeAcademicRiskPayload(payload) {
  return analyzeAcademicRiskSchema.safeParse(payload);
}

function validateAcademicRiskListQuery(query) {
  return academicRiskListQuerySchema.safeParse(query);
}

function validateAcademicRiskIdParam(params) {
  return academicRiskIdParamSchema.strict().safeParse(params);
}

module.exports = {
  validateAcademicRiskIdParam,
  validateAcademicRiskListQuery,
  validateAnalyzeAcademicRiskPayload
};
