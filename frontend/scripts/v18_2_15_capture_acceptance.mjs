/**
 * V18.2.15 remote acceptance: deploy wait + mojibake counters + screenshots (max 7).
 */
import { chromium } from "playwright";
import fs from "fs";

const out = "D:/NEXUS_RUNTIME/evidence_coordinator/v18_2_15_acceptance";
fs.mkdirSync(out, { recursive: true });
const base = "https://nexus-member-preview-v18-2-1.zeabur.app";
const MARKER = "PUBLIC_V18_2_15_EXCHANGE_VISUAL_TERMINAL_HEAD";

const browser = await chromium.launch({ headless: true });

function countMojibake(text) {
  const replacement = (text.match(/\uFFFD/g) || []).length;
  // Contiguous ??? often indicates corrupted CJK; ignore lone ? in English.
  const questionRuns = text.match(/\?{2,}/g) || [];
  let question_mark_corruption_count = 0;
  for (const run of questionRuns) question_mark_corruption_count += run.length;
  // Visible mojibake: replacement + common CP1252/UTF-8 mishmash glyphs in UI text
  const mishmash = (text.match(/[ÃÂåæçèéêëìíîïðñòóôõö]/g) || []).length;
  const visible_mojibake_count = replacement + mishmash;
  return { visible_mojibake_count, replacement_character_count: replacement, question_mark_corruption_count };
}

async function waitDeploy(max = 42) {
  for (let i = 0; i < max; i++) {
    const page = await browser.newPage();
    try {
      const res = await page.goto(base + "/overview", { waitUntil: "domcontentloaded", timeout: 60000 });
      const html = await page.content();
      const markerOk =
        html.includes(MARKER) || (await page.locator(`[data-build-marker="${MARKER}"]`).count()) > 0;
      const shell = (await page.locator('[data-testid="nexus-member-product-v2"]').count()) > 0;
      console.log(`attempt ${i + 1} status=${res?.status()} marker=${markerOk} shell=${shell}`);
      await page.close();
      if (markerOk && shell && res?.ok()) return true;
    } catch (e) {
      console.log(`attempt ${i + 1} err`, String(e).slice(0, 140));
      await page.close().catch(() => undefined);
    }
    await new Promise((r) => setTimeout(r, 10000));
  }
  return false;
}

const ready = await waitDeploy();
if (!ready) {
  console.error("DEPLOY_NOT_READY");
  await browser.close();
  process.exit(2);
}

async function shot(name, path, w, h) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto(base + path, { waitUntil: "networkidle", timeout: 90000 });
  await page.waitForTimeout(2800);
  const bodyText = await page.locator("body").innerText();
  const enc = countMojibake(bodyText);
  const attrs = await page.evaluate(() => {
    const root = document.querySelector('[data-testid="product-v2-overview"]');
    const shell = document.querySelector('[data-testid="nexus-member-product-v2"]');
    return {
      marker: shell?.getAttribute("data-build-marker") || null,
      radar_eligible: root?.getAttribute("data-radar-eligible"),
      scanner_visible: root?.getAttribute("data-scanner-visible"),
      trade_eligible: root?.getAttribute("data-trade-eligible"),
      fixed: root?.getAttribute("data-fixed-symbol-dependency-count"),
      generation: shell?.getAttribute("data-nexus-product-generation"),
    };
  });
  console.log("ok", name, w, h, enc, attrs.marker);
  await page.screenshot({ path: `${out}/${name}_${w}x${h}.png`, fullPage: false });
  await page.close();
  return { name, path, w, h, ...enc, attrs };
}

const results = [];
results.push(await shot("market_home", "/overview", 1440, 900));
results.push(await shot("market_terminal_btc", "/market/BTCUSDT", 1440, 900));
results.push(await shot("discover_live_radar", "/opportunities", 1440, 900));
results.push(await shot("scanner", "/scanner", 1440, 900));
results.push(await shot("alerts", "/alerts", 1440, 900));
results.push(await shot("research", "/intelligence", 1440, 900));
results.push(await shot("market_terminal_btc", "/market/BTCUSDT", 390, 844));

await browser.close();

const files = fs.readdirSync(out).filter((f) => f.endsWith(".png")).sort();
const totals = results.reduce(
  (a, r) => ({
    visible_mojibake_count: a.visible_mojibake_count + r.visible_mojibake_count,
    replacement_character_count: a.replacement_character_count + r.replacement_character_count,
    question_mark_corruption_count: a.question_mark_corruption_count + r.question_mark_corruption_count,
  }),
  { visible_mojibake_count: 0, replacement_character_count: 0, question_mark_corruption_count: 0 },
);

const home = results.find((r) => r.name === "market_home");
const summary = {
  ready: true,
  marker: MARKER,
  encoding: totals,
  home_attrs: home?.attrs || null,
  count: files.length,
  files,
  results,
};
fs.writeFileSync(`${out}/acceptance_summary.json`, JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));

if (
  totals.visible_mojibake_count !== 0 ||
  totals.replacement_character_count !== 0 ||
  totals.question_mark_corruption_count !== 0
) {
  console.error("MOJIBAKE_FAIL", totals);
  process.exit(3);
}
