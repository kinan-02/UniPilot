const { ObjectId } = require("mongodb");

const SEMESTER_PLANS_COLLECTION = "semester_plans";

function parseObjectId(value) {
  try {
    return new ObjectId(String(value));
  } catch (_error) {
    return null;
  }
}

async function ensureSemesterPlanIndexes(database) {
  await database.collection(SEMESTER_PLANS_COLLECTION).createIndex(
    { userId: 1, updatedAt: -1 },
    {
      name: "semester_plans_user_updated_at"
    }
  );

  await database.collection(SEMESTER_PLANS_COLLECTION).createIndex(
    { userId: 1, status: 1 },
    {
      name: "semester_plans_user_status"
    }
  );
}

function buildSemesterPlanDocument(userId, planData) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    throw new Error("Invalid user id for semester plan");
  }

  const now = new Date();

  return {
    userId: parsedUserId,
    name: planData.name,
    status: planData.status ?? "draft",
    version: planData.version ?? 1,
    basePlanId: null,
    plannerType: planData.plannerType ?? "deterministic",
    assumptions: planData.assumptions ?? {},
    explanation: planData.explanation ?? {},
    semesters: planData.semesters ?? [],
    createdAt: now,
    updatedAt: now
  };
}

async function createSemesterPlan(database, userId, planData) {
  const document = buildSemesterPlanDocument(userId, planData);
  const insertResult = await database.collection(SEMESTER_PLANS_COLLECTION).insertOne(document);

  return {
    _id: insertResult.insertedId,
    ...document
  };
}

async function findSemesterPlansByUserId(database, userId, { page = 1, limit = 50 } = {}) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    return { plans: [], total: 0, page: 1, limit };
  }

  const safePage = Math.max(page, 1);
  const safeLimit = Math.min(Math.max(limit, 1), 100);
  const skip = (safePage - 1) * safeLimit;

  const collection = database.collection(SEMESTER_PLANS_COLLECTION);
  const query = { userId: parsedUserId };

  const [plans, total] = await Promise.all([
    collection.find(query).sort({ createdAt: -1 }).skip(skip).limit(safeLimit).toArray(),
    collection.countDocuments(query)
  ]);

  return {
    plans,
    total,
    page: safePage,
    limit: safeLimit
  };
}

async function findSemesterPlanByIdAndUserId(database, planId, userId) {
  const parsedPlanId = parseObjectId(planId);
  const parsedUserId = parseObjectId(userId);
  if (!parsedPlanId || !parsedUserId) {
    return null;
  }

  return database.collection(SEMESTER_PLANS_COLLECTION).findOne({
    _id: parsedPlanId,
    userId: parsedUserId
  });
}

function toPublicSemesterPlanSummary(planDocument) {
  if (!planDocument) {
    return null;
  }

  const primarySemester = planDocument.semesters?.[0] ?? null;

  return {
    id: planDocument._id.toString(),
    name: planDocument.name,
    status: planDocument.status,
    version: planDocument.version,
    plannerType: planDocument.plannerType,
    semesterCode: primarySemester?.semesterCode ?? null,
    recommendedCourseCount: primarySemester?.plannedCourses?.length ?? 0,
    totalRecommendedCredits: planDocument.explanation?.totalRecommendedCredits ?? 0,
    summary: planDocument.explanation?.summary ?? null,
    createdAt: planDocument.createdAt,
    updatedAt: planDocument.updatedAt
  };
}

function toPublicSemesterPlan(planDocument) {
  if (!planDocument) {
    return null;
  }

  return {
    id: planDocument._id.toString(),
    name: planDocument.name,
    status: planDocument.status,
    version: planDocument.version,
    plannerType: planDocument.plannerType,
    assumptions: planDocument.assumptions ?? {},
    explanation: planDocument.explanation ?? {},
    semesters: (planDocument.semesters ?? []).map((semester) => ({
      semesterCode: semester.semesterCode,
      goalCredits: semester.goalCredits,
      order: semester.order,
      plannedCourses: semester.plannedCourses ?? [],
      notes: semester.notes ?? "",
      constraintsSnapshot: semester.constraintsSnapshot ?? {}
    })),
    createdAt: planDocument.createdAt,
    updatedAt: planDocument.updatedAt
  };
}

module.exports = {
  createSemesterPlan,
  ensureSemesterPlanIndexes,
  findSemesterPlanByIdAndUserId,
  findSemesterPlansByUserId,
  toPublicSemesterPlan,
  toPublicSemesterPlanSummary
};
