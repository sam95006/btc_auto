/**
 * Focused V18.2.14 ranking contract checks (no vitest).
 * Ensures fixed_symbol_dependency_count=0 and deterministic nex_rank_score_v1.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "..", "src");

const rankingSrc = fs.readFileSync(path.join(SRC, "market", "liveMarketRanking.ts"), "utf8");
assert.ok(rankingSrc.includes("FIXED_SYMBOL_DEPENDENCY_COUNT = 0"), "fixed dependency must be 0");
assert.ok(rankingSrc.includes("nex_rank_score_v1"), "score version missing");
assert.ok(rankingSrc.includes("rank_event"), "rank_event contract missing");
assert.ok(!/FIXED_SYMBOLS\s*=\s*\[\s*["']BTC/.test(rankingSrc), "must not hardcode BTC ranking universe");

const terminal = fs.readFileSync(path.join(SRC, "product_v2", "pages", "MarketTerminalPageV2.tsx"), "utf8");
assert.ok(terminal.includes("fetchScannerSymbol"), "terminal must reuse fetchScannerSymbol");
assert.ok(terminal.includes("NexusLiveCandleChart"), "terminal must reuse chart");
assert.ok(!terminal.includes("nx-score-bars"), "must not reuse old nx page composition");

const app = fs.readFileSync(path.join(SRC, "app", "NexusMemberProductV2.tsx"), "utf8");
assert.ok(app.includes("MarketTerminalPageV2"), "route terminal v2");
assert.ok(!app.includes('from "../pages/MarketSymbolPage"'), "old symbol page must not be routed in Product V2");
assert.ok(app.includes("MarketPulseBar"), "pulse bar required");
const footer = app.slice(app.indexOf("<footer"));
assert.ok(!footer.includes("buildMarker") && !footer.includes("generation"), "footer must not show build marker/generation");

const opp = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OpportunitiesPageV2.tsx"), "utf8");
assert.ok(!/>\s*L1\s*</.test(opp) && !/>\s*L2\s*</.test(opp) && !/>\s*L3\s*</.test(opp), "L1/L2/L3 must be removed");
assert.ok(opp.includes("探索"), "discover label");

const nav = fs.readFileSync(path.join(SRC, "product_v2", "ProductV2TopNav.tsx"), "utf8");
assert.ok(nav.includes('"探索"'), "nav 探索");
assert.ok(!/>狀態</.test(nav), "no prominent 狀態 text button");
assert.ok(!/>帳戶</.test(nav), "no prominent 帳戶 text button");

console.log("PASS: v18.2.14 live ranking + terminal contract checks");
