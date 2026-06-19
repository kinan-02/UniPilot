const { MongoMemoryServer } = require("mongodb-memory-server");
const { ObjectId } = require("mongodb");
const { closeMongoClient, getDatabase } = require("../../src/db/mongoClient");
const { seedCatalogIntoDatabase } = require("../../src/catalog/seedCatalogIntoDatabase");

const TECHNION_DEGREE_ID = new ObjectId("665f2b0f2a3f7b2a1a9a7d01");

jest.setTimeout(30_000);

describe("catalog seed idempotency", () => {
  let mongoServer;

  beforeAll(async () => {
    mongoServer = await MongoMemoryServer.create();
    process.env.MONGO_URI = mongoServer.getUri("unipilot_seed_idempotency_test");
  });

  afterAll(async () => {
    await closeMongoClient();
    if (mongoServer) {
      await mongoServer.stop();
    }
  });

  test("seedCatalogIntoDatabase can run twice without error and preserves createdAt", async () => {
    const database = await getDatabase();

    const firstRun = await seedCatalogIntoDatabase(database, {
      institutionId: "technion",
      catalogYear: 2025
    });
    const degreeAfterFirst = await database.collection("degrees").findOne({
      _id: TECHNION_DEGREE_ID
    });

    const secondRun = await seedCatalogIntoDatabase(database, {
      institutionId: "technion",
      catalogYear: 2025
    });
    const degreeAfterSecond = await database.collection("degrees").findOne({
      _id: TECHNION_DEGREE_ID
    });

    expect(firstRun.counts.degrees).toBe(1);
    expect(secondRun.counts.degrees).toBe(1);
    expect(degreeAfterSecond.createdAt.getTime()).toBe(degreeAfterFirst.createdAt.getTime());
    expect(degreeAfterSecond.metadata.isCuratedPlaceholder).toBe(true);
  });
});
