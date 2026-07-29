import { defineConfig } from "@playwright/test";

import { identityNames } from "./tests/e2e/identity";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "foundation-errors.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  forbidOnly: true,
  retries: 0,
  reporter: "line",
  outputDir: "/tmp/kaj-playwright-test-results",
  use: {
    baseURL: "http://127.0.0.1:8766",
  },
  projects: identityNames.map((identity) => ({
    name: identity,
    metadata: { identity },
  })),
  webServer: {
    command: "./scripts/e2e-server",
    url: "http://127.0.0.1:8766/ready/",
    timeout: 30_000,
    reuseExistingServer: false,
  },
});
