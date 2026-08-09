import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  confirmMfa,
  enrollMfa,
  forgotPassword,
  loadMemberSession,
  loginMember,
  logoutMember,
  resetPassword,
  signupMember,
  verifyEmailToken,
  fetchAuthMe,
  type MemberSession,
} from "./authApi";
import { fetchBetaAccess, redeemInviteCode, type BetaAccess } from "./closedBetaApi";
import { fetchServerWatchlist, fetchNotifications } from "./retentionApi";

type Mode = "login" | "signup" | "forgot" | "reset" | "verify" | "mfa";

/** Closed Beta identity panel — invite-bound access; no live Billing. */
export function MemberIdentityPanel() {
  const [session, setSession] = useState<MemberSession | null>(() => loadMemberSession());
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [token, setToken] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [mfaChallengeId, setMfaChallengeId] = useState("");
  const [mfaResponse, setMfaResponse] = useState("");
  const [mfaHint, setMfaHint] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [beta, setBeta] = useState<BetaAccess | null>(null);
  const [entitlementTier, setEntitlementTier] = useState<string | null>(null);
  const [mfaStatus, setMfaStatus] = useState<string | null>(null);
  const [watchCount, setWatchCount] = useState<number | null>(null);
  const [notifUnread, setNotifUnread] = useState<number | null>(null);

  const refreshAccountSurface = async () => {
    const me = await fetchAuthMe();
    if (me.res.ok && me.body?.ok) {
      setEntitlementTier(String(me.body?.entitlements?.tier || me.body?.account?.tier || ""));
      setMfaStatus(String(me.body?.mfa?.status || "disabled"));
      if (me.body?.beta_access) setBeta(me.body.beta_access as BetaAccess);
    }
    const b = await fetchBetaAccess();
    if (b.res.ok && b.body?.beta_access) setBeta(b.body.beta_access as BetaAccess);
    const wl = await fetchServerWatchlist();
    if (wl.res.ok && wl.body?.ok) setWatchCount(Number(wl.body?.count ?? wl.body?.items?.length ?? 0));
    const notes = await fetchNotifications(20);
    if (notes.res.ok && notes.body?.ok) {
      const items = (notes.body.items || []) as Array<{ read?: boolean }>;
      setNotifUnread(items.filter((n) => !n.read).length);
    }
  };

  useEffect(() => {
    setSession(loadMemberSession());
  }, []);

  useEffect(() => {
    if (session?.token) void refreshAccountSurface();
  }, [session?.token]);

  const onLogout = async () => {
    setBusy(true);
    await logoutMember();
    setSession(null);
    setBeta(null);
    setMessage("已登出 — 工作階段已作廢");
    setBusy(false);
  };

  const onRedeemInvite = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const { res, body } = await redeemInviteCode(inviteCode);
      if (!res.ok || !body?.ok) {
        setMessage(String(body?.error || `invite_failed_${res.status}`));
      } else {
        setBeta(body.beta_access as BetaAccess);
        setMessage(`Closed Beta 已啟用：${body.beta_access?.status}`);
        setInviteCode("");
      }
    } finally {
      setBusy(false);
    }
  };

  const onEnrollMfa = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const { res, body } = await enrollMfa("totp", "optional-primary");
      if (!res.ok || !body?.ok) {
        setMessage(String(body?.error || `mfa_enroll_failed_${res.status}`));
      } else {
        const secret = String(body?.enrollment?.enrollment_secret_once || body?.enrollment_secret_once || "");
        const factorId = String(body?.enrollment?.factor_id || body?.factor_id || "");
        if (secret && factorId) {
          const conf = await confirmMfa(factorId, secret);
          if (conf.res.ok && conf.body?.ok !== false) {
            setMfaStatus("enabled");
            setMessage("選用 MFA 已啟用（staging stub；一般 beta 非強制）");
          } else {
            setMessage(String(conf.body?.error || "mfa_confirm_failed"));
          }
        } else {
          setMessage("MFA enroll started");
        }
        await refreshAccountSurface();
      }
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      if (mode === "signup") {
        const { res, body } = await signupMember(email, password, displayName);
        if (!res.ok || !body?.ok) {
          setMessage(String(body?.error || `signup_failed_${res.status}`));
        } else {
          const vTok = body?.account?.verification?.token;
          setMessage(
            vTok
              ? `註冊成功。請貼上驗證碼完成 email 驗證，再以邀請碼啟用 Closed Beta。`
              : "註冊成功。請以邀請碼啟用 Closed Beta。",
          );
          if (vTok) {
            setToken(String(vTok));
            setMode("verify");
          }
        }
      } else if (mode === "login" || mode === "mfa") {
        const { res, body } = await loginMember(email, password, {
          mfaChallengeId: mfaChallengeId || undefined,
          mfaResponseCode: mfaResponse || undefined,
        });
        if (body?.mfa_required && body?.mfa_challenge) {
          setMfaChallengeId(String(body.mfa_challenge.challenge_id || ""));
          setMfaHint(String(body.mfa_challenge.stub_response_hint || ""));
          setMode("mfa");
          setMessage("需要 MFA 驗證（Admin 已啟用時較強；一般成員選用）");
        } else if (!res.ok || !body?.ok) {
          setMessage(String(body?.error || `login_failed_${res.status}`));
        } else {
          setSession(loadMemberSession());
          setMode("login");
          setMfaChallengeId("");
          setMfaResponse("");
          setMessage("登入成功 — 自選 / 通知 / Closed Beta 狀態已綁定此身分");
        }
      } else if (mode === "verify") {
        const { res, body } = await verifyEmailToken(token);
        if (!res.ok || !body?.ok) {
          setMessage(String(body?.error || `verify_failed_${res.status}`));
        } else {
          setMessage("Email 已驗證");
          setMode("login");
        }
      } else if (mode === "forgot") {
        const { res, body } = await forgotPassword(email);
        if (!res.ok) {
          setMessage(String(body?.error || `forgot_failed_${res.status}`));
        } else {
          const rTok = body?.reset?.token;
          setMessage(rTok ? "已核發一次性重設碼（staging inline）。" : String(body?.note || "已受理"));
          if (rTok) {
            setToken(String(rTok));
            setMode("reset");
          }
        }
      } else if (mode === "reset") {
        const { res, body } = await resetPassword(token, password);
        if (!res.ok || !body?.ok) {
          setMessage(String(body?.error || `reset_failed_${res.status}`));
        } else {
          setMessage("密碼已重設 — 請重新登入（舊工作階段已作廢）");
          setMode("login");
          setPassword("");
        }
      }
    } finally {
      setBusy(false);
    }
  };

  if (session?.token) {
    return (
      <section className="nx10-panel" style={{ marginTop: 16 }} data-testid="member-identity-session">
        <h2 className="nx-sec-title" style={{ marginTop: 0 }}>
          已登入 · Closed Beta
        </h2>
        <dl className="nx-review-dl" data-testid="account-identity-summary">
          <div>
            <dt>Email</dt>
            <dd>{session.email}</dd>
          </div>
          <div>
            <dt>驗證</dt>
            <dd>{session.emailVerified ? "已驗證" : "尚未驗證"}</dd>
          </div>
          <div>
            <dt>Session</dt>
            <dd className="mono" style={{ fontSize: "0.75rem" }}>
              {session.sessionId || "—"}
            </dd>
          </div>
          <div>
            <dt>Beta access</dt>
            <dd data-testid="beta-access-status">{beta?.status || "INVITED"}</dd>
          </div>
          <div>
            <dt>Entitlement</dt>
            <dd>{entitlementTier || "server"} · Billing OFF</dd>
          </div>
          <div>
            <dt>MFA</dt>
            <dd>{mfaStatus || "disabled"} · 選用（非強制）</dd>
          </div>
          <div>
            <dt>Watchlist</dt>
            <dd>
              {watchCount == null ? "…" : `${watchCount} 檔`} ·{" "}
              <Link to="/watchlist">開啟</Link>
            </dd>
          </div>
          <div>
            <dt>通知</dt>
            <dd>
              未讀 {notifUnread == null ? "…" : notifUnread} ·{" "}
              <Link to="/alerts">通知中心</Link> ·{" "}
              <Link to="/notification-settings">偏好</Link>
            </dd>
          </div>
        </dl>
        <p className="mono muted" style={{ fontSize: "0.75rem" }}>
          account={session.accountId}
        </p>

        {beta?.status !== "ACTIVE" ? (
          <div style={{ marginTop: 12 }} data-testid="closed-beta-redeem">
            <label className="muted sm" htmlFor="invite-code">
              Closed Beta 邀請碼（單次使用）
            </label>
            <input
              id="invite-code"
              className="mp2-input"
              value={inviteCode}
              onChange={(ev) => setInviteCode(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }}
              placeholder="貼上邀請碼"
            />
            <button
              type="button"
              className="mp2-btn mp2-btn-primary"
              style={{ marginTop: 8 }}
              disabled={busy || !inviteCode}
              onClick={() => void onRedeemInvite()}
            >
              啟用 Beta
            </button>
          </div>
        ) : (
          <p className="muted sm" style={{ marginTop: 8 }} data-testid="closed-beta-active">
            Beta 狀態 ACTIVE · 無假付費訂閱 · Production Billing 未啟用
          </p>
        )}

        <div className="mp2-actions" style={{ marginTop: 12, flexWrap: "wrap" }}>
          <button type="button" className="mp2-btn mp2-btn-primary" disabled={busy} onClick={() => void onLogout()}>
            登出
          </button>
          <Link to="/account-deletion" className="mp2-btn mp2-btn-ghost">
            刪除帳戶
          </Link>
          {!session.emailVerified ? (
            <button type="button" className="mp2-btn mp2-btn-ghost" onClick={() => setMode("verify")}>
              驗證 Email
            </button>
          ) : null}
          {mfaStatus !== "enabled" ? (
            <button type="button" className="mp2-btn mp2-btn-ghost" disabled={busy} onClick={() => void onEnrollMfa()}>
              選用 MFA
            </button>
          ) : null}
        </div>
        {mode === "verify" ? (
          <form onSubmit={onSubmit} style={{ marginTop: 12 }} data-testid="member-verify-form">
            <label className="muted sm" htmlFor="verify-token">
              驗證碼
            </label>
            <input
              id="verify-token"
              className="mp2-input"
              value={token}
              onChange={(ev) => setToken(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }}
            />
            <button type="submit" className="mp2-btn mp2-btn-primary" style={{ marginTop: 8 }} disabled={busy}>
              確認驗證
            </button>
          </form>
        ) : null}
        {message ? (
          <p className="muted sm" style={{ marginTop: 8 }} role="status">
            {message}
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <section className="nx10-panel" style={{ marginTop: 16 }} data-testid="member-identity-panel">
      <h2 className="nx-sec-title" style={{ marginTop: 0 }}>
        Closed Beta · 身分
      </h2>
      <p className="muted sm">邀請制 Closed Beta（Billing OFF）。註冊／登入後以邀請碼啟用；自選與通知綁定真實工作階段。</p>
      <div className="mp2-actions" style={{ marginTop: 8, flexWrap: "wrap" }}>
        {(
          [
            ["login", "登入"],
            ["signup", "註冊"],
            ["forgot", "忘記密碼"],
            ["reset", "重設密碼"],
            ["verify", "驗證 Email"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={mode === id || (mode === "mfa" && id === "login") ? "mp2-btn mp2-btn-primary" : "mp2-btn mp2-btn-ghost"}
            onClick={() => setMode(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <form onSubmit={onSubmit} style={{ marginTop: 12, maxWidth: 420 }} data-testid="member-identity-form">
        {mode === "signup" || mode === "login" || mode === "forgot" || mode === "mfa" ? (
          <>
            <label className="muted sm" htmlFor="id-email">
              Email
            </label>
            <input
              id="id-email"
              type="email"
              required
              autoComplete="username"
              className="mp2-input"
              value={email}
              onChange={(ev) => setEmail(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, marginBottom: 8 }}
            />
          </>
        ) : null}
        {mode === "signup" ? (
          <>
            <label className="muted sm" htmlFor="id-name">
              顯示名稱
            </label>
            <input
              id="id-name"
              className="mp2-input"
              value={displayName}
              onChange={(ev) => setDisplayName(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, marginBottom: 8 }}
            />
          </>
        ) : null}
        {mode === "signup" || mode === "login" || mode === "reset" || mode === "mfa" ? (
          <>
            <label className="muted sm" htmlFor="id-password">
              密碼
            </label>
            <input
              id="id-password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === "login" || mode === "mfa" ? "current-password" : "new-password"}
              className="mp2-input"
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, marginBottom: 8 }}
            />
          </>
        ) : null}
        {mode === "mfa" ? (
          <>
            <label className="muted sm" htmlFor="id-mfa">
              MFA 回應碼
            </label>
            <input
              id="id-mfa"
              required
              className="mp2-input"
              value={mfaResponse}
              onChange={(ev) => setMfaResponse(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, marginBottom: 8 }}
              placeholder={mfaHint ? `staging hint: ${mfaHint}` : "MFA code"}
            />
          </>
        ) : null}
        {mode === "verify" || mode === "reset" ? (
          <>
            <label className="muted sm" htmlFor="id-token">
              {mode === "verify" ? "驗證碼" : "重設碼"}
            </label>
            <input
              id="id-token"
              required
              className="mp2-input"
              value={token}
              onChange={(ev) => setToken(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, marginBottom: 8 }}
            />
          </>
        ) : null}
        <button type="submit" className="mp2-btn mp2-btn-primary" disabled={busy}>
          {busy ? "處理中…" : "送出"}
        </button>
      </form>
      {message ? (
        <p className="muted sm" style={{ marginTop: 8 }} role="status">
          {message}
        </p>
      ) : null}
    </section>
  );
}
