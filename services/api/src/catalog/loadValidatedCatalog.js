const fs = require("fs/promises");
const path = require("path");
const { getValidatedCatalogDirectory } = require("./catalogPaths");

async function readJsonFile(filePath) {
  const fileContents = await fs.readFile(filePath, "utf8");
  return JSON.parse(fileContents);
}

async function loadValidatedCatalog({ institutionId, catalogYear }) {
  const catalogDirectory = getValidatedCatalogDirectory({ institutionId, catalogYear });

  const [meta, degrees, courses, degreeRequirements] = await Promise.all([
    readJsonFile(path.join(catalogDirectory, "catalog.meta.json")),
    readJsonFile(path.join(catalogDirectory, "degrees.json")),
    readJsonFile(path.join(catalogDirectory, "courses.json")),
    readJsonFile(path.join(catalogDirectory, "degree_requirements.json"))
  ]);

  return {
    meta,
    degrees,
    courses,
    degreeRequirements
  };
}

module.exports = {
  loadValidatedCatalog
};
