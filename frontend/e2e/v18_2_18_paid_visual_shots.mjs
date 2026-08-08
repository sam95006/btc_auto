/**
 * V18.2.18 acceptance screenshots (max 7) against local preview of built SPA.
 * Run: node e2e/v18_2_18_paid_visual_shots.mjs
 */
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";
import { spawn } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const DIST = path.join(ROOT, "dist");
const OUT = path.resolve("D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_18_acceptance");
const BASE = process.env.V18218_SHOT_BASE || "http://127.0.0.1:4178";

const shots = [
  { name: "market_home_1440x900.png", path: "/overview", w: 1440, h: 900 },
  { name: "market_terminal_btc_1440x900.png", path: "/market/BTCUSDT", w: 1440, h: 900 },
  { name: "discover_live_radar_1440x900.png", path: "/opportunities", w: 1440, h: 900 },
  { name: "scanner_1440x900.png", path: "/scanner", w: 1440, h: 900 },
  { name: "alerts_1440x900.png", path: "/alerts", w: 1440, h: 900 },
  { name: "research_1440x900.png", path: "/intelligence", w: 1440, h: 900 },
  { name: "market_terminal_btc_390x844.png", path: "/market/BTCUSDT", w: 390, h: 844 },
];

fs.mkdirSync(OUT, { recursive: true });

async function waitReady(url, ms = 60000) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    try {
      const r = await fetch(url);
      if (r.ok || r.status === 200) return;
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`preview not ready: ${url}`);
}

const preview = spawn(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["vite", "preview", "--host", "127.0.0.1", "--port", "4178", "--strictPort"],
  { cwd: ROOT, stdio: "ignore", shell: true },
);

try {
  await waitReady(`${BASE}/overview`);
  const browser = await chromium.launch({ headless: true });
  const manifest = [];
  for (const s of shots) {
    const page = await browser.newPage({ viewport: { width: s.w, height: s.h } });
    await page.goto(`${BASE}${s.path}`, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(1800);
    const filePath = path.join(OUT, s.name);
    await page.screenshot({ path: filePath, fullPage: false });
    manifest.push({ ...s, file: filePath });
    await page.close();
    console.log("shot", s.name);
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify({ count: manifest.length, shots: manifest }, null, 2));
  console.log("done", manifest.length, OUT);
} finally {
  preview.kill();
}
