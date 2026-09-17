import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const stateFile = path.join(here, "e2e", ".auth-state.json");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  // CI 上重试一次：后端冷启动/首查抖动偶发 serial 链中断；本地保持 0 快速失败
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: "http://127.0.0.1:5273",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5273",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: stateFile,
      },
      dependencies: ["setup"],
    },
  ],
});
