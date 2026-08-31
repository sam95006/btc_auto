/**
 * CMS content editor. Uses a structured SchemaForm when a schema exists for the
 * slug, otherwise a raw-JSON fallback. Tracks unsaved changes (in-app + a
 * beforeunload guard), supports Save Draft / Publish / Preview, and shows the
 * published version. Every mutation goes through the authenticated CSRF-guarded
 * API — this component holds no credentials.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { adminGetContent, adminPublish, adminSaveContent } from "../../api/client";
import { SchemaForm, validate } from "./formKit";
import { SCHEMAS } from "./schemas";

type AnyObj = Record<string, unknown>;

export function ContentEditor({ slug }: { slug: string }) {
  const conf = SCHEMAS[slug];
  const [value, setValue] = useState<AnyObj>({});
  const [json, setJson] = useState("");
  const [jsonError, setJsonError] = useState("");
  const [meta, setMeta] = useState<{ status?: string; published_version?: number } | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const baseline = useRef("");

  const load = async () => {
    setMsg("");
    const r = await adminGetContent(slug);
    const draft = ((r.body as AnyObj).draft as AnyObj) ?? {};
    setValue(draft);
    setJson(JSON.stringify(draft, null, 2));
    baseline.current = JSON.stringify(draft);
    setMeta({ status: (r.body as AnyObj).status as string, published_version: (r.body as AnyObj).published_version as number });
  };
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  const current = conf ? JSON.stringify(value) : json.trim() ? safeStable(json) : "";
  const dirty = useMemo(() => current !== baseline.current && baseline.current !== "", [current]);

  // Guard against losing unsaved edits on a hard navigation / reload.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const readValue = (): AnyObj | null => {
    if (conf) return value;
    try {
      const parsed = JSON.parse(json);
      setJsonError("");
      return parsed;
    } catch {
      setJsonError("JSON 格式錯誤 / invalid JSON");
      return null;
    }
  };

  const save = async () => {
    const data = readValue();
    if (!data) return;
    if (conf) {
      const errs = validate(conf.schema, data);
      if (errs.length) { setMsg(errs.join(" · ")); return; }
    }
    setBusy(true);
    const r = await adminSaveContent(slug, data);
    setBusy(false);
    if (r.ok) { baseline.current = JSON.stringify(data); setMsg("草稿已儲存 / draft saved"); }
    else setMsg("儲存失敗 / save failed");
  };

  const publish = async () => {
    if (dirty) { setMsg("請先儲存草稿再發布 / save draft before publishing"); return; }
    setBusy(true);
    const r = await adminPublish(slug);
    setBusy(false);
    if (r.ok) { setMsg(`已發布 v${(r.body as AnyObj).published_version} / published`); load(); }
    else setMsg("發布失敗（權限？）/ publish failed");
  };

  return (
    <div className="corp-admin-section">
      <div className="corp-actions" style={{ justifyContent: "space-between" }}>
        <h2>{conf?.label ?? slug}</h2>
        <span className="corp-published-tag">
          {meta?.status ?? "—"}{meta?.published_version ? ` · v${meta.published_version}` : ""}
        </span>
      </div>

      {conf ? (
        <SchemaForm schema={conf.schema} value={value} onChange={setValue} />
      ) : (
        <div className="corp-editor">
          <div className="corp-editor-row">
            <label>Raw JSON</label>
            <textarea
              rows={18} spellCheck={false} style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.82rem" }}
              className={jsonError ? "invalid" : ""}
              value={json} onChange={(e) => setJson(e.target.value)}
            />
            {jsonError ? <div className="corp-editor-err">{jsonError}</div> : null}
            <div className="corp-editor-hint">No structured editor for this section yet — edit JSON directly.</div>
          </div>
        </div>
      )}

      <div className="corp-actions">
        <button className="corp-btn corp-btn-sm" onClick={save} disabled={busy || !dirty}>儲存草稿 / Save draft</button>
        <button className="corp-btn-ghost corp-btn-sm" onClick={publish} disabled={busy}>發布 / Publish</button>
        <Link className="corp-btn-ghost corp-btn-sm" to={`/admin/preview/${slug}`}>預覽草稿 / Preview</Link>
        {dirty ? <span className="corp-admin-dirty" data-testid="dirty">未儲存 / Unsaved changes</span> : null}
        {msg ? <span className="corp-provenance" role="status">{msg}</span> : null}
      </div>
    </div>
  );
}

function safeStable(jsonStr: string): string {
  try { return JSON.stringify(JSON.parse(jsonStr)); } catch { return jsonStr; }
}
