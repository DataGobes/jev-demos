import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    { command: "cd .. && uv run python -m jevviz.data e2e.duckdb && env -u TYPESAFE_API_KEY JEVVIZ_DB=e2e.duckdb DOTENV_DISABLE=1 uv run uvicorn jevviz.api:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/health", reuseExistingServer: false, timeout: 60_000 },
    { command: "npm run dev", url: "http://localhost:5173", reuseExistingServer: false },
  ],
});
