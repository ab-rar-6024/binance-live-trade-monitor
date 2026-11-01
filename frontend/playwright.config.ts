import { defineConfig } from "@playwright/test";

// The tests drive a real browser against the Vite dev server with the backend mocked (see e2e/mock.ts),
// so they need neither Kafka nor Spark. They use the Edge/Chrome already installed on the machine.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: process.env.E2E_BROWSER ?? "msedge", // set E2E_BROWSER=chrome to use Chrome
    headless: true,
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
