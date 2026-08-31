import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminLogin } from "../api/client";

export function AdminLogin() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    const r = await adminLogin(email, password);
    setBusy(false);
    if (r.ok) nav("/admin");
    else setErr("登入失敗，請確認帳號密碼。");
  }

  return (
    <div className="corp-admin-shell">
      <div className="corp-admin-card">
        <h1>管理登入 / Admin Login</h1>
        <form onSubmit={onSubmit} className="corp-form">
          <label>電子郵件<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>密碼<input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          <button className="corp-btn" disabled={busy} type="submit" data-testid="admin-login-submit">{busy ? "登入中…" : "登入"}</button>
          {err ? <p className="corp-state corp-state-error" role="alert">{err}</p> : null}
        </form>
      </div>
    </div>
  );
}
