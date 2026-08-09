/**
 * V18.2.19 — visual analytics market terminal checks.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "..", "src");
const ROOT = path.resolve(__dirname, "..", "..");

const marker = "PUBLIC_V18_2_20_PAID_BETA_RETENTION_HEAD";
const legacyMarkers = [
  marker,
  "PUBLIC_V18_2_19_VISUAL_ANALYTICS_HEAD",
  "PUBLIC_V18_2_18_PAID_PRODUCT_VISUAL_HEAD",
];

const buildInfo = fs.readFileSync(path.join(SRC, "demo", "buildInfo.ts"), "utf8");
assert.ok(legacyMarkers.some((m) => buildInfo.includes(m)), "buildInfo marker");

const app = fs.readFileSync(path.join(SRC, "app", "NexusMemberProductV2.tsx"), "utf8");
assert.ok(legacyMarkers.some((m) => app.includes(m)), "app marker");
assert.ok(
  app.includes('data-member-surface="v18_2_20"') ||
    app.includes('data-member-surface="v18_2_19"') ||
    app.includes('data-member-surface="v18_2_18"'),
  "surface marker",
);

const overview = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OverviewPageV2.tsx"), "utf8");
assert.ok(overview.includes("MarketStateVisual"), "market state visual");
assert.ok(overview.includes("MarketMapHeat"), "market map");
assert.ok(overview.includes("data-fabricated-visual-count"), "fabricated flag");
assert.ok(overview.includes("data-market-state-visual"), "state visual flag");
assert.ok(overview.includes("FundingScale"), "funding scale");
assert.ok(overview.includes("RankStepSpark"), "rank step spark");
assert.ok(overview.includes("APPROACHING RADAR"), "approaching radar");
assert.ok(overview.includes("MARKET MAP"), "market map label");
assert.ok(!overview.includes("mp2-now-tile"), "no number-card tiles");
assert.ok([...overview].some((c) => c >= "\u4e00" && c <= "\u9fff"), "overview CJK");

const state = fs.readFileSync(path.join(SRC, "product_v2", "MarketStateVisual.tsx"), "utf8");
assert.ok(state.includes("Opportunity Pipeline"), "pipeline");
assert.ok(state.includes("Radar") && state.includes("Trade"), "radar trade disclaimer");
assert.ok(state.includes("NO DATA"), "no data labels");
assert.ok(state.includes('data-fabricated-visual-count="0"'), "fabricated 0");

const spark = fs.readFileSync(path.join(SRC, "product_v2", "MetricSpark.tsx"), "utf8");
assert.ok(spark.includes("RiskGauge"), "risk gauge");
assert.ok(spark.includes("PipelineBars"), "pipeline bars");
assert.ok(spark.includes("FundingScale"), "funding scale");
assert.ok(spark.includes("RankStepSpark"), "rank step");

const histApi = fs.readFileSync(path.join(SRC, "market", "marketSummaryHistory.ts"), "utf8");
assert.ok(histApi.includes("/api/nexus/public/market-summary/history"), "history endpoint");

const backendHist = fs.readFileSync(
  path.join(ROOT, "backend", "market", "live_radar", "market_summary_history.py"),
  "utf8",
);
assert.ok(backendHist.includes("MARKET_SUMMARY_HISTORY_V1"), "history contract");
assert.ok(backendHist.includes("fabricated_visual_count"), "fabricated count field");

const routes = fs.readFileSync(path.join(ROOT, "backend", "api", "public_radar_routes.py"), "utf8");
assert.ok(routes.includes("market-summary/history"), "history route");

const css = fs.readFileSync(path.join(SRC, "styles", "v18211MemberProductV2.css"), "utf8");
assert.ok(css.includes("#0d1117") || css.includes("#0D1117"), "canvas bg");
assert.ok(css.includes("#12d18a") || css.includes("#12D18A"), "stronger pos");
assert.ok(css.includes("#ff4d6a") || css.includes("#FF4D6A"), "stronger neg");
assert.ok(css.includes("17fr") && css.includes("57fr") && css.includes("26fr"), "terminal ratios");
assert.ok(css.includes("mp2-market-state"), "market state css");
assert.ok(css.includes("mp2-map-grid"), "map grid css");

const terminal = fs.readFileSync(path.join(SRC, "product_v2", "pages", "MarketTerminalPageV2.tsx"), "utf8");
assert.ok(terminal.includes("WHY NOW"), "WHY NOW");
assert.ok(terminal.includes("RankStepSpark"), "terminal rank step");
assert.ok(terminal.includes("ranking.events"), "server rank events");

console.log("PASS: v18.2.19 visual analytics market terminal");
