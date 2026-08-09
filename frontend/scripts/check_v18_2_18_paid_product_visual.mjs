/**
 * V18.2.18 — paid product visual + true market series contract checks.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "..", "src");
const ROOT = path.resolve(__dirname, "..", "..");

const marker = "PUBLIC_V18_2_20_PAID_BETA_RETENTION_HEAD";
const markers = [
  marker,
  "PUBLIC_V18_2_19_VISUAL_ANALYTICS_HEAD",
  "PUBLIC_V18_2_18_PAID_PRODUCT_VISUAL_HEAD",
];

const buildInfo = fs.readFileSync(path.join(SRC, "demo", "buildInfo.ts"), "utf8");
assert.ok(markers.some((m) => buildInfo.includes(m)), "buildInfo marker");

const app = fs.readFileSync(path.join(SRC, "app", "NexusMemberProductV2.tsx"), "utf8");
assert.ok(markers.some((m) => app.includes(m)), "app marker");
assert.ok(
  app.includes('data-member-surface="v18_2_20"') ||
    app.includes('data-member-surface="v18_2_19"') ||
    app.includes('data-member-surface="v18_2_18"'),
  "surface marker",
);

const series = fs.readFileSync(path.join(SRC, "market", "marketSeries.ts"), "utf8");
assert.ok(series.includes("MARKET_SERIES_CONTRACT_V1"), "series contract");
assert.ok(series.includes("pulse_24h"), "pulse preset");
assert.ok(series.includes("radar_4h"), "radar preset");
assert.ok(series.includes("/api/nexus/markets/"), "series API path");

const spark = fs.readFileSync(path.join(SRC, "product_v2", "MetricSpark.tsx"), "utf8");
assert.ok(spark.includes("expectedIntervalMs"), "gap-aware spark");
assert.ok(spark.includes("timestamp"), "timestamped spark");

const pulse = fs.readFileSync(path.join(SRC, "product_v2", "MarketPulseBar.tsx"), "utf8");
assert.ok(!pulse.includes("sparkBuf"), "browser tick spark buffer removed from pulse");
assert.ok(pulse.includes("useMarketSeriesBatch"), "pulse uses true series");
assert.ok(pulse.includes("pulse_24h"), "pulse 24h series");

const overview = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OverviewPageV2.tsx"), "utf8");
assert.ok(!overview.includes("sparkBuf"), "browser tick spark buffer removed from overview");
assert.ok(overview.includes("data-browser-tick-spark=\"0\""), "browser tick flag");
assert.ok(overview.includes("data-true-market-series=\"1\""), "true series flag");
assert.ok(overview.includes("radar_4h"), "radar 4h series");
assert.ok(overview.includes("APPROACHING RADAR"), "approaching radar label");
assert.ok(overview.includes("MARKET MAP") || overview.includes("MARKET MOVERS"), "market movers/map");
assert.ok(overview.includes("TokenIcon"), "token icons");
assert.ok(overview.includes("ContextualUpgrade"), "paid value surface");
assert.ok([...overview].some((c) => c >= "\u4e00" && c <= "\u9fff"), "overview CJK");

const watch = fs.readFileSync(path.join(SRC, "product_v2", "pages", "WatchlistPageV2.tsx"), "utf8");
assert.ok(watch.includes("watchlist_24h"), "watchlist series");
assert.ok(!watch.includes("priceChange1mPct"), "no synthetic multi-pct spark");

const terminal = fs.readFileSync(path.join(SRC, "product_v2", "pages", "MarketTerminalPageV2.tsx"), "utf8");
assert.ok(terminal.includes("WHY NOW"), "WHY NOW");
assert.ok(terminal.includes("AGAINST"), "AGAINST");
assert.ok(terminal.includes("INVALIDATION"), "INVALIDATION");
assert.ok(terminal.includes("STATE"), "STATE");
assert.ok(terminal.includes("TRUST"), "TRUST");
assert.ok(terminal.includes("ContextualUpgrade"), "terminal paid surfaces");

const css = fs.readFileSync(path.join(SRC, "styles", "v18211MemberProductV2.css"), "utf8");
assert.ok(css.includes("#0d1117") || css.includes("#0D1117"), "canvas bg");
assert.ok(css.includes("#5b7cfa") || css.includes("#5B7CFA"), "nex accent");
assert.ok(
  css.includes("#20c997") ||
    css.includes("#20C997") ||
    css.includes("#12d18a") ||
    css.includes("#12D18A"),
  "pos color",
);
assert.ok(css.includes("17fr") && css.includes("57fr") && css.includes("26fr"), "terminal ratios");

const backendCharts = fs.readFileSync(
  path.join(ROOT, "backend", "market", "charts", "bybit_public_charts.py"),
  "utf8",
);
assert.ok(backendCharts.includes("MARKET_SERIES_CONTRACT_V1"), "backend series contract");
assert.ok(backendCharts.includes("bars_to_market_series"), "bars_to_market_series");
assert.ok(backendCharts.includes("invented_candles"), "no invent flag");

const routes = fs.readFileSync(path.join(ROOT, "backend", "api", "nexus_market_data_routes.py"), "utf8");
assert.ok(routes.includes("/series"), "series routes");

const caps = fs.readFileSync(path.join(SRC, "product_v2", "productCapabilities.ts"), "utf8");
assert.ok(caps.includes("FREE") && caps.includes("PRO") && caps.includes("RESEARCH"), "capability plans");

console.log("PASS: v18.2.18 paid product visual + true market series");
