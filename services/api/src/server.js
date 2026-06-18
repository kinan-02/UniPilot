const { createApp } = require("./app");

const port = Number(process.env.API_PORT) || 3000;
const app = createApp();

app.listen(port, "0.0.0.0", () => {
  console.log(`[api] listening on port ${port}`);
});
