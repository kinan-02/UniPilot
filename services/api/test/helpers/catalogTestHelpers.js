const { seedCatalogIntoDatabase } = require("../../src/catalog/seedCatalogIntoDatabase");

const TECHNION_SEED = {
  institutionId: "technion",
  catalogYear: 2025,
  degreeId: "665f2b0f2a3f7b2a1a9a7d01",
  courseIds: {
    foundations: "665f2b0f2a3f7b2a1a9a7c01",
    machineLearning: "665f2b0f2a3f7b2a1a9a7c07"
  }
};

async function seedTechnionCatalogForTests(database) {
  return seedCatalogIntoDatabase(database, {
    institutionId: TECHNION_SEED.institutionId,
    catalogYear: TECHNION_SEED.catalogYear
  });
}

module.exports = {
  TECHNION_SEED,
  seedTechnionCatalogForTests
};
