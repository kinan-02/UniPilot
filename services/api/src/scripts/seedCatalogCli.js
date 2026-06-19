const { closeMongoClient, getDatabase } = require("../db/mongoClient");
const { seedCatalogIntoDatabase } = require("../catalog/seedCatalogIntoDatabase");

async function runSeedCatalogCli(argv = process.argv.slice(2)) {
  const institutionId = readFlagValue(argv, "--institution") || "technion";
  const catalogYear = Number(readFlagValue(argv, "--catalogYear") || "2025");

  if (!process.env.MONGO_URI) {
    throw new Error("MONGO_URI is required to seed the catalog.");
  }

  if (!Number.isInteger(catalogYear)) {
    throw new Error("--catalogYear must be an integer.");
  }

  const database = await getDatabase();
  const result = await seedCatalogIntoDatabase(database, { institutionId, catalogYear });
  await closeMongoClient();
  return result;
}

function readFlagValue(args, flagName) {
  const flagIndex = args.indexOf(flagName);
  if (flagIndex === -1) {
    return null;
  }

  return args[flagIndex + 1] ?? null;
}

if (require.main === module) {
  runSeedCatalogCli()
    .then((result) => {
      console.log(
        JSON.stringify(
          {
            success: true,
            message: "Catalog seeded successfully",
            result
          },
          null,
          2
        )
      );
      process.exit(0);
    })
    .catch((error) => {
      console.error("Catalog seed failed:", error.message);
      closeMongoClient().catch(() => undefined);
      process.exit(1);
    });
}

module.exports = {
  runSeedCatalogCli
};
