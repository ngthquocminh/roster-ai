import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    // Must match the webServer URL below. The preview server binds 127.0.0.1 only, so navigating
    // via "localhost" would resolve ::1 first on Windows and pay the same IPv6 probe the webServer
    // URL was changed to avoid.
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  webServer: {
    // Start Vite directly so Playwright can terminate the server process without leaving an
    // npm/cmd.exe/Vite chain behind on Windows. The test:e2e script builds before this server is
    // started, and the IPv4 URL avoids localhost's IPv6 probe delay when Vite binds IPv4.
    command: "node node_modules/vite/bin/vite.js preview --host 127.0.0.1",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGINT", timeout: 5_000 },
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
