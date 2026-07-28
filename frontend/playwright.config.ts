import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
    screenshot: "off",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    cwd: __dirname,
    env: {
      ...process.env,
      AUTONOMOUS_SEND: "false",
      EXCHANGE_WRITE: "false",
      MAINNET: "false",
      REAL_MONEY: "false",
      ARM: "false",
      FIXED_LEVERAGE: "25",
      AI_CAN_CHANGE_LEVERAGE: "false",
      EXPLICIT_FIXTURE_MODE: "false",
      NEXUS_ZEABUR_CLEAN_OBSERVER: "false",
    },
  },
  outputDir: path.join(repoRoot, "artifacts", "wave4", "playwright-output"),
});
