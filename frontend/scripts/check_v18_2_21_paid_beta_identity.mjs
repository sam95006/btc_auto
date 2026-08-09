#!/usr/bin/env node
/**
 * V18.2.21 — paid beta identity + retention completion checks.
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

const account = fs.readFileSync(path.join(SRC, "pages", "member", "MemberAccountPage.tsx"), "utf8");
assert.ok(account.includes("MemberIdentityPanel"), "account identity panel");

const authApi = fs.readFileSync(path.join(SRC, "retention", "authApi.ts"), "utf8");
assert.ok(authApi.includes("/api/public/auth"), "auth API base");
assert.ok(authApi.includes("signupMember"), "signup");
assert.ok(authApi.includes("loginMember"), "login");
assert.ok(authApi.includes("logoutMember"), "logout");
assert.ok(authApi.includes("forgotPassword"), "forgot");
assert.ok(authApi.includes("resetPassword"), "reset");
assert.ok(authApi.includes("verifyEmailToken"), "verify");

const watch = fs.readFileSync(path.join(SRC, "product_v2", "pages", "WatchlistPageV2.tsx"), "utf8");
assert.ok(watch.includes("AuthRequiredBlocker"), "watchlist auth blocker");
assert.ok(watch.includes('data-watchlist-authority="SERVER"'), "server watchlist authority");

const overview = fs.readFileSync(path.join(SRC, "product_v2", "pages", "OverviewPageV2.tsx"), "utf8");
assert.ok(overview.includes("SinceLastVisitPanel"), "since last visit");
assert.ok(overview.includes("MarketStateVisual"), "preserve market state visual");

const backendRoutes = fs.readFileSync(
  path.join(ROOT, "backend", "nexus_public_auth", "routes.py"),
  "utf8",
);
assert.ok(backendRoutes.includes('/login'), "login route");
assert.ok(backendRoutes.includes('/logout'), "logout route");
assert.ok(backendRoutes.includes("/email/verify"), "email verify");
assert.ok(backendRoutes.includes("/password/forgot"), "forgot");
assert.ok(backendRoutes.includes("/password/reset"), "reset");

const passwords = fs.readFileSync(path.join(ROOT, "backend", "nexus_public_auth", "passwords.py"), "utf8");
assert.ok(passwords.includes("pbkdf2"), "pbkdf2 hashing");

const analytics = fs.readFileSync(
  path.join(ROOT, "backend", "nexus_product_analytics", "events.py"),
  "utf8",
);
for (const ev of [
  "signup_completed",
  "login_completed",
  "radar_opened",
  "symbol_opened",
  "watchlist_added",
  "alert_opened",
  "returned_from_alert",
]) {
  assert.ok(analytics.includes(ev), `analytics event ${ev}`);
}

console.log("PASS: v18.2.21 paid beta identity + retention");
