/**
 * V18.2.15 contract checks — radar eligibility, score semantics, markers.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "..", "src");

const rankingSrc = fs.readFileSync(path.join(SRC, "market", "liveMarketRanking.ts"), "utf8");
assert.ok(rankingSrc.includes("RADAR_ELIGIBILITY_CONTRACT_V1"), "radar contract missing");
assert.ok(rankingSrc.includes("FIXED_SYMBOL_DEPENDENCY_COUNT = 0"), "fixed dependency must be 0");
assert.ok(rankingSrc.includes("nex_rank_score_v1"), "score version missing");
assert.ok(rankingSrc.includes("NEX_RANK_RAW_MIN"), "normalization bounds missing");
assert.ok(rankingSrc.includes("RANK_HYSTERESIS_SCORE"), "hysteresis missing");
assert.ok(rankingSrc.includes("isRadarEligible"), "isRadarEligible missing");
assert.ok(rankingSrc.includes("isTradeEligible"), "isTradeEligible missing");
assert.ok(rankingSrc.includes("closest_watch"), "closest_watch missing");
assert.ok(!/isRadarStage[\s\S]*INSUFFICIENT_DATA/.test(rankingSrc), "INSUFFICIENT_DATA must not be radar-eligible via isRadarStage");
assert.ok(
  /function isRadarEligible[\s\S]*INSUFFICIENT_DATA[\s\S]*return false/.test(rankingSrc),
  "INSUFFICIENT_DATA must be excluded from radar",
);
assert.ok(
  /function isRadarEligible[\s\S]*EXPIRED[\s\S]*return false/.test(rankingSrc),
  "EXPIRED must be excluded from radar",
);

const overview = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OverviewPageV2.tsx"), "utf8");
assert.ok(overview.includes("目前沒有") || overview.includes("沒有市場滿足"), "empty radar copy");
assert.ok(overview.includes("APPROACHING RADAR") || overview.includes("Closest Watch"), "closest watch label");
assert.ok(overview.includes("MARKET PULSE"), "market pulse section");
assert.ok(!overview.includes("????"), "mojibake question marks in overview");
assert.ok([...overview].some((c) => c >= "\u4e00" && c <= "\u9fff"), "overview must contain CJK");

const terminal = fs.readFileSync(path.join(SRC, "product_v2", "pages", "MarketTerminalPageV2.tsx"), "utf8");
assert.ok(terminal.includes("WHY NOW"), "WHY NOW");
assert.ok(terminal.includes("AGAINST") || terminal.includes("CONTRADICTING"), "AGAINST/CONTRADICTING");
assert.ok(terminal.includes("INVALIDATION"), "INVALIDATION");
assert.ok(terminal.includes("SUPPORTING") || terminal.includes("WHY NOW"), "WHY NOW/SUPPORTING");

const buildInfo = fs.readFileSync(path.join(SRC, "demo", "buildInfo.ts"), "utf8");
assert.ok(
  buildInfo.includes("PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD") ||
    buildInfo.includes("PUBLIC_V18_2_19_VISUAL_ANALYTICS_HEAD") ||
    buildInfo.includes("PUBLIC_V18_2_18_PAID_PRODUCT_VISUAL_HEAD"),
  "marker",
);

const app = fs.readFileSync(path.join(SRC, "app", "NexusMemberProductV2.tsx"), "utf8");
assert.ok(
  app.includes("PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD") ||
    app.includes("PUBLIC_V18_2_19_VISUAL_ANALYTICS_HEAD") ||
    app.includes("PUBLIC_V18_2_18_PAID_PRODUCT_VISUAL_HEAD"),
  "app marker",
);
assert.ok(
  app.includes('data-member-surface="v18_2_22"') ||
    app.includes('data-member-surface="v18_2_19"') ||
    app.includes('data-member-surface="v18_2_18"'),
  "surface marker",
);

const css = fs.readFileSync(path.join(SRC, "styles", "global.css"), "utf8");
assert.ok(css.length > 0, "global.css utf-8 readable");

console.log("PASS: v18.2.15 compatibility gate (marker bumped to v18.2.18)");
