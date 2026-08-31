/**
 * Authenticated DRAFT preview. Fetches the admin-only draft (never the public
 * API) and renders a readable structured view so the OWNER can review before
 * publishing. Drafts are never exposed publicly.
 */
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { adminPreview } from "../api/client";

type AnyObj = Record<string, unknown>;

function Value({ v }: { v: unknown }) {
  if (v == null) return <span className="corp-muted">—</span>;
  if (Array.isArray(v)) {
    return (
      <ul className="corp-feat">
        {v.map((it, i) => (
          <li key={i}>{typeof it === "object" ? <Obj o={it as AnyObj} /> : String(it)}</li>
        ))}
      </ul>
    );
  }
  if (typeof v === "object") return <Obj o={v as AnyObj} />;
  return <span>{String(v)}</span>;
}

function Obj({ o }: { o: AnyObj }) {
  return (
    <div className="corp-repeat-item">
      {Object.entries(o).map(([k, val]) => (
        <div key={k} className="corp-editor-row">
          <label>{k}</label>
          <Value v={val} />
        </div>
      ))}
    </div>
  );
}

export function Preview() {
  const loc = useLocation();
  const slug = decodeURIComponent(loc.pathname.replace(/^\/admin\/preview\//, ""));
  const [data, setData] = useState<AnyObj | null | undefined>(undefined);
  useEffect(() => {
    adminPreview(slug).then((r) => setData(r.ok ? ((r.body as AnyObj).data as AnyObj) : null)).catch(() => setData(null));
  }, [slug]);

  return (
    <div className="corp-admin-section">
      <div className="corp-actions" style={{ justifyContent: "space-between" }}>
        <h2>草稿預覽 / Draft preview · {slug}</h2>
        <Link className="corp-btn-ghost corp-btn-sm" to="/admin/content">← 返回 / Back</Link>
      </div>
      <p className="corp-editor-hint">此為草稿內容，尚未公開發布 / DRAFT — not published, not visible to the public.</p>
      <div className="corp-preview-frame" style={{ padding: "1.25rem" }}>
        {data === undefined ? (
          <p className="corp-state corp-state-loading">載入中… / loading…</p>
        ) : data === null ? (
          <p className="corp-state corp-state-error">無法載入草稿 / cannot load draft</p>
        ) : (
          <Obj o={data} />
        )}
      </div>
    </div>
  );
}
