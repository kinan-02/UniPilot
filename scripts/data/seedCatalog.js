#!/usr/bin/env node

const path = require("path");

const apiRoot = path.resolve(__dirname, "../../services/api");
const { runSeedCatalogCli } = require(path.join(apiRoot, "src/scripts/seedCatalogCli"));

runSeedCatalogCli(process.argv.slice(2))
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
    process.exit(1);
  });
