#!/usr/bin/env node
/** V18.2.1 STEP A — baseline screenshots (deployed panel, not in git). */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const LIVE_BASE =
  process.env.NEXUS_PANEL_BASE_URL || "https://nexus-bybit-demo-val.zeabur.app";
const OUT = path.resolve(
  "D:/NEXUS_RUNTIME/evidence_coordinator/v18_2_1_actual_panel",
);
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 },
  { width: 430, height: 932 },
  { width: 390, height: 844 },
];
const ROUTES = [
  "/overview",
  "/opportunities",
  "/anomalies",
  "/alerts",
  "/intelligence",
  "/market/BTCUSDT",
  "/market/ETHUSDT",
  "/market/SOLUSDT",
  "/account",
  "/notification-settings",
  "/founder/runtime",
];

function slug(route) {
  const t = route.replace(/^\//, "").replace(/\/$/, "") || "root";
  return t.replace(/\//g, "_");
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const inventory = [];
  const overflowNotes = [];
  let a11yFails = 0;

  for (const route of ROUTES) {
    for (const vp of VIEWPORTS) {
      const page = await browser.newPage();
      await page.setViewportSize(vp);
      const url = `${LIVE_BASE}${route}`;
      let status = "ok";
      try {
        const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120_000 });
        if (resp && resp.status() >= 400) status = `http_${resp.status()}`;
        await page.waitForTimeout(2500);
        const hasHScroll = await page.evaluate(
          () => document.documentElement.scrollWidth > window.innerWidth + 8,
        );
        if (hasHScroll) {
          overflowNotes.push({ route, viewport: `${vp.width}x${vp.height}` });
        }
      } catch (e) {
        status = `error:${String(e.message || e).slice(0, 80)}`;
      }
      const file = `${slug(route)}_${vp.width}x${vp.height}.png`;
      const filePath = path.join(OUT, file);
      await page.screenshot({ path: filePath, fullPage: true }).catch(() => {});
      inventory.push({
        route,
        viewport: `${vp.width}x${vp.height}`,
        screenshot: filePath,
        source: LIVE_BASE,
        capture_status: status,
        title: await page.title().catch(() => ""),
      });
      await page.close();
    }
  }

  const audit = {
    schema: "v18_2_1_panel_baseline_audit_v1",
    captured_at: new Date().toISOString(),
    deployed_base_url: LIVE_BASE,
    actual_routes_audited: ROUTES.length,
    viewports: VIEWPORTS.length,
    screenshot_count: inventory.length,
    horizontal_overflow_cases: overflowNotes.length,
    overflow_notes: overflowNotes,
    a11y_fails: a11yFails,
    routes: inventory,
  };
  const auditPath = path.resolve(
    "D:/NEXUS_RUNTIME/evidence_coordinator/v18_2_1_panel_baseline_audit.json",
  );
  fs.writeFileSync(auditPath, JSON.stringify(audit, null, 2), "utf-8");
  await browser.close();
  console.log("baseline_audit", auditPath);
  console.log("screenshots_dir", OUT);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
