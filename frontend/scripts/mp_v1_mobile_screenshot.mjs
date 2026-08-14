/**
 * Capture mobile screenshots for Member Platform Mobile V1.
 * Usage: node scripts/mp_v1_mobile_screenshot.mjs
 * Requires Vite on MP_BASE_URL (default http://localhost:5173)
 */
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../design_reference/mobile/screenshots");
const base = process.env.MP_BASE_URL || "http://localhost:5173";

const viewports = [
  { name: "390", width: 390, height: 844 },
  { name: "393", width: 393, height: 852 },
  { name: "430", width: 430, height: 932 },
];

const routes = [
  { route: "/login", file: "01_login", auth: false },
  { route: "/app", file: "02_dashboard", auth: true },
  { route: "/app/markets", file: "03_markets", auth: true },
  { route: "/app/watchlist", file: "04_watchlist", auth: true },
  { route: "/app/alerts", file: "05_alerts", auth: true },
  { route: "/app/market/ETH", file: "06_asset_detail_eth", auth: true },
  { route: "/app/membership", file: "07_membership", auth: true },
  { route: "/app/account", file: "08_account", auth: true },
];

async function ensureAuth(page) {
  await page.goto(`${base}/login`, { waitUntil: "networkidle" });
  // Mobile login: continue → password → submit; fallback desktop selectors
  const passkey = page.locator(".mpv1-m-passkey");
  if (await passkey.isVisible().catch(() => false)) {
    await passkey.click();
  } else {
    await page.fill("#email", "founder@nexus.local");
    await page.fill("#password", "demo");
    await page.click('button[type="submit"]');
  }
  await page.waitForURL("**/app**", { timeout: 20000 });
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });

  for (const vp of viewports) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
    });
    const page = await context.newPage();
    let authed = false;

    for (const item of routes) {
      if (item.auth && !authed) {
        await ensureAuth(page);
        authed = true;
      }
      await page.goto(`${base}${item.route}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(500);
      const out = path.join(outDir, `${item.file}_${vp.name}.png`);
      await page.screenshot({ path: out, fullPage: false });
      console.log("SHOT", vp.name, item.route, "->", out);
    }
    await context.close();
  }

  await browser.close();
  console.log("DONE", outDir);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
