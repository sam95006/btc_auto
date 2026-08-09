/**
 * V18.2.16 contract checks — server-side Full-Market Live Radar.
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

const hook = fs.readFileSync(path.join(SRC, "product_v2", "useLiveMarketRanking.ts"), "utf8");
assert.ok(hook.includes("fetchPublicRadar"), "must fetch server radar");
assert.ok(hook.includes('rank_authority: "SERVER"'), "SERVER authority");
assert.ok(hook.includes("frontend_local_rank_authority: false"), "no local rank authority");
assert.ok(!hook.includes("fetchScannerCandidates"), "must not fetch scanner candidates for rank");
assert.ok(!hook.includes("buildLiveRanking"), "must not build ranks in browser");
assert.ok(!hook.includes("persist: true"), "must not persist localStorage ranks");

const api = fs.readFileSync(path.join(SRC, "market", "publicRadarApi.ts"), "utf8");
assert.ok(api.includes("/api/nexus/public/radar"), "public radar path");

const overview = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OverviewPageV2.tsx"), "utf8");
assert.ok(overview.includes("data-rank-authority"), "rank authority attr");
assert.ok(overview.includes("evaluated-count"), "evaluated count");
assert.ok(overview.includes("monitored-count"), "monitored count");
assert.ok([...overview].some((c) => c >= "\u4e00" && c <= "\u9fff"), "overview must contain CJK");

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

console.log("PASS: v18.2.16 server-side full-market live radar checks (marker bumped to v18.2.18)");
