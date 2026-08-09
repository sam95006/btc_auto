import { useEffect, useState } from "react";
import {
  forgotPassword,
  loadMemberSession,
  loginMember,
  logoutMember,
  resetPassword,
  signupMember,
  verifyEmailToken,
  type MemberSession,
} from "./authApi";

type Mode = "login" | "signup" | "forgot" | "reset" | "verify";

/** Paid Private Beta identity panel — uses existing public auth realm. */
export function MemberIdentityPanel() {
  const [session, setSession] = useState<MemberSession | null>(() => loadMemberSession());
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [token, setToken] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSession(loadMemberSession());
  }, []);

  const onLogout = async () => {
    setBusy(true);
    await logoutMember();
    setSession(null);
    setMessage("已登出 — 工作階段已作廢");
    setBusy(false);
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
              ? `註冊成功。請貼上驗證碼完成 email 驗證（staging inline token）。`
              : "註冊成功。",
          );
          if (vTok) {
            setToken(String(vTok));
            setMode("verify");
          }
        }
      } else if (mode === "login") {
        const { res, body } = await loginMember(email, password);
        if (!res.ok || !body?.ok) {
          setMessage(String(body?.error || `login_failed_${res.status}`));
        } else {
          setSession(loadMemberSession());
          setMessage("登入成功 — 自選 / 通知 / 上次造訪已綁定此身分");
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
          已登入
        </h2>
        <p className="muted sm">
          {session.email}
          {session.emailVerified ? " · 已驗證" : " · 尚未驗證 email"}
        </p>
        <p className="mono muted" style={{ fontSize: "0.75rem" }}>
          account={session.accountId} · session={session.sessionId}
        </p>
        <div className="mp2-actions" style={{ marginTop: 12 }}>
          <button type="button" className="mp2-btn mp2-btn-primary" disabled={busy} onClick={() => void onLogout()}>
            登出
          </button>
          {!session.emailVerified ? (
            <button type="button" className="mp2-btn mp2-btn-ghost" onClick={() => setMode("verify")}>
              驗證 Email
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
        Paid Private Beta · 身分
      </h2>
      <p className="muted sm">註冊 / 登入後，自選與通知中心綁定真實工作階段（非本機 canonical）。</p>
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
            className={mode === id ? "mp2-btn mp2-btn-primary" : "mp2-btn mp2-btn-ghost"}
            onClick={() => setMode(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <form onSubmit={onSubmit} style={{ marginTop: 12, maxWidth: 420 }} data-testid="member-identity-form">
        {mode === "signup" || mode === "login" || mode === "forgot" ? (
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
        {mode === "signup" || mode === "login" || mode === "reset" ? (
          <>
            <label className="muted sm" htmlFor="id-password">
              密碼
            </label>
            <input
              id="id-password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              className="mp2-input"
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, marginBottom: 8 }}
            />
          </>
        ) : null}
        {mode === "verify" || mode === "reset" || mode === "forgot" ? null : null}
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
