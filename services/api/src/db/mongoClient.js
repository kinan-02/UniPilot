const { MongoClient } = require("mongodb");

let activeClient = null;
let activeUri = null;
let activeConnectionPromise = null;

function resolveDatabaseName(mongoUri) {
  if (!mongoUri) {
    return process.env.MONGO_DB || "unipilot";
  }

  try {
    const parsedUri = new URL(mongoUri);
    const databaseFromPath = parsedUri.pathname.replace("/", "").trim();
    return databaseFromPath || process.env.MONGO_DB || "unipilot";
  } catch (_error) {
    return process.env.MONGO_DB || "unipilot";
  }
}

async function getMongoClient(mongoUri = process.env.MONGO_URI) {
  if (!mongoUri) {
    throw new Error("MONGO_URI is required");
  }

  if (!activeClient || activeUri !== mongoUri) {
    if (activeClient) {
      await activeClient.close();
    }

    activeUri = mongoUri;
    activeClient = new MongoClient(mongoUri, {
      maxPoolSize: 10
    });
    activeConnectionPromise = activeClient.connect();
  }

  await activeConnectionPromise;
  return activeClient;
}

async function getDatabase() {
  const mongoUri = process.env.MONGO_URI;
  const client = await getMongoClient(mongoUri);
  return client.db(resolveDatabaseName(mongoUri));
}

async function closeMongoClient() {
  if (activeClient) {
    await activeClient.close();
  }

  activeClient = null;
  activeUri = null;
  activeConnectionPromise = null;
}

module.exports = {
  closeMongoClient,
  getDatabase,
  getMongoClient
};
