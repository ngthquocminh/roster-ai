import { defineConfig, devices } from "@playwright/test";

const origin = process.env.LIVE_CONVERSATION_ORIGIN;
if (!origin || !/^http:\/\/localhost:\d+$/.test(origin)) {
  throw new Error("LIVE_CONVERSATION_ORIGIN must name the disposable local stack");
}
const budget = Number(process.env.LIVE_CONVERSATION_BROWSER_BUDGET_USD);
if (!Number.isFinite(budget) || budget <= 0 || budget > 7) {
  throw new Error("A positive browser allowance within the total story budget is required");
}

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/live-conversations.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 600_000,
  expect: { timeout: 15_000 },
  reporter: "list",
  outputDir: `../_bmad-output/test-artifacts/browser-live-5-7-${Date.now()}`,
  use: { baseURL: origin, trace: "off", screenshot: "only-on-failure" },
  projects: [{ name: "live-chromium", use: { ...devices["Desktop Chrome"] } }],
});
