const { createApp } = require("./app");
const { closeMongoClient } = require("./db/mongoClient");

const port = Number(process.env.API_PORT) || 3000;

const requiredEnvironmentVariables = ["MONGO_URI", "JWT_SECRET"];
const missingEnvironmentVariables = requiredEnvironmentVariables.filter(
  (environmentVariable) => !process.env[environmentVariable]
);

if (missingEnvironmentVariables.length > 0) {
  throw new Error(
    `Missing required environment variables: ${missingEnvironmentVariables.join(", ")}`
  );
}

const app = createApp();

app.listen(port, "0.0.0.0", () => {
  console.log(`[api] listening on port ${port}`);
});

async function shutdownGracefully() {
  const shutdownTimeout = setTimeout(() => {
    console.error("[api] shutdown timeout reached; forcing process exit");
    process.exit(1);
  }, 5_000);
  shutdownTimeout.unref();

  await closeMongoClient();
  clearTimeout(shutdownTimeout);
  process.exit(0);
}

process.on("SIGINT", shutdownGracefully);
process.on("SIGTERM", shutdownGracefully);
