const { ObjectId } = require("mongodb");

const DEGREE_REQUIREMENTS_COLLECTION = "degree_requirements";

function parseObjectId(value) {
  try {
    return new ObjectId(String(value));
  } catch (_error) {
    return null;
  }
}

async function ensureDegreeRequirementIndexes(database) {
  await database.collection(DEGREE_REQUIREMENTS_COLLECTION).createIndex(
    { degreeId: 1, version: 1, priority: 1 },
    {
      name: "degree_requirements_degree_version_priority"
    }
  );

  await database.collection(DEGREE_REQUIREMENTS_COLLECTION).createIndex(
    { degreeId: 1, requirementType: 1 },
    {
      name: "degree_requirements_degree_type"
    }
  );
}

async function findDegreeRequirementsByDegreeId(
  database,
  degreeId,
  { status = "published", version = null } = {}
) {
  const parsedDegreeId = parseObjectId(degreeId);
  if (!parsedDegreeId) {
    return [];
  }

  const query = {
    degreeId: parsedDegreeId,
    status
  };

  if (version) {
    query.version = version;
  }

  return database
    .collection(DEGREE_REQUIREMENTS_COLLECTION)
    .find(query)
    .sort({ priority: 1 })
    .toArray();
}

function toPublicDegreeRequirement(requirementDocument) {
  if (!requirementDocument) {
    return null;
  }

  return {
    id: requirementDocument._id.toString(),
    degreeId: requirementDocument.degreeId.toString(),
    version: requirementDocument.version,
    catalogYear: requirementDocument.catalogYear,
    catalogVersion: requirementDocument.catalogVersion,
    requirementType: requirementDocument.requirementType,
    title: requirementDocument.title,
    ruleExpression: requirementDocument.ruleExpression,
    minCredits: requirementDocument.minCredits,
    courseIds: (requirementDocument.courseSet ?? []).map((id) => id.toString()),
    priority: requirementDocument.priority,
    isMandatory: requirementDocument.isMandatory,
    status: requirementDocument.status,
    metadata: requirementDocument.metadata ?? {},
    sourceRefs: requirementDocument.sourceRefs ?? [],
    createdAt: requirementDocument.createdAt,
    updatedAt: requirementDocument.updatedAt
  };
}

module.exports = {
  ensureDegreeRequirementIndexes,
  findDegreeRequirementsByDegreeId,
  toPublicDegreeRequirement
};
