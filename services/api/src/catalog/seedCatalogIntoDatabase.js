const { ObjectId } = require("mongodb");
const { ensureCourseIndexes } = require("../models/courseModel");
const { ensureDegreeIndexes } = require("../models/degreeModel");
const { ensureDegreeRequirementIndexes } = require("../models/degreeRequirementModel");
const { loadValidatedCatalog } = require("./loadValidatedCatalog");

function parseObjectId(value) {
  return new ObjectId(String(value));
}

function parseOptionalDate(value) {
  if (!value) {
    return null;
  }
  return new Date(value);
}

function mapDegreeRecord(degreeRecord) {
  const now = new Date();

  return {
    _id: parseObjectId(degreeRecord.id),
    institutionId: degreeRecord.institutionId,
    code: degreeRecord.code,
    name: degreeRecord.name,
    version: degreeRecord.version,
    catalogYear: degreeRecord.catalogYear,
    catalogVersion: degreeRecord.catalogVersion,
    effectiveFrom: parseOptionalDate(degreeRecord.effectiveFrom),
    effectiveTo: parseOptionalDate(degreeRecord.effectiveTo),
    status: degreeRecord.status,
    metadata: degreeRecord.metadata ?? {},
    sourceRefs: degreeRecord.sourceRefs ?? [],
    createdAt: now,
    updatedAt: now
  };
}

function mapCourseRecord(courseRecord) {
  const now = new Date();

  return {
    _id: parseObjectId(courseRecord.id),
    institutionId: courseRecord.institutionId,
    subject: courseRecord.subject,
    number: courseRecord.number,
    title: courseRecord.title,
    credits: courseRecord.credits,
    description: courseRecord.description ?? "",
    level: courseRecord.level ?? "undergraduate",
    tags: courseRecord.tags ?? [],
    prerequisites: (courseRecord.prerequisiteCourseIds ?? []).map(parseObjectId),
    corequisites: (courseRecord.corequisiteCourseIds ?? []).map(parseObjectId),
    catalogYear: courseRecord.catalogYear,
    catalogVersion: courseRecord.catalogVersion,
    version: courseRecord.version,
    status: courseRecord.status,
    metadata: courseRecord.metadata ?? {},
    sourceRefs: courseRecord.sourceRefs ?? [],
    createdAt: now,
    updatedAt: now
  };
}

function mapDegreeRequirementRecord(requirementRecord) {
  const now = new Date();

  return {
    _id: parseObjectId(requirementRecord.id),
    degreeId: parseObjectId(requirementRecord.degreeId),
    version: requirementRecord.version,
    catalogYear: requirementRecord.catalogYear,
    catalogVersion: requirementRecord.catalogVersion,
    requirementType: requirementRecord.requirementType,
    title: requirementRecord.title,
    ruleExpression: requirementRecord.ruleExpression,
    minCredits: requirementRecord.minCredits ?? null,
    courseSet: (requirementRecord.courseIds ?? []).map(parseObjectId),
    priority: requirementRecord.priority,
    isMandatory: requirementRecord.isMandatory,
    status: requirementRecord.status,
    metadata: requirementRecord.metadata ?? {},
    sourceRefs: requirementRecord.sourceRefs ?? [],
    createdAt: now,
    updatedAt: now
  };
}

async function upsertCatalogCollection(database, collectionName, documents) {
  const collection = database.collection(collectionName);
  let upsertedCount = 0;

  for (const document of documents) {
    const replaceResult = await collection.replaceOne({ _id: document._id }, document, {
      upsert: true
    });

    if (replaceResult.upsertedCount > 0 || replaceResult.modifiedCount > 0) {
      upsertedCount += 1;
    }
  }

  return upsertedCount;
}

async function seedCatalogIntoDatabase(database, { institutionId, catalogYear }) {
  const catalog = await loadValidatedCatalog({ institutionId, catalogYear });

  await ensureDegreeIndexes(database);
  await ensureCourseIndexes(database);
  await ensureDegreeRequirementIndexes(database);

  const degreeDocuments = catalog.degrees.map(mapDegreeRecord);
  const courseDocuments = catalog.courses.map(mapCourseRecord);
  const requirementDocuments = catalog.degreeRequirements.map(mapDegreeRequirementRecord);

  const degreesSeeded = await upsertCatalogCollection(database, "degrees", degreeDocuments);
  const coursesSeeded = await upsertCatalogCollection(database, "courses", courseDocuments);
  const requirementsSeeded = await upsertCatalogCollection(
    database,
    "degree_requirements",
    requirementDocuments
  );

  return {
    institutionId,
    catalogYear,
    catalogVersion: catalog.meta.catalogVersion,
    counts: {
      degrees: degreesSeeded,
      courses: coursesSeeded,
      degreeRequirements: requirementsSeeded
    }
  };
}

module.exports = {
  mapCourseRecord,
  mapDegreeRecord,
  mapDegreeRequirementRecord,
  seedCatalogIntoDatabase
};
