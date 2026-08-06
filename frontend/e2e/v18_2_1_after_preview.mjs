#!/usr/bin/env node
/** After preview — local flag-on screenshots (not in git). */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const BASE = process.env.NEXUS_PREVIEW_BASE || "http://127.0.0.1:4173";
const OUT = path.resolve(
  "D:/NEXUS_RUNTIME/evidence_coordinator/v18_2_1_actual_panel/after",
);
const Q = "?member_surface_v18_2_1=1";
const ROUTES = ["/overview", "/opportunities", "/alerts", "/scanner"];

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const route of ROUTES) {
    await page.goto(`${BASE}${route}${Q}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    const file = path.join(OUT, `${route.replace(/\//g, "_") || "root"}_1440x900.png`);
    await page.screenshot({ path: file, fullPage: true });
  }
  await browser.close();
  console.log("after_preview_dir", OUT);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
