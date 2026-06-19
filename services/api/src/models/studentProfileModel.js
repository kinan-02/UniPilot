const { ObjectId } = require("mongodb");

const STUDENT_PROFILES_COLLECTION = "student_profiles";

async function ensureStudentProfileIndexes(database) {
  await database.collection(STUDENT_PROFILES_COLLECTION).createIndex(
    { userId: 1 },
    {
      unique: true,
      name: "student_profiles_unique_user"
    }
  );

  await database.collection(STUDENT_PROFILES_COLLECTION).createIndex(
    { degreeId: 1 },
    {
      name: "student_profiles_degree_id"
    }
  );
}

function parseObjectId(value) {
  try {
    return new ObjectId(String(value));
  } catch (_error) {
    return null;
  }
}

function buildProfileDocument(userId, profileData) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    throw new Error("Invalid user id for student profile");
  }

  const now = new Date();

  return {
    userId: parsedUserId,
    institutionId: profileData.institutionId,
    programType: profileData.programType,
    degreeId: profileData.degreeId ? parseObjectId(profileData.degreeId) : null,
    catalogYear: profileData.catalogYear,
    currentSemesterCode: profileData.currentSemesterCode,
    preferences: profileData.preferences ?? {},
    revision: 1,
    createdAt: now,
    updatedAt: now
  };
}

async function createStudentProfile(database, userId, profileData) {
  const profileDocument = buildProfileDocument(userId, profileData);
  const insertResult = await database
    .collection(STUDENT_PROFILES_COLLECTION)
    .insertOne(profileDocument);

  return {
    _id: insertResult.insertedId,
    ...profileDocument
  };
}

async function findStudentProfileByUserId(database, userId) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    return null;
  }

  return database.collection(STUDENT_PROFILES_COLLECTION).findOne({
    userId: parsedUserId
  });
}

async function updateStudentProfileByUserId(database, userId, updates) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    return null;
  }

  const updateDocument = {
    updatedAt: new Date()
  };

  if (updates.institutionId !== undefined) {
    updateDocument.institutionId = updates.institutionId;
  }
  if (updates.programType !== undefined) {
    updateDocument.programType = updates.programType;
  }
  if (updates.degreeId !== undefined) {
    updateDocument.degreeId = updates.degreeId ? parseObjectId(updates.degreeId) : null;
  }
  if (updates.catalogYear !== undefined) {
    updateDocument.catalogYear = updates.catalogYear;
  }
  if (updates.currentSemesterCode !== undefined) {
    updateDocument.currentSemesterCode = updates.currentSemesterCode;
  }
  if (updates.preferences !== undefined) {
    updateDocument.preferences = updates.preferences;
  }

  const updateResult = await database.collection(STUDENT_PROFILES_COLLECTION).findOneAndUpdate(
    { userId: parsedUserId },
    {
      $set: updateDocument,
      $inc: { revision: 1 }
    },
    { returnDocument: "after" }
  );

  return updateResult;
}

async function deleteStudentProfileByUserId(database, userId) {
  const parsedUserId = parseObjectId(userId);
  if (!parsedUserId) {
    return { deletedCount: 0 };
  }

  return database.collection(STUDENT_PROFILES_COLLECTION).deleteOne({
    userId: parsedUserId
  });
}

function toPublicStudentProfile(profileDocument) {
  if (!profileDocument) {
    return null;
  }

  return {
    id: profileDocument._id.toString(),
    userId: profileDocument.userId.toString(),
    institutionId: profileDocument.institutionId,
    programType: profileDocument.programType,
    degreeId: profileDocument.degreeId ? profileDocument.degreeId.toString() : null,
    catalogYear: profileDocument.catalogYear,
    currentSemesterCode: profileDocument.currentSemesterCode,
    preferences: profileDocument.preferences ?? {},
    revision: profileDocument.revision,
    createdAt: profileDocument.createdAt,
    updatedAt: profileDocument.updatedAt
  };
}

module.exports = {
  createStudentProfile,
  deleteStudentProfileByUserId,
  ensureStudentProfileIndexes,
  findStudentProfileByUserId,
  toPublicStudentProfile,
  updateStudentProfileByUserId
};
