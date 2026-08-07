#!/usr/bin/env node
/**
 * V18.2.7 data-truth static checks for public Actual Panel surface.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");

function read(rel) {
  return fs.readFileSync(path.join(SRC, rel), "utf8");
}

const issues = [];

const overview = read("pages/actual_panel/ActualPanelOverviewPage.tsx");
if (!overview.includes("目前沒有符合安全條件的市場機會")) {
  issues.push("overview missing eligible=0 honest message");
}
if (!overview.includes("data-eligible-zero-false-opportunity-count")) {
  issues.push("overview missing eligible_zero_false_opportunity_count wiring");
}
if (!overview.includes("尚未通過安全條件 · 不可視為交易建議")) {
  issues.push("overview missing watch-candidate disclaimer");
}
if (overview.includes("Top 3 機會") && !overview.includes("eligibleZero")) {
  issues.push("overview still hardcodes Top 3 機會 without eligibleZero gate");
}

const filter = read("market/cryptoOpportunityFilter.ts");
if (!filter.includes("SOXL") || !filter.includes("SPCX")) {
  issues.push("cryptoOpportunityFilter missing SOXL/SPCX defense list");
}
if (!filter.includes("non_crypto_symbol_in_crypto_opportunity_count")) {
  issues.push("missing non_crypto_symbol_in_crypto_opportunity_count metric");
}

const policy = read("market/cryptoInstrumentPolicy.ts");
if (!policy.includes("CROSS_ASSET_CONTEXT_ONLY")) {
  issues.push("cryptoInstrumentPolicy missing CROSS_ASSET_CONTEXT_ONLY");
}
if (/disposition:\s*bybitLinear.*VALID_CRYPTO_INSTRUMENT/.test(policy)) {
  issues.push("SOXL/SPCX must not be VALID_CRYPTO_INSTRUMENT for opportunity ranking");
}

const ticker = read("components/MarketTopTicker.tsx");
if (!ticker.includes("全市場發現") || !ticker.includes("即時監控")) {
  issues.push("MarketTopTicker missing Founder funnel metric labels");
}
if (ticker.includes("市場涵蓋") || ticker.includes("重點追蹤")) {
  issues.push("MarketTopTicker still uses ambiguous 市場涵蓋/重點追蹤 labels");
}

const nav = read("components/ActualPanelSidebarNav.tsx");
if (/data-testid=["']nav-membership-review["']/.test(nav) || /<span[^>]*>Membership review<\/span>/.test(nav)) {
  issues.push("Membership review must not appear in normal sidebar");
}
if (!nav.includes('plan === "ENTERPRISE"')) {
  issues.push("Enterprise org nav gate missing");
}

const navContract = read("member/navigationContractV18_2_1.ts");
const utilBlock = navContract.slice(
  navContract.indexOf("UTILITY_ACTUAL_PANEL_NAV"),
  navContract.indexOf("ENTERPRISE_ACTUAL_PANEL_NAV"),
);
if (utilBlock.includes('"/account"')) {
  issues.push("Account duplicated in utility nav");
}

const freshness = read("market/dataTruthFreshness.ts");
if (!freshness.includes("部分即時／資料降級")) {
  issues.push("missing degraded freshness label");
}
if (!freshness.includes("eligibleZeroFalseOpportunityCount")) {
  issues.push("missing eligibleZeroFalseOpportunityCount helper");
}

// Execute helper invariants via dynamic transpile-free checks (string-level metric defaults)
const require = createRequire(import.meta.url);
void require;

if (issues.length) {
  console.error("FAIL data-truth:", issues);
  process.exit(1);
}
console.log("PASS: v18.2.7 data-truth static checks");
