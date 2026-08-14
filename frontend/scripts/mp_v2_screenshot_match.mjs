/**
 * Capture member-platform routes for visual reference matching.
 * Usage: npx playwright test scripts/mp_v2_screenshot_match.mjs --config=...
 * Or: node with playwright chromium directly.
 */
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../design_reference/screenshots");
const base = process.env.MP_BASE_URL || "http://localhost:5173";

const routes = [
  { route: "/", file: "01_public_home", size: { width: 1491, height: 1055 } },
  { route: "/login", file: "02_login", size: { width: 1440, height: 900 } },
  { route: "/register", file: "03_register", size: { width: 1440, height: 900 } },
  { route: "/app", file: "04_dashboard", size: { width: 1491, height: 1055 }, auth: true },
  { route: "/app/markets", file: "05_markets", size: { width: 1491, height: 1055 }, auth: true },
  { route: "/app/watchlist", file: "06_watchlist", size: { width: 1491, height: 1055 }, auth: true },
  { route: "/app/alerts", file: "07_alerts", size: { width: 1491, height: 1055 }, auth: true },
  { route: "/app/market/ETH", file: "08_asset_detail_eth", size: { width: 1491, height: 1055 }, auth: true },
  { route: "/app/membership", file: "09_membership", size: { width: 1491, height: 1055 }, auth: true },
  { route: "/app/account", file: "10_account", size: { width: 1491, height: 1055 }, auth: true },
];

async function ensureAuth(page) {
  await page.goto(`${base}/login`, { waitUntil: "networkidle" });
  await page.fill("#email", "founder@nexus.local");
  await page.fill("#password", "demo");
  await page.click('button[type="submit"]');
  await page.waitForURL("**/app**", { timeout: 15000 });
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  let authed = false;
  for (const item of routes) {
    await page.setViewportSize(item.size);
    if (item.auth && !authed) {
      await ensureAuth(page);
      authed = true;
    }
    await page.goto(`${base}${item.route}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);
    const out = path.join(outDir, `${item.file}.png`);
    await page.screenshot({ path: out, fullPage: false });
    console.log("SHOT", item.route, "->", out);
  }

  await browser.close();
  console.log("DONE", outDir);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
