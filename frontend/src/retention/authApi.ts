/** Public auth API — session token cached in localStorage for UX only; server is canonical. */
import { saveRetentionToken, loadRetentionAuth } from "./retentionApi";

const AUTH_BASE = "/api/public/auth";

export type MemberSession = {
  accountId: string;
  email: string;
  displayName: string;
  emailVerified: boolean;
  token: string;
  sessionId: string;
  expiresAt: string;
};

const ACCOUNT_KEY = "nexus.public.auth.account.v1";

export function loadMemberSession(): MemberSession | null {
  try {
    const raw = localStorage.getItem(ACCOUNT_KEY);
    const auth = loadRetentionAuth();
    if (!raw || !auth.token) return null;
    const parsed = JSON.parse(raw) as MemberSession;
    if (!parsed?.accountId || !parsed?.token) return null;
    return { ...parsed, token: auth.token };
  } catch {
    return null;
  }
}

export function saveMemberSession(session: MemberSession | null) {
  try {
    if (!session) {
      localStorage.removeItem(ACCOUNT_KEY);
      saveRetentionToken(null);
      return;
    }
    localStorage.setItem(ACCOUNT_KEY, JSON.stringify(session));
    saveRetentionToken(session.token);
  } catch {
    /* ignore */
  }
}

async function authFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const auth = loadRetentionAuth();
  if (auth.token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${auth.token}`);
  }
  const res = await fetch(`${AUTH_BASE}${path}`, { ...init, headers, cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  return { res, body };
}

function persistLoginBody(body: any, email: string) {
  if (body?.session?.token) {
    const session: MemberSession = {
      accountId: String(body.account?.account_id || ""),
      email: String(body.account?.email || email),
      displayName: String(body.account?.display_name || ""),
      emailVerified: Boolean(body.account?.email_verified),
      token: String(body.session.token),
      sessionId: String(body.session.session_id || ""),
      expiresAt: String(body.session.expires_at || ""),
    };
    saveMemberSession(session);
  }
}

export async function signupMember(email: string, password: string, displayName = "") {
  return authFetch("/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, display_name: displayName || email.split("@")[0] }),
  });
}

export async function loginMember(
  email: string,
  password: string,
  opts?: { mfaChallengeId?: string; mfaResponseCode?: string },
) {
  const { res, body } = await authFetch("/login", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      mfa_challenge_id: opts?.mfaChallengeId || undefined,
      mfa_response_code: opts?.mfaResponseCode || undefined,
    }),
  });
  if (res.ok && body?.ok && body?.session?.token) {
    persistLoginBody(body, email);
  }
  return { res, body };
}

export async function logoutMember() {
  const { res, body } = await authFetch("/logout", { method: "POST", body: "{}" });
  saveMemberSession(null);
  return { res, body };
}

export async function verifyEmailToken(token: string) {
  return authFetch("/email/verify", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function resendVerification() {
  return authFetch("/email/resend", { method: "POST", body: "{}" });
}

export async function forgotPassword(email: string) {
  return authFetch("/password/forgot", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(token: string, password: string) {
  return authFetch("/password/reset", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}

export async function fetchAuthMe() {
  return authFetch("/me", { method: "POST", body: "{}" });
}

export async function enrollMfa(factorType = "totp", label = "primary") {
  const me = await fetchAuthMe();
  const accountId = me.body?.account?.account_id || me.body?.auth?.account_id;
  if (!accountId) return { res: me.res, body: { ok: false, error: "not_authenticated" } };
  return authFetch("/mfa/enroll", {
    method: "POST",
    body: JSON.stringify({ account_id: accountId, factor_type: factorType, label }),
  });
}

export async function confirmMfa(factorId: string, enrollmentSecret: string) {
  const me = await fetchAuthMe();
  const accountId = me.body?.account?.account_id || me.body?.auth?.account_id;
  if (!accountId) return { res: me.res, body: { ok: false, error: "not_authenticated" } };
  return authFetch("/mfa/confirm", {
    method: "POST",
    body: JSON.stringify({
      account_id: accountId,
      factor_id: factorId,
      enrollment_secret: enrollmentSecret,
    }),
  });
}
