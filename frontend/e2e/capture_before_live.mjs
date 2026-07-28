#!/usr/bin/env node
/**
 * Wave 4.1 — capture LIVE read-only baseline from Zeabur (GET only, no trading).
 * Writes overview_pro + scanner PNGs to artifacts/wave4/before/
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
function routeSlug(route) {
  const trimmed = route.replace(/^\//, "").replace(/\/$/, "");
  if (!trimmed) return "root";
  return trimmed.replace(/\//g, "_").replace(/:/g, "");
}

function screenshotPath(baseDir, route, state, width, height) {
  const file = `${routeSlug(route)}_${state}_${width}x${height}.png`;
  return path.join(baseDir, file);
}

function writeVisualManifest(baseDir, entries) {
  const manifestPath = path.join(baseDir, "manifest.json");
  fs.writeFileSync(
    manifestPath,
    JSON.stringify(
      {
        schema_version: "wave4_visual_capture_manifest_v1",
        capturedAt: new Date().toISOString(),
        entries,
      },
      null,
      2,
    ),
    "utf-8",
  );
}

const LIVE_BASE = "https://nexus-stage3-bybit-demo-learning.zeabur.app";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(__dirname, "../../artifacts/wave4/before");

const TARGETS = [
  { route: "/overview", state: "overview_pro", width: 1440, height: 900 },
  { route: "/scanner", state: "scanner", width: 1440, height: 900 },
];

async function main() {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const entries = [];

  for (const target of TARGETS) {
    await page.setViewportSize({ width: target.width, height: target.height });
    const url = `${LIVE_BASE}${target.route}`;
    console.log(`GET ${url}`);
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90_000 });
    await page.waitForTimeout(3000);
    const filePath = screenshotPath(
      outputDir,
      target.route,
      target.state,
      target.width,
      target.height,
    );
    await page.screenshot({ path: filePath, fullPage: true });
    entries.push({
      file: path.basename(filePath),
      route: target.route,
      state: target.state,
      viewport: `${target.width}x${target.height}`,
      capturedAt: new Date().toISOString(),
      source: LIVE_BASE,
    });
    console.log(`wrote ${filePath}`);
  }

  writeVisualManifest(outputDir, entries);
  await browser.close();
  console.log("capture_before_live=PASS");
}

main().catch((err) => {
  console.error("capture_before_live=FAIL", err);
  process.exit(1);
});
