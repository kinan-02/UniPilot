const { ObjectId } = require("mongodb");

const COMPLETED_COURSES_COLLECTION = "completed_courses";

function parseObjectId(value) {
  try {
    return new ObjectId(String(value));
  } catch (_error) {
    return null;
  }
}

async function ensureCompletedCourseIndexes(database) {
  await database.collection(COMPLETED_COURSES_COLLECTION).createIndex(
    { userId: 1, courseId: 1, attempt: 1 },
    {
      unique: true,
      name: "completed_courses_unique_user_course_attempt"
    }
  );

  await database.collection(COMPLETED_COURSES_COLLECTION).createIndex(
    { userId: 1, semesterCode: 1 },
    {
      name: "completed_courses_user_semester"
    }
  );

  await database.collection(COMPLETED_COURSES_COLLECTION).createIndex(
    { userId: 1, recordedAt: -1 },
    {
      name: "completed_courses_user_recorded_at"
    }
  );
}

function buildCompletedCourseDocument(userId, recordData) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    throw new Error("Invalid user id for completed course");
  }

  const now = new Date();

  return {
    userId: parsedUserId,
    courseId: parseObjectId(recordData.courseId),
    courseOfferingId: null,
    semesterCode: recordData.semesterCode,
    grade: recordData.grade,
    gradePoints: recordData.gradePoints ?? null,
    creditsEarned: recordData.creditsEarned,
    attempt: recordData.attempt ?? 1,
    source: recordData.source ?? "manual",
    metadata: recordData.metadata ?? {},
    recordedAt: now,
    createdAt: now,
    updatedAt: now
  };
}

async function createCompletedCourse(database, userId, recordData) {
  const document = buildCompletedCourseDocument(userId, recordData);
  const insertResult = await database
    .collection(COMPLETED_COURSES_COLLECTION)
    .insertOne(document);

  return {
    _id: insertResult.insertedId,
    ...document
  };
}

async function findCompletedCoursesByUserId(
  database,
  userId,
  { page = 1, limit = 50 } = {}
) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    return { records: [], total: 0, page: 1, limit };
  }

  const safePage = Math.max(page, 1);
  const safeLimit = Math.min(Math.max(limit, 1), 100);
  const skip = (safePage - 1) * safeLimit;

  const collection = database.collection(COMPLETED_COURSES_COLLECTION);
  const query = { userId: parsedUserId };

  const [records, total] = await Promise.all([
    collection.find(query).sort({ recordedAt: -1 }).skip(skip).limit(safeLimit).toArray(),
    collection.countDocuments(query)
  ]);

  return {
    records,
    total,
    page: safePage,
    limit: safeLimit
  };
}

async function findCompletedCourseByIdAndUserId(database, recordId, userId) {
  const parsedRecordId = parseObjectId(recordId);
  const parsedUserId = parseObjectId(userId);
  if (!parsedRecordId || !parsedUserId) {
    return null;
  }

  return database.collection(COMPLETED_COURSES_COLLECTION).findOne({
    _id: parsedRecordId,
    userId: parsedUserId
  });
}

async function updateCompletedCourseByIdAndUserId(database, recordId, userId, updates) {
  const existingRecord = await findCompletedCourseByIdAndUserId(database, recordId, userId);
  if (!existingRecord) {
    return { status: "not_found" };
  }

  if (existingRecord.source !== "manual") {
    return { status: "not_editable", record: existingRecord };
  }

  const updateDocument = {
    updatedAt: new Date()
  };

  if (updates.semesterCode !== undefined) {
    updateDocument.semesterCode = updates.semesterCode;
  }
  if (updates.grade !== undefined) {
    updateDocument.grade = updates.grade;
  }
  if (updates.gradePoints !== undefined) {
    updateDocument.gradePoints = updates.gradePoints;
  }
  if (updates.creditsEarned !== undefined) {
    updateDocument.creditsEarned = updates.creditsEarned;
  }
  if (updates.metadata !== undefined) {
    updateDocument.metadata = updates.metadata;
  }

  const updateResult = await database
    .collection(COMPLETED_COURSES_COLLECTION)
    .findOneAndUpdate(
      { _id: existingRecord._id, userId: existingRecord.userId, source: "manual" },
      { $set: updateDocument },
      { returnDocument: "after" }
    );

  if (!updateResult) {
    return { status: "not_found" };
  }

  return { status: "updated", record: updateResult };
}

async function deleteCompletedCourseByIdAndUserId(database, recordId, userId) {
  const existingRecord = await findCompletedCourseByIdAndUserId(database, recordId, userId);
  if (!existingRecord) {
    return { status: "not_found" };
  }

  if (existingRecord.source !== "manual") {
    return { status: "not_editable", record: existingRecord };
  }

  const deleteResult = await database.collection(COMPLETED_COURSES_COLLECTION).deleteOne({
    _id: existingRecord._id,
    userId: existingRecord.userId,
    source: "manual"
  });

  if (!deleteResult.deletedCount) {
    return { status: "not_found" };
  }

  return { status: "deleted" };
}

function toPublicCompletedCourse(recordDocument, courseSummary = null) {
  if (!recordDocument) {
    return null;
  }

  return {
    id: recordDocument._id.toString(),
    courseId: recordDocument.courseId.toString(),
    courseNumber: courseSummary?.number ?? null,
    courseTitle: courseSummary?.title ?? null,
    semesterCode: recordDocument.semesterCode,
    grade: recordDocument.grade,
    gradePoints: recordDocument.gradePoints,
    creditsEarned: recordDocument.creditsEarned,
    attempt: recordDocument.attempt,
    source: recordDocument.source,
    metadata: recordDocument.metadata ?? {},
    recordedAt: recordDocument.recordedAt,
    createdAt: recordDocument.createdAt,
    updatedAt: recordDocument.updatedAt
  };
}

module.exports = {
  createCompletedCourse,
  deleteCompletedCourseByIdAndUserId,
  ensureCompletedCourseIndexes,
  findCompletedCourseByIdAndUserId,
  findCompletedCoursesByUserId,
  toPublicCompletedCourse,
  updateCompletedCourseByIdAndUserId
};
