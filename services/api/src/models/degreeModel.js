const { ObjectId } = require("mongodb");

const DEGREES_COLLECTION = "degrees";

function parseObjectId(value) {
  try {
    return new ObjectId(String(value));
  } catch (_error) {
    return null;
  }
}

async function ensureDegreeIndexes(database) {
  await database.collection(DEGREES_COLLECTION).createIndex(
    { institutionId: 1, code: 1, version: 1 },
    {
      unique: true,
      name: "degrees_unique_institution_code_version"
    }
  );

  await database.collection(DEGREES_COLLECTION).createIndex(
    { institutionId: 1, catalogYear: 1, status: 1 },
    {
      name: "degrees_institution_catalog_year_status"
    }
  );
}

async function findDegrees(database, { institutionId, catalogYear, status = "published" }) {
  const query = {
    institutionId,
    catalogYear,
    status
  };

  return database
    .collection(DEGREES_COLLECTION)
    .find(query)
    .sort({ code: 1 })
    .toArray();
}

async function findDegreeById(database, degreeId, { status = "published" } = {}) {
  const parsedDegreeId = parseObjectId(degreeId);
  if (!parsedDegreeId) {
    return null;
  }

  return database.collection(DEGREES_COLLECTION).findOne({
    _id: parsedDegreeId,
    status
  });
}

function toPublicDegree(degreeDocument) {
  if (!degreeDocument) {
    return null;
  }

  return {
    id: degreeDocument._id.toString(),
    institutionId: degreeDocument.institutionId,
    code: degreeDocument.code,
    name: degreeDocument.name,
    version: degreeDocument.version,
    catalogYear: degreeDocument.catalogYear,
    catalogVersion: degreeDocument.catalogVersion,
    effectiveFrom: degreeDocument.effectiveFrom,
    effectiveTo: degreeDocument.effectiveTo,
    status: degreeDocument.status,
    metadata: degreeDocument.metadata ?? {},
    sourceRefs: degreeDocument.sourceRefs ?? [],
    createdAt: degreeDocument.createdAt,
    updatedAt: degreeDocument.updatedAt
  };
}

module.exports = {
  ensureDegreeIndexes,
  findDegreeById,
  findDegrees,
  toPublicDegree
};
