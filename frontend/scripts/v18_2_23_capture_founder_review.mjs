/**
 * V18.2.23 founder visual review support — max 5 REMOTE screenshots.
 * Local captures are not acceptance. No visual redesign.
 */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const OUT = path.resolve("D:/NEXUS_RUNTIME/evidence_coordinator/v18_2_23_acceptance");
const EXPECTED_MARKER = "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD";
const REMOTE = "https://nexus-member-preview-v18-2-1.zeabur.app";

fs.mkdirSync(OUT, { recursive: true });

async function remoteProbe() {
  const ui = await (await fetch(`${REMOTE}/api/nexus/ui-build`)).json();
  const foundation = await (await fetch(`${REMOTE}/api/nexus/public/closed-beta/foundation`)).json();
  const marker =
    String(ui.build_marker || ui.buildMarker || "") === EXPECTED_MARKER &&
    String(foundation.marker || "") === EXPECTED_MARKER;
  return {
    marker_ok: marker,
    ui_marker: ui.build_marker || ui.buildMarker,
    foundation_marker: foundation.marker,
    visual_status: foundation.visual_status,
    assets: ui.sync_meta?.current_assets || [],
  };
}

async function shot(page, name, w, h, route) {
  await page.setViewportSize({ width: w, height: h });
  await page.goto(route, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForTimeout(2800);
  const file = path.join(OUT, name);
  await page.screenshot({ path: file, fullPage: false });
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      overflowX: doc.scrollWidth > doc.clientWidth + 2,
    };
  });
  const bodyText = (await page.locator("body").innerText()).slice(0, 400);
  console.log("wrote", file, JSON.stringify(overflow));
  return { name, overflow, body_preview: bodyText.replace(/\s+/g, " ").slice(0, 160) };
}

async function main() {
  const probe = await remoteProbe();
  console.log("probe", JSON.stringify(probe));
  if (!probe.marker_ok) {
    console.error("REMOTE_MARKER_MISMATCH");
    process.exit(2);
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const findings = [];
  try {
    findings.push(await shot(page, "overview_desktop_1440x900.png", 1440, 900, `${REMOTE}/overview`));
    findings.push(
      await shot(page, "market_terminal_desktop_1440x900.png", 1440, 900, `${REMOTE}/market/BTCUSDT`),
    );
    findings.push(await shot(page, "radar_scanner_desktop_1440x900.png", 1440, 900, `${REMOTE}/scanner`));
    findings.push(await shot(page, "overview_mobile_390x844.png", 390, 844, `${REMOTE}/overview`));
    findings.push(
      await shot(page, "market_terminal_mobile_390x844.png", 390, 844, `${REMOTE}/market/BTCUSDT`),
    );
  } finally {
    await browser.close();
  }

  const files = fs.readdirSync(OUT).filter((f) => f.endsWith(".png"));
  const summary = {
    out: OUT,
    count: files.length,
    files,
    remote: true,
    local_not_acceptance: true,
    marker: EXPECTED_MARKER,
    probe,
    overflow_any: findings.some((f) => f.overflow?.overflowX),
    findings,
    status: "READY_FOR_FOUNDER_VISUAL_REVIEW",
  };
  fs.writeFileSync(path.join(OUT, "capture_meta.json"), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
