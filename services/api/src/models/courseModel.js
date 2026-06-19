const { ObjectId } = require("mongodb");

const COURSES_COLLECTION = "courses";

function parseObjectId(value) {
  try {
    return new ObjectId(String(value));
  } catch (_error) {
    return null;
  }
}

async function ensureCourseIndexes(database) {
  await database.collection(COURSES_COLLECTION).createIndex(
    { institutionId: 1, subject: 1, number: 1, version: 1 },
    {
      unique: true,
      name: "courses_unique_institution_subject_number_version"
    }
  );

  await database.collection(COURSES_COLLECTION).createIndex(
    { institutionId: 1, catalogYear: 1, status: 1 },
    {
      name: "courses_institution_catalog_year_status"
    }
  );
}

async function findCourses(
  database,
  { institutionId, catalogYear, status = "published", page = 1, limit = 50 }
) {
  const query = {
    institutionId,
    catalogYear,
    status
  };

  const safePage = Math.max(page, 1);
  const safeLimit = Math.min(Math.max(limit, 1), 100);
  const skip = (safePage - 1) * safeLimit;

  const collection = database.collection(COURSES_COLLECTION);
  const [courses, total] = await Promise.all([
    collection.find(query).sort({ number: 1 }).skip(skip).limit(safeLimit).toArray(),
    collection.countDocuments(query)
  ]);

  return {
    courses,
    total,
    page: safePage,
    limit: safeLimit
  };
}

async function findCourseById(database, courseId, { status = "published" } = {}) {
  const parsedCourseId = parseObjectId(courseId);
  if (!parsedCourseId) {
    return null;
  }

  return database.collection(COURSES_COLLECTION).findOne({
    _id: parsedCourseId,
    status
  });
}

function toPublicCourse(courseDocument) {
  if (!courseDocument) {
    return null;
  }

  return {
    id: courseDocument._id.toString(),
    institutionId: courseDocument.institutionId,
    subject: courseDocument.subject,
    number: courseDocument.number,
    title: courseDocument.title,
    credits: courseDocument.credits,
    description: courseDocument.description,
    level: courseDocument.level,
    tags: courseDocument.tags ?? [],
    prerequisiteIds: (courseDocument.prerequisites ?? []).map((id) => id.toString()),
    corequisiteIds: (courseDocument.corequisites ?? []).map((id) => id.toString()),
    catalogYear: courseDocument.catalogYear,
    catalogVersion: courseDocument.catalogVersion,
    version: courseDocument.version,
    status: courseDocument.status,
    metadata: courseDocument.metadata ?? {},
    sourceRefs: courseDocument.sourceRefs ?? [],
    createdAt: courseDocument.createdAt,
    updatedAt: courseDocument.updatedAt
  };
}

module.exports = {
  ensureCourseIndexes,
  findCourseById,
  findCourses,
  toPublicCourse
};
