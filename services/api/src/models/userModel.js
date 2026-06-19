const { ObjectId } = require("mongodb");

const USERS_COLLECTION = "users";

function normalizeEmail(email) {
  return String(email).trim().toLowerCase();
}

async function ensureUserIndexes(database) {
  await database.collection(USERS_COLLECTION).createIndex(
    { email: 1 },
    {
      unique: true,
      name: "users_unique_email"
    }
  );
}

async function createUser(database, { email, passwordHash }) {
  const now = new Date();
  const userDocument = {
    email: normalizeEmail(email),
    passwordHash,
    createdAt: now,
    updatedAt: now
  };

  const insertResult = await database.collection(USERS_COLLECTION).insertOne(userDocument);
  return {
    _id: insertResult.insertedId,
    ...userDocument
  };
}

async function findUserByEmail(database, email) {
  return database.collection(USERS_COLLECTION).findOne({
    email: normalizeEmail(email)
  });
}

async function findUserById(database, userId) {
  let parsedObjectId;
  try {
    parsedObjectId = new ObjectId(String(userId));
  } catch (_error) {
    return null;
  }

  return database.collection(USERS_COLLECTION).findOne({ _id: parsedObjectId });
}

function toPublicUser(userDocument) {
  if (!userDocument) {
    return null;
  }

  return {
    id: userDocument._id.toString(),
    email: userDocument.email,
    createdAt: userDocument.createdAt
  };
}

module.exports = {
  createUser,
  ensureUserIndexes,
  findUserByEmail,
  findUserById,
  toPublicUser
};
