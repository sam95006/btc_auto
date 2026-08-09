#!/usr/bin/env node
/**
 * V18.2.22 — closed beta readiness + product reliability checks.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, "..", "src");
const ROOT = path.resolve(__dirname, "..", "..");

const marker = "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD";

const buildInfo = fs.readFileSync(path.join(SRC, "demo", "buildInfo.ts"), "utf8");
assert.ok(buildInfo.includes(marker), "buildInfo marker");

const app = fs.readFileSync(path.join(SRC, "app", "NexusMemberProductV2.tsx"), "utf8");
assert.ok(app.includes(marker), "app marker");
assert.ok(app.includes('data-member-surface="v18_2_22"'), "surface marker");

const account = fs.readFileSync(path.join(SRC, "pages", "member", "MemberAccountPage.tsx"), "utf8");
assert.ok(account.includes("MemberIdentityPanel"), "account identity panel");
assert.ok(account.includes("Billing"), "no live billing implication text present as OFF");

const identity = fs.readFileSync(path.join(SRC, "retention", "MemberIdentityPanel.tsx"), "utf8");
assert.ok(identity.includes("beta-access-status") || identity.includes("Beta access"), "beta access UX");
assert.ok(identity.includes("redeemInviteCode") || identity.includes("invite"), "invite redeem");
assert.ok(identity.includes("選用 MFA") || identity.includes("enrollMfa"), "optional MFA");
assert.ok(identity.includes("account-deletion") || identity.includes("刪除帳戶"), "deletion link");

const closedBeta = fs.readFileSync(path.join(SRC, "retention", "closedBetaApi.ts"), "utf8");
assert.ok(closedBeta.includes("/api/nexus/public/closed-beta"), "closed beta API");

const backendInvite = fs.readFileSync(
  path.join(ROOT, "backend", "nexus_closed_beta", "service.py"),
  "utf8",
);
assert.ok(backendInvite.includes("INVITED"), "INVITED status");
assert.ok(backendInvite.includes("ACTIVE"), "ACTIVE status");
assert.ok(backendInvite.includes("REVOKED"), "REVOKED status");
assert.ok(backendInvite.includes("EXPIRED"), "EXPIRED status");
assert.ok(backendInvite.includes("redeem_invite"), "redeem");
assert.ok(backendInvite.includes("revoke_invite"), "revoke");

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
  "session_started",
  "session_returned",
  "watchlist_removed",
  "notification_read",
]) {
  assert.ok(analytics.includes(ev), `analytics event ${ev}`);
}

const ops = fs.readFileSync(path.join(ROOT, "backend", "nexus_closed_beta", "ops.py"), "utf8");
for (const ch of [
  "auth_errors",
  "radar_api_failures",
  "watchlist_persistence_failures",
  "notification_failures",
  "market_series_failures",
]) {
  assert.ok(ops.includes(ch), `ops channel ${ch}`);
}

const partner = fs.readFileSync(
  path.join(ROOT, "backend", "nexus_closed_beta", "partner_inventory.py"),
  "utf8",
);
assert.ok(partner.includes("new_external_agent_api_exposed"), "partner inventory");
assert.ok(partner.includes("Agent Gateway"), "future attach point");

console.log("PASS: v18.2.22 closed beta readiness");
