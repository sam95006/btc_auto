import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getStatus, ownerSetup } from "../api/client";

/** One-time owner bootstrap UI. The backend is authoritative — this only
 * reflects the server's open/closed state and cannot bypass it. */
export function OwnerSetup() {
  const nav = useNavigate();
  const [open, setOpen] = useState<boolean | null>(null);
  const [form, setForm] = useState({ email: "", password: "", display_name: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getStatus().then((s) => setOpen(s.owner_bootstrap === "open")).catch(() => setOpen(null));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    const r = await ownerSetup(form);
    setBusy(false);
    if (r.ok) nav("/admin");
    else setErr(r.status === 403 ? "擁有者帳號已建立，Bootstrap 已關閉。" : String(r.body.error || "建立失敗"));
  }

  return (
    <div className="corp-admin-shell">
      <div className="corp-admin-card">
        <h1>建立擁有者帳號 / Owner Setup</h1>
        {open === false ? (
          <p className="corp-state corp-state-unavailable" data-testid="bootstrap-closed">
            擁有者帳號已存在，Bootstrap 已永久關閉。請前往 <a href="/admin/login">登入</a>。
          </p>
        ) : (
          <form onSubmit={onSubmit} className="corp-form">
            <label>電子郵件<input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
            <label>名稱<input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
            <label>密碼（至少 12 字元）<input type="password" required minLength={12} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
            <button className="corp-btn" disabled={busy} type="submit">{busy ? "建立中…" : "建立擁有者"}</button>
            {err ? <p className="corp-state corp-state-error" role="alert">{err}</p> : null}
          </form>
        )}
      </div>
    </div>
  );
}
