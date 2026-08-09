/**
 * V18.2.22 founder visual review support — max 5 REMOTE screenshots.
 * Local captures are not acceptance.
 */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const OUT = path.resolve("D:/NEXUS_RUNTIME/evidence_coordinator/v18_2_22_acceptance");
const MARKER = "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD";
const REMOTE = "https://nexus-member-preview-v18-2-1.zeabur.app";

fs.mkdirSync(OUT, { recursive: true });

async function markerOk(base) {
  try {
    const health = await fetch(`${base}/api/nexus/ui-build`).catch(() => null);
    if (health && health.ok) {
      const j = await health.json();
      if (String(j.build_marker || j.buildMarker || "").includes("V18_2_22")) return true;
    }
    const res = await fetch(`${base}/`);
    const html = await res.text();
    const m = html.match(/\/assets\/(index-[^"]+\.js)/);
    if (!m) return false;
    const js = await (await fetch(`${base}/assets/${m[1]}`)).text();
    return js.includes(MARKER);
  } catch {
    return false;
  }
}

async function shot(page, name, w, h, route) {
  await page.setViewportSize({ width: w, height: h });
  await page.goto(route, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForTimeout(2800);
  const file = path.join(OUT, name);
  await page.screenshot({ path: file, fullPage: false });
  console.log("wrote", file);
}

async function main() {
  const useRemote = await markerOk(REMOTE);
  const base = useRemote ? REMOTE : REMOTE;
  console.log("base", base, "remote_marker_v22", useRemote);

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await shot(page, "overview_desktop_1440x900.png", 1440, 900, `${base}/overview`);
    await shot(page, "market_terminal_desktop_1440x900.png", 1440, 900, `${base}/market/BTCUSDT`);
    await shot(page, "radar_scanner_desktop_1440x900.png", 1440, 900, `${base}/scanner`);
    await shot(page, "overview_mobile_390x844.png", 390, 844, `${base}/overview`);
    await shot(page, "market_terminal_mobile_390x844.png", 390, 844, `${base}/market/BTCUSDT`);
  } finally {
    await browser.close();
  }
  const files = fs.readdirSync(OUT).filter((f) => f.endsWith(".png"));
  console.log(
    JSON.stringify({
      out: OUT,
      count: files.length,
      files,
      remote_marker_v22: useRemote,
      local_not_acceptance: true,
      status: useRemote ? "READY_FOR_FOUNDER_VISUAL_REVIEW" : "READY_FOR_FOUNDER_VISUAL_REVIEW_PENDING_REMOTE_MARKER",
    }),
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
