const { z } = require("zod");

const semesterCodeSchema = z
  .string()
  .regex(/^\d{4}-[12]$/, "Semester code must match YYYY-1 or YYYY-2 format");

const objectIdSchema = z
  .string()
  .regex(/^[a-f0-9]{24}$/i, "Identifier must be a valid ObjectId");

const gradeSchema = z.enum(
  ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F", "Pass", "Fail"],
  { errorMap: () => ({ message: "Grade must be a valid letter grade or Pass/Fail" }) }
);

const metadataSchema = z
  .object({
    notes: z.string().max(500).optional()
  })
  .strict();

const createCompletedCourseSchema = z
  .object({
    courseId: objectIdSchema,
    semesterCode: semesterCodeSchema,
    grade: gradeSchema,
    gradePoints: z.number().min(0).max(100).optional(),
    creditsEarned: z.number().min(0).max(36),
    attempt: z.number().int().min(1).max(5).optional(),
    source: z.literal("manual").optional(),
    metadata: metadataSchema.optional()
  })
  .strict();

const updateCompletedCourseSchema = z
  .object({
    semesterCode: semesterCodeSchema.optional(),
    grade: gradeSchema.optional(),
    gradePoints: z.number().min(0).max(100).optional(),
    creditsEarned: z.number().min(0).max(36).optional(),
    metadata: metadataSchema.optional()
  })
  .strict()
  .refine((payload) => Object.keys(payload).length > 0, {
    message: "At least one field is required for update"
  });

const completedCourseListQuerySchema = z
  .object({
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional()
  })
  .strict();

const completedCourseIdParamSchema = z.object({
  id: objectIdSchema
});

function validateCreateCompletedCoursePayload(payload) {
  return createCompletedCourseSchema.safeParse(payload);
}

function validateUpdateCompletedCoursePayload(payload) {
  return updateCompletedCourseSchema.safeParse(payload);
}

function validateCompletedCourseListQuery(query) {
  return completedCourseListQuerySchema.safeParse(query);
}

function validateCompletedCourseIdParam(params) {
  return completedCourseIdParamSchema.strict().safeParse(params);
}

module.exports = {
  validateCompletedCourseIdParam,
  validateCompletedCourseListQuery,
  validateCreateCompletedCoursePayload,
  validateUpdateCompletedCoursePayload
};
