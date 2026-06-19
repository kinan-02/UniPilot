const { ObjectId } = require("mongodb");

const ACADEMIC_RISKS_COLLECTION = "academic_risks";

function parseObjectId(value) {
  try {
    return new ObjectId(String(value));
  } catch (_error) {
    return null;
  }
}

async function ensureAcademicRiskIndexes(database) {
  await database.collection(ACADEMIC_RISKS_COLLECTION).createIndex(
    { userId: 1, createdAt: -1 },
    {
      name: "academic_risks_user_created_at"
    }
  );

  await database.collection(ACADEMIC_RISKS_COLLECTION).createIndex(
    { userId: 1, status: 1, "summary.highestSeverity": 1 },
    {
      name: "academic_risks_user_status_severity"
    }
  );

  await database.collection(ACADEMIC_RISKS_COLLECTION).createIndex(
    { userId: 1, planId: 1, createdAt: -1 },
    {
      name: "academic_risks_user_plan_created_at"
    }
  );
}

function buildAcademicRiskDocument(userId, analysisData) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    throw new Error("Invalid user id for academic risk analysis");
  }

  const now = new Date();

  return {
    userId: parsedUserId,
    planId: analysisData.planId ? parseObjectId(analysisData.planId) : null,
    semesterCode: analysisData.semesterCode,
    analyzerType: analysisData.analyzerType ?? "deterministic",
    analysisSource: analysisData.analysisSource ?? "semester_plan",
    status: analysisData.status ?? "open",
    summary: analysisData.summary ?? {
      totalRisks: 0,
      highestSeverity: null,
      counts: { low: 0, medium: 0, high: 0 }
    },
    risks: analysisData.risks ?? [],
    contextSnapshot: analysisData.contextSnapshot ?? {},
    createdAt: now,
    updatedAt: now
  };
}

async function createAcademicRiskAnalysis(database, userId, analysisData) {
  const document = buildAcademicRiskDocument(userId, analysisData);
  const insertResult = await database.collection(ACADEMIC_RISKS_COLLECTION).insertOne(document);

  return {
    _id: insertResult.insertedId,
    ...document
  };
}

async function findAcademicRiskAnalysesByUserId(database, userId, { page = 1, limit = 50 } = {}) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    return { analyses: [], total: 0, page: 1, limit };
  }

  const safePage = Math.max(page, 1);
  const safeLimit = Math.min(Math.max(limit, 1), 100);
  const skip = (safePage - 1) * safeLimit;

  const collection = database.collection(ACADEMIC_RISKS_COLLECTION);
  const query = { userId: parsedUserId };

  const [analyses, total] = await Promise.all([
    collection.find(query).sort({ createdAt: -1 }).skip(skip).limit(safeLimit).toArray(),
    collection.countDocuments(query)
  ]);

  return {
    analyses,
    total,
    page: safePage,
    limit: safeLimit
  };
}

async function findAcademicRiskAnalysisByIdAndUserId(database, analysisId, userId) {
  const parsedAnalysisId = parseObjectId(analysisId);
  const parsedUserId = parseObjectId(userId);
  if (!parsedAnalysisId || !parsedUserId) {
    return null;
  }

  return database.collection(ACADEMIC_RISKS_COLLECTION).findOne({
    _id: parsedAnalysisId,
    userId: parsedUserId
  });
}

function toPublicAcademicRiskSummary(analysisDocument) {
  if (!analysisDocument) {
    return null;
  }

  return {
    id: analysisDocument._id.toString(),
    planId: analysisDocument.planId ? analysisDocument.planId.toString() : null,
    semesterCode: analysisDocument.semesterCode,
    analyzerType: analysisDocument.analyzerType,
    analysisSource: analysisDocument.analysisSource,
    status: analysisDocument.status,
    summary: analysisDocument.summary,
    createdAt: analysisDocument.createdAt,
    updatedAt: analysisDocument.updatedAt
  };
}

function toPublicAcademicRiskAnalysis(analysisDocument) {
  if (!analysisDocument) {
    return null;
  }

  return {
    id: analysisDocument._id.toString(),
    planId: analysisDocument.planId ? analysisDocument.planId.toString() : null,
    semesterCode: analysisDocument.semesterCode,
    analyzerType: analysisDocument.analyzerType,
    analysisSource: analysisDocument.analysisSource,
    status: analysisDocument.status,
    summary: analysisDocument.summary,
    risks: analysisDocument.risks ?? [],
    contextSnapshot: analysisDocument.contextSnapshot ?? {},
    createdAt: analysisDocument.createdAt,
    updatedAt: analysisDocument.updatedAt
  };
}

module.exports = {
  createAcademicRiskAnalysis,
  ensureAcademicRiskIndexes,
  findAcademicRiskAnalysesByUserId,
  findAcademicRiskAnalysisByIdAndUserId,
  toPublicAcademicRiskAnalysis,
  toPublicAcademicRiskSummary
};
