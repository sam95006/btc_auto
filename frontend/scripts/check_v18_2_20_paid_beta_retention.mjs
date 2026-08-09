#!/usr/bin/env node
/**
 * V18.2.20 — paid beta retention foundation checks (preserves V18.2.19 analytics).
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "..", "src");
const ROOT = path.resolve(__dirname, "..", "..");

const marker = "PUBLIC_V18_2_21_PAID_BETA_IDENTITY_HEAD";

const buildInfo = fs.readFileSync(path.join(SRC, "demo", "buildInfo.ts"), "utf8");
assert.ok(buildInfo.includes(marker), "buildInfo marker");

const app = fs.readFileSync(path.join(SRC, "app", "NexusMemberProductV2.tsx"), "utf8");
assert.ok(app.includes(marker), "app marker");
assert.ok(app.includes('data-member-surface="v18_2_21"'), "surface marker");
assert.ok(app.includes('path="/research"'), "research route");

const watch = fs.readFileSync(path.join(SRC, "product_v2", "pages", "WatchlistPageV2.tsx"), "utf8");
assert.ok(watch.includes("AuthRequiredBlocker"), "watchlist auth blocker");
assert.ok(watch.includes('data-watchlist-authority="SERVER"'), "server watchlist authority");
assert.ok(watch.includes("fetchServerWatchlist"), "server watchlist fetch");

const alerts = fs.readFileSync(path.join(SRC, "product_v2", "pages", "AlertsPageV2.tsx"), "utf8");
assert.ok(alerts.includes("NotificationCenterPanel"), "notification center");
assert.ok(alerts.includes("RETENTION_ALERT_EVENT_TYPES"), "alert event types");

const overview = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OverviewPageV2.tsx"), "utf8");
assert.ok(overview.includes("OnboardingWizard"), "onboarding");
assert.ok(overview.includes("SinceLastVisitPanel"), "since last visit");
assert.ok(overview.includes("MarketStateVisual"), "preserve market state visual");

const retentionApi = fs.readFileSync(path.join(SRC, "retention", "retentionApi.ts"), "utf8");
assert.ok(retentionApi.includes("AUTH_REQUIRED_BLOCKER"), "auth blocker const");
assert.ok(retentionApi.includes("/api/nexus/public/retention"), "retention API");

const backendRoutes = fs.readFileSync(
  path.join(ROOT, "backend", "nexus_paid_beta_retention", "routes.py"),
  "utf8",
);
assert.ok(backendRoutes.includes("AUTH_REQUIRED_BLOCKER") || backendRoutes.includes("auth_required_body"), "backend auth gate");
assert.ok(backendRoutes.includes("/watchlist"), "watchlist routes");
assert.ok(backendRoutes.includes("/notifications"), "notification routes");
assert.ok(backendRoutes.includes("/since-last-visit"), "since last visit route");

const constants = fs.readFileSync(
  path.join(ROOT, "backend", "nexus_paid_beta_retention", "constants.py"),
  "utf8",
);
for (const t of [
  "RADAR_NEW",
  "RADAR_UP",
  "RADAR_DOWN",
  "RADAR_OUT",
  "STATE_CHANGE",
  "ACTIVITY_ACCELERATION",
  "OI_CHANGE",
  "FUNDING_EXTREME",
  "RISK_CHANGE",
  "DATA_DEGRADED",
  "WATCHLIST_EVENT",
]) {
  assert.ok(constants.includes(t), `missing event type ${t}`);
}

console.log("PASS: v18.2.20 paid beta retention foundation");
