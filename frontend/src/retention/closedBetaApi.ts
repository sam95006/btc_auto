/** Closed-beta invite + access API — server-authoritative; Billing OFF. */

import { loadRetentionAuth } from "./retentionApi";

const BASE = "/api/nexus/public/closed-beta";

export type BetaAccess = {
  account_id: string;
  status: "INVITED" | "ACTIVE" | "REVOKED" | "EXPIRED" | string;
  invite_id?: string | null;
  has_access?: boolean;
  production_billing?: boolean;
  entitlement_authority?: string;
};

async function betaFetch(path: string, init: RequestInit = {}) {
  const auth = loadRetentionAuth();
  const headers = new Headers(init.headers || {});
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (auth.token) headers.set("Authorization", `Bearer ${auth.token}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  return { res, body };
}

export async function fetchBetaAccess() {
  return betaFetch("/me");
}

export async function redeemInviteCode(inviteCode: string) {
  return betaFetch("/invites/redeem", {
    method: "POST",
    body: JSON.stringify({ invite_code: inviteCode }),
  });
}

export async function fetchClosedBetaFoundation() {
  return betaFetch("/foundation");
}
