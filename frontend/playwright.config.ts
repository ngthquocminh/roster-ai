import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:4173",
    trace: "retain-on-failure",
  },
  webServer: {
    // Playwright spawns this via a shell already (cmd.exe on Windows, /bin/sh elsewhere) — an
    // explicit "cmd /c" wrapper is not just redundant, it breaks the command on non-Windows hosts.
    command: "npm run build && npm run preview -- --host 127.0.0.1",
    url: "http://localhost:4173",
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    {
      name: "msedge",
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
  ],
});
