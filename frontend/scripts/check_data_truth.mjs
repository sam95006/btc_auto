#!/usr/bin/env node
/** Active V1 member-surface data-truth checks. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "src");

function read(rel) {
  return fs.readFileSync(path.join(SRC, rel), "utf8");
}

const issues = [];

const routes = read("member_platform_v1/index.tsx");
const pages = read("member_platform_v1/pages/RealAppPages.tsx");
const shells = read("member_platform_v1/layout/Shells.tsx");
const tradingView = read("member_platform_v1/components/TradingViewTopStories.tsx");
const stagingApi = read("member_platform_v1/services/stagingApi.ts");

for (const path of ["/login", "/register", "/forgot-password", "/plans", 'path="/app"']) {
  if (!routes.includes(path)) issues.push(`active V1 route missing: ${path}`);
}
for (const classification of ["LIVE_API", "LIVE_MEMBER_DB", "LIVE_TRADINGVIEW", "STATIC_PRODUCT_CONFIG", "RUNTIME_REQUIRED", "NOT_IMPLEMENTED"]) {
  if (!(pages.includes(classification) || tradingView.includes(classification))) {
    issues.push(`active V1 classification missing: ${classification}`);
  }
}
if (!pages.includes("此功能將在 Runtime 綁定後啟用")) {
  issues.push("runtime-required copy missing");
}
if (pages.includes("NEXUS Opportunity Ranking") || pages.includes("NEXUS Signal / Risk Alerts")) {
  issues.push("runtime intelligence label presented as active");
}
if (!pages.includes("不是 NEXUS/AI 機會排行")) {
  issues.push("market-ranking source disclaimer missing");
}
if (!tradingView.includes("embed-widget-timeline.js") || !tradingView.includes('locale: "zh_TW"') || !tradingView.includes("tradingview.com/news")) {
  issues.push("official TradingView news integration incomplete");
}
if (!stagingApi.includes("nexus-api-staging.zeabur.app") || !stagingApi.includes("/api/v1")) {
  issues.push("V1 staging API origin missing");
}
const desktopSide = shells.slice(shells.indexOf("const SIDE"), shells.indexOf("const MOBILE"));
if ((desktopSide.match(/to: "\/app\/account"/g) || []).length !== 1) {
  issues.push("desktop Account navigation must have exactly one entry");
}
const desktopTopbar = shells.slice(shells.indexOf('className="mpv1-topbar'), shells.indexOf('className="mpv1-m-topbar'));
if (desktopTopbar.includes('to="/app/account"')) {
  issues.push("Account duplicated in desktop utility nav");
}

if (issues.length) {
  console.error("FAIL data-truth:", issues);
  process.exit(1);
}
console.log("PASS: v18.2.7 data-truth static checks");
