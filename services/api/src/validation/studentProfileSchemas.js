const { z } = require("zod");

const semesterCodeSchema = z
  .string()
  .regex(/^\d{4}-[12]$/, "Semester code must match YYYY-1 or YYYY-2 format");

const objectIdSchema = z
  .string()
  .regex(/^[a-f0-9]{24}$/i, "Identifier must be a valid ObjectId");

const preferencesSchema = z
  .object({
    maxCreditsPerSemester: z.number().int().min(1).max(36).optional()
  })
  .strict();

const createStudentProfileSchema = z
  .object({
    institutionId: z.string().trim().min(1, "Institution id is required").max(100),
    programType: z.string().trim().min(1, "Program type is required").max(100),
    degreeId: objectIdSchema.optional(),
    catalogYear: z.number().int().min(1990).max(2100),
    currentSemesterCode: semesterCodeSchema,
    preferences: preferencesSchema.optional()
  })
  .strict();

const updateStudentProfileSchema = z
  .object({
    institutionId: z.string().trim().min(1).max(100).optional(),
    programType: z.string().trim().min(1).max(100).optional(),
    degreeId: objectIdSchema.optional(),
    catalogYear: z.number().int().min(1990).max(2100).optional(),
    currentSemesterCode: semesterCodeSchema.optional(),
    preferences: preferencesSchema.optional(),
    _id: objectIdSchema.optional()
  })
  .strict()
  .refine((payload) => Object.keys(payload).length > 0, {
    message: "At least one field is required for update"
  });

function validateCreateStudentProfilePayload(payload) {
  return createStudentProfileSchema.safeParse(payload);
}

function validateUpdateStudentProfilePayload(payload) {
  return updateStudentProfileSchema.safeParse(payload);
}

module.exports = {
  validateCreateStudentProfilePayload,
  validateUpdateStudentProfilePayload
};
