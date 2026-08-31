import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  adminAnalytics, adminAudit, adminContentList, adminCreateAdmin, adminGetSetting, adminLeads,
  adminLogout, adminOverview, adminSession, adminSetSetting,
} from "../api/client";
import type { AdminSession } from "../types";
import { ContentEditor } from "./editors/ContentEditor";
import { Preview } from "./Preview";

const SECTIONS: [string, string][] = [
  ["", "Overview"], ["website", "Website"], ["products", "Products"], ["pricing", "Pricing"],
  ["showcase", "Showcase"], ["seo", "SEO"], ["content", "Content"], ["analytics", "Analytics"],
  ["leads", "Leads"], ["audit", "Audit"], ["admins", "Admins"], ["settings", "Settings"],
];

function useSession(): AdminSession | null | undefined {
  const [s, setS] = useState<AdminSession | null | undefined>(undefined);
  useEffect(() => {
    // Session is a cookie; ask the server whether it is still valid (survives reload).
    adminSession().then((r) => setS(r as AdminSession)).catch(() => setS(null));
  }, []);
  return s;
}

function Overview() {
  const [d, setD] = useState<Record<string, unknown> | null>(null);
  const [a, setA] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    adminOverview().then((r) => setD(r.ok ? r.body : null));
    adminAnalytics().then((r) => setA(r.ok ? r.body : null));
  }, []);
  return (
    <div className="corp-admin-section">
      <h2>Overview</h2>
      <div className="corp-metric-grid">
        <div className="corp-metric"><div className="v">{String(d?.owner_bootstrap ?? "—")}</div><div className="l">Owner bootstrap</div></div>
        <div className="corp-metric"><div className="v">{String(d?.content_sections ?? "—")}</div><div className="l">Content sections</div></div>
        <div className="corp-metric"><div className="v">{String(d?.leads ?? "—")}</div><div className="l">Leads</div></div>
        <div className="corp-metric">
          {a && (a.availability === "READY") ? <div className="v">{String(a.total)}</div> : <div className="u">unavailable</div>}
          <div className="l">Analytics events (recent)</div>
        </div>
      </div>
      <p className="corp-editor-hint">{String(d?.note ?? "")}</p>
    </div>
  );
}

function Analytics() {
  const [a, setA] = useState<Record<string, unknown> | null>(null);
  useEffect(() => { adminAnalytics().then((r) => setA(r.ok ? r.body : null)); }, []);
  const events = (a?.events as { event: string; count: number }[]) || [];
  return (
    <div className="corp-admin-section">
      <h2>Analytics</h2>
      <p className="corp-editor-hint">{String(a?.note ?? "First-party, privacy-conscious. Counts are backend-collected — never fabricated.")}</p>
      {a && a.availability === "READY" ? (
        <table className="corp-table">
          <thead><tr><th>Event</th><th>Count</th></tr></thead>
          <tbody>{events.map((e) => <tr key={e.event}><td>{e.event}</td><td>{e.count}</td></tr>)}</tbody>
        </table>
      ) : (
        <div className="corp-state corp-state-unavailable">尚無事件資料 / no analytics data yet</div>
      )}
    </div>
  );
}

function ContentList() {
  const [rows, setRows] = useState<{ slug: string; status?: string; published_version?: number }[]>([]);
  useEffect(() => { adminContentList().then((r) => setRows(((r.body.content as typeof rows) || []))); }, []);
  return (
    <div className="corp-admin-section">
      <h2>Content</h2>
      <p className="corp-editor-hint">All CMS sections. Priority sections have structured editors; others use JSON.</p>
      <table className="corp-table">
        <thead><tr><th>Slug</th><th>Status</th><th>Version</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.slug}>
              <td>{r.slug}</td><td>{r.status ?? "—"}</td><td>{r.published_version ?? "—"}</td>
              <td><Link className="corp-btn-ghost corp-btn-sm" to={`/admin/content/${r.slug}`}>編輯 / Edit</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SimpleList({ title, loader, cols }: { title: string; loader: () => Promise<{ body: Record<string, unknown> }>; cols: string[] }) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  useEffect(() => { loader().then((r) => setRows(((r.body.leads || r.body.audit || []) as Record<string, unknown>[]))); }, [loader]);
  return (
    <div className="corp-admin-section">
      <h2>{title}</h2>
      <table className="corp-table">
        <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((row, i) => <tr key={i}>{cols.map((c) => <td key={c}>{String(row[c] ?? "")}</td>)}</tr>)}</tbody>
      </table>
      {rows.length === 0 ? <p className="corp-editor-hint">尚無資料 / no records</p> : null}
    </div>
  );
}

function AdminsSection() {
  return (
    <div className="corp-admin-section">
      <h2>Admins</h2>
      <p className="corp-editor-hint">建立編輯者帳號（EDITOR 僅能編輯，不能發布）/ Create an EDITOR (can edit, cannot publish).</p>
      <CreateAdminForm />
    </div>
  );
}

function CreateAdminForm() {
  const [form, setForm] = useState({ email: "", password: "", display_name: "", role: "EDITOR" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setMsg("");
    const r = await adminCreateAdmin(form);
    setBusy(false);
    setMsg(r.ok ? "已建立 / created" : `失敗 / failed: ${String((r.body as Record<string, unknown>).error ?? r.status)}`);
    if (r.ok) setForm({ email: "", password: "", display_name: "", role: "EDITOR" });
  };
  return (
    <div className="corp-editor" style={{ maxWidth: "30rem" }}>
      <div className="corp-editor-row"><label>Email</label>
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
      <div className="corp-editor-row"><label>Display name</label>
        <input type="text" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></div>
      <div className="corp-editor-row"><label>Password (min 12)</label>
        <input type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
      <div className="corp-editor-row"><label>Role</label>
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="EDITOR">EDITOR</option>
        </select>
        <div className="corp-editor-hint">OWNER cannot be created here (one-time bootstrap only).</div>
      </div>
      <div className="corp-actions">
        <button className="corp-btn corp-btn-sm" onClick={submit} disabled={busy || form.password.length < 12 || !form.email}>建立 / Create</button>
        {msg ? <span className="corp-provenance">{msg}</span> : null}
      </div>
    </div>
  );
}

function SettingsSection() {
  const [key, setKey] = useState("site.meta");
  const [json, setJson] = useState("{}");
  const [msg, setMsg] = useState("");
  const loadKey = async () => {
    setMsg("");
    const r = await adminGetSetting(key);
    setJson(JSON.stringify((r.body as Record<string, unknown>).value ?? {}, null, 2));
  };
  const saveKey = async () => {
    try {
      const value = JSON.parse(json);
      const r = await adminSetSetting(key, value);
      setMsg(r.ok ? "已儲存 / saved" : "失敗 / failed");
    } catch { setMsg("JSON 格式錯誤 / invalid JSON"); }
  };
  return (
    <div className="corp-admin-section">
      <h2>Settings</h2>
      <div className="corp-editor" style={{ maxWidth: "40rem" }}>
        <div className="corp-editor-row"><label>Key</label>
          <input type="text" value={key} onChange={(e) => setKey(e.target.value)} /></div>
        <div className="corp-actions"><button className="corp-btn-ghost corp-btn-sm" onClick={loadKey}>載入 / Load</button></div>
        <div className="corp-editor-row"><label>Value (JSON)</label>
          <textarea rows={8} spellCheck={false} style={{ fontFamily: "ui-monospace, monospace" }} value={json} onChange={(e) => setJson(e.target.value)} /></div>
        <div className="corp-actions">
          <button className="corp-btn corp-btn-sm" onClick={saveKey}>儲存 / Save</button>
          {msg ? <span className="corp-provenance">{msg}</span> : null}
        </div>
      </div>
    </div>
  );
}

export function AdminConsole() {
  const session = useSession();
  const nav = useNavigate();
  const loc = useLocation();
  if (session === undefined) return <div className="corp-admin-shell"><p className="corp-state corp-state-loading">載入中… / loading…</p></div>;
  if (!session || !session.authenticated) return <Navigate to="/admin/login" replace />;

  const activeKey = loc.pathname.replace(/^\/admin\/?/, "").split("/")[0];
  return (
    <div className="corp-root">
      <div className="corp-admin-topbar">
        <Link to="/admin" className="corp-brand-mark"><span className="corp-brand-glyph" aria-hidden /><span className="corp-brand">NEXUS Admin</span></Link>
        <span className="sp" />
        <span className="corp-admin-me" style={{ margin: 0 }}>{session.email}<span>{session.role}</span></span>
        <button className="corp-btn-ghost corp-btn-sm" onClick={async () => { await adminLogout(); nav("/admin/login"); }}>登出 / Logout</button>
      </div>
      <nav className="corp-admin-nav" aria-label="Admin sections">
        {SECTIONS.map(([p, label]) => (
          <Link key={p} to={`/admin/${p}`} className={activeKey === p ? "is-active" : ""}>{label}</Link>
        ))}
      </nav>
      <div className="corp-admin-main">
        <Routes>
          <Route index element={<Overview />} />
          <Route path="website" element={<ContentEditor slug="site" />} />
          <Route path="products" element={<ContentEditor slug="products" />} />
          <Route path="pricing" element={<ContentEditor slug="pricing" />} />
          <Route path="showcase" element={<ContentEditor slug="showcase" />} />
          <Route path="seo" element={<ContentEditor slug="seo" />} />
          <Route path="content" element={<ContentList />} />
          <Route path="content/*" element={<ContentEditorRoute />} />
          <Route path="preview/*" element={<Preview />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="leads" element={<SimpleList title="Leads" loader={adminLeads} cols={["email", "company", "kind", "status", "created_at"]} />} />
          <Route path="audit" element={<SimpleList title="Audit" loader={adminAudit} cols={["action", "target", "created_at"]} />} />
          <Route path="admins" element={<AdminsSection />} />
          <Route path="settings" element={<SettingsSection />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </div>
    </div>
  );
}

function ContentEditorRoute() {
  const { slug = "" } = useLocationSlug();
  return <ContentEditor slug={slug} />;
}
function useLocationSlug() {
  const loc = useLocation();
  const slug = decodeURIComponent(loc.pathname.replace(/^\/admin\/content\//, ""));
  return { slug };
}
