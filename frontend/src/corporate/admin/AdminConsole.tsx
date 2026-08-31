import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import {
  adminAudit,
  adminContentList,
  adminGetContent,
  adminLeads,
  adminLogout,
  adminOverview,
  adminPublish,
  adminSaveContent,
  adminSession,
} from "../api/client";
import type { AdminSession } from "../types";

const SECTIONS = [
  ["", "Overview"], ["content", "Content"], ["leads", "Leads"], ["audit", "Audit"],
] as const;

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
  useEffect(() => { adminOverview().then((r) => setD(r.ok ? r.body : null)); }, []);
  if (!d) return <p className="corp-state corp-state-loading">載入中…</p>;
  return (
    <div className="corp-cards">
      <div className="corp-card"><h3>Owner bootstrap</h3><p>{String(d.owner_bootstrap ?? "unavailable")}</p></div>
      <div className="corp-card"><h3>Content sections</h3><p>{String(d.content_sections ?? "unavailable")}</p></div>
      <div className="corp-card"><h3>Leads</h3><p>{String(d.leads ?? "unavailable")}</p></div>
      <p className="corp-provenance">{String(d.note ?? "")}</p>
    </div>
  );
}

function ContentAdmin() {
  const [list, setList] = useState<any[]>([]);
  const [slug, setSlug] = useState("");
  const [json, setJson] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => { adminContentList().then((r) => setList((r.body.content as any[]) || [])); }, []);
  async function open(s: string) {
    setSlug(s); setMsg("");
    const r = await adminGetContent(s);
    setJson(JSON.stringify((r.body as any).draft ?? {}, null, 2));
  }
  async function save() {
    try { await adminSaveContent(slug, JSON.parse(json)); setMsg("草稿已儲存 (DRAFT)"); }
    catch { setMsg("JSON 格式錯誤"); }
  }
  async function publish() { const r = await adminPublish(slug); setMsg(r.ok ? `已發布 v${(r.body as any).published_version}` : "發布失敗（權限？）"); }
  return (
    <div className="corp-admin-content">
      <div className="corp-admin-slugs">
        {list.map((c) => <button key={c.slug} className={slug === c.slug ? "is-active" : ""} onClick={() => open(c.slug)}>{c.slug}</button>)}
      </div>
      {slug ? (
        <div className="corp-admin-editor">
          <h3>{slug}</h3>
          <textarea value={json} onChange={(e) => setJson(e.target.value)} rows={16} spellCheck={false} />
          <div className="corp-scene-cta">
            <button className="corp-btn" onClick={save}>儲存草稿</button>
            <button className="corp-btn-ghost" onClick={publish}>發布</button>
          </div>
          {msg ? <p className="corp-provenance" role="status">{msg}</p> : null}
        </div>
      ) : <p className="corp-state corp-state-loading">選擇一個內容區塊以編輯。</p>}
    </div>
  );
}

function SimpleList({ loader, cols }: { loader: () => Promise<any>; cols: string[] }) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { loader().then((r) => setRows((r.body.leads || r.body.audit || []) as any[])); }, []);
  return (
    <table className="corp-table">
      <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={i}>{cols.map((c) => <td key={c}>{String(row[c] ?? "")}</td>)}</tr>)}</tbody>
    </table>
  );
}

export function AdminConsole() {
  const session = useSession();
  const nav = useNavigate();
  if (session === undefined) return <div className="corp-admin-shell"><p className="corp-state corp-state-loading">載入中…</p></div>;
  if (!session || !session.authenticated) return <Navigate to="/admin/login" replace />;
  return (
    <div className="corp-admin-shell corp-admin-full">
      <aside className="corp-admin-side">
        <div className="corp-admin-me">{session.email}<span>{session.role}</span></div>
        {SECTIONS.map(([p, label]) => <Link key={p} to={`/admin/${p}`}>{label}</Link>)}
        <button className="corp-btn-ghost" onClick={async () => { await adminLogout(); nav("/admin/login"); }}>登出</button>
      </aside>
      <div className="corp-admin-main">
        <Routes>
          <Route index element={<Overview />} />
          <Route path="content" element={<ContentAdmin />} />
          <Route path="leads" element={<SimpleList loader={adminLeads} cols={["email", "company", "kind", "status", "created_at"]} />} />
          <Route path="audit" element={<SimpleList loader={adminAudit} cols={["action", "target", "created_at"]} />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </div>
    </div>
  );
}
