#!/usr/bin/env node
/** V18.2.2 visual evidence — disk only, not committed. */
import fs from "node:fs";
import path from "node:path";
import { chromium, devices } from "@playwright/test";

const BASE = process.env.NEXUS_PREVIEW_BASE || "http://127.0.0.1:4173";
const OUT = path.resolve("D:/NEXUS_RUNTIME/evidence_coordinator/v18_2_2_remote_preview");
const MANIFEST = path.join(OUT, "manifest.json");
const BEFORE_AFTER = path.join(OUT, "before_after_index.json");
const SMOKE = path.join(OUT, "remote_preview_smoke.json");

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: devices["iPad (gen 7)"].viewport,
  mobile: devices["iPhone 13"].viewport,
};

const SCENARIOS = [
  { id: "01_review_default", url: "/preview/v18_2_1/review", action: null },
  { id: "02_review_visitor", url: "/review?member_surface_v18_2_1=1", action: "plan:VISITOR" },
  { id: "03_review_free", url: "/review?member_surface_v18_2_1=1", action: "plan:FREE" },
  { id: "04_review_pro", url: "/review?member_surface_v18_2_1=1", action: "plan:PRO" },
  { id: "05_review_research", url: "/review?member_surface_v18_2_1=1", action: "plan:RESEARCH" },
  { id: "06_review_enterprise", url: "/review?member_surface_v18_2_1=1", action: "plan:ENTERPRISE" },
  { id: "07_review_expert_mode", url: "/review?member_surface_v18_2_1=1", action: "mode:EXPERT" },
  { id: "08_opportunities_nav_link", url: "/opportunities?member_surface_v18_2_1=1", action: "nav:review" },
  { id: "09_review_route_shortcut_opp", url: "/review?member_surface_v18_2_1=1", action: "route:opportunities" },
  { id: "10_review_reset_state", url: "/review?member_surface_v18_2_1=1", action: "reset" },
];

async function runAction(page, action) {
  if (!action) return;
  if (action.startsWith("plan:")) {
    const plan = action.split(":")[1];
    await page.getByTestId(`review-plan-${plan}`).click();
    await page.waitForTimeout(400);
    return;
  }
  if (action === "mode:EXPERT") {
    await page.getByRole("button", { name: "專業模式" }).click();
    await page.waitForTimeout(400);
    return;
  }
  if (action === "nav:review") {
    const link = page.getByTestId("nav-membership-review");
    if ((await link.count()) > 0) {
      await link.click();
      await page.waitForTimeout(800);
    }
    return;
  }
  if (action.startsWith("route:")) {
    const r = action.split(":")[1];
    await page.getByTestId(`review-route-${r}`).click();
    await page.waitForTimeout(800);
    return;
  }
  if (action === "reset") {
    await page.getByTestId("review-plan-PRO").click();
    await page.getByTestId("review-reset-state").click();
    await page.waitForTimeout(400);
  }
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const manifest = [];
  const browser = await chromium.launch({ headless: true });

  for (const scenario of SCENARIOS) {
    for (const [vpName, vp] of Object.entries(VIEWPORTS)) {
      const page = await browser.newPage();
      await page.setViewportSize(vp);
      await page.goto(`${BASE}${scenario.url}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(1200);
      await runAction(page, scenario.action);
      const file = `${scenario.id}_${vpName}.png`;
      const filePath = path.join(OUT, file);
      await page.screenshot({ path: filePath, fullPage: true });
      manifest.push({
        scenario: scenario.id,
        viewport: vpName,
        url: scenario.url,
        file,
        path: filePath,
      });
      await page.close();
    }
  }

  await browser.close();

  const manifestObj = {
    generated_at: new Date().toISOString(),
    base: BASE,
    screenshot_count: manifest.length,
    entries: manifest,
  };
  fs.writeFileSync(MANIFEST, JSON.stringify(manifestObj, null, 2));
  fs.writeFileSync(
    BEFORE_AFTER,
    JSON.stringify(
      {
        before_baseline: "v18_2_1_actual_panel (no review route)",
        after_dir: OUT,
        scenarios: SCENARIOS.map((s) => s.id),
      },
      null,
      2,
    ),
  );
  fs.writeFileSync(
    SMOKE,
    JSON.stringify(
      {
        ok: manifest.length >= 30,
        local_preview_base: BASE,
        review_path: "/preview/v18_2_1/review",
        screenshot_count: manifest.length,
      },
      null,
      2,
    ),
  );
  console.log("evidence_dir", OUT);
  console.log("screenshot_count", manifest.length);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
