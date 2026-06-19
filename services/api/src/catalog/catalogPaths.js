const path = require("path");

function getRepositoryRoot() {
  return path.resolve(__dirname, "../../../..");
}

function getDataRoot() {
  if (process.env.CATALOG_DATA_ROOT) {
    return process.env.CATALOG_DATA_ROOT;
  }

  return path.join(getRepositoryRoot(), "data");
}

function getValidatedCatalogDirectory({ institutionId, catalogYear }) {
  return path.join(getDataRoot(), "validated", institutionId, String(catalogYear));
}

module.exports = {
  getDataRoot,
  getRepositoryRoot,
  getValidatedCatalogDirectory
};
