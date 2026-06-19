const { z } = require("zod");

const objectIdSchema = z
  .string()
  .regex(/^[a-f0-9]{24}$/i, "Identifier must be a valid ObjectId");

const catalogListQuerySchema = z
  .object({
    institutionId: z.string().trim().min(1).max(100),
    catalogYear: z.coerce.number().int().min(1990).max(2100)
  })
  .strict();

const courseListQuerySchema = catalogListQuerySchema
  .extend({
    page: z.coerce.number().int().min(1).optional(),
    limit: z.coerce.number().int().min(1).max(100).optional()
  })
  .strict();

const resourceIdParamsSchema = z
  .object({
    courseId: objectIdSchema.optional(),
    degreeId: objectIdSchema.optional()
  })
  .strict();

function validateCourseListQuery(query) {
  return courseListQuerySchema.safeParse(query);
}

function validateCatalogListQuery(query) {
  return catalogListQuerySchema.safeParse(query);
}

function validateCourseIdParam(params) {
  return z.object({ courseId: objectIdSchema }).strict().safeParse(params);
}

function validateDegreeIdParam(params) {
  return z.object({ degreeId: objectIdSchema }).strict().safeParse(params);
}

module.exports = {
  validateCatalogListQuery,
  validateCourseIdParam,
  validateCourseListQuery,
  validateDegreeIdParam
};
