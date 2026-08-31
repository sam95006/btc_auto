/**
 * Compact schema-driven form kit for the Admin CMS. Renders structured inputs
 * (text / textarea / string-list / nested group / repeatable group) from a
 * schema so OWNERs edit fields, not raw JSON. Values are immutable-updated.
 * All mutations still flow through the authenticated, CSRF-protected API.
 */
import type { ReactNode } from "react";

export type Field =
  | { key: string; label: string; type: "text" | "textarea"; hint?: string; required?: boolean; placeholder?: string }
  | { key: string; label: string; type: "list"; hint?: string }
  | { key: string; label: string; type: "group"; fields: Field[] }
  | { key: string; label: string; type: "repeat"; fields: Field[]; addLabel?: string };

type AnyObj = Record<string, unknown>;

function get(obj: AnyObj, key: string): unknown {
  return obj ? obj[key] : undefined;
}
function setKey(obj: AnyObj, key: string, val: unknown): AnyObj {
  return { ...obj, [key]: val };
}

function FieldRow({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="corp-editor-row">
      <label>{label}</label>
      {children}
      {hint ? <div className="corp-editor-hint">{hint}</div> : null}
    </div>
  );
}

function renderField(field: Field, value: AnyObj, onChange: (v: AnyObj) => void): ReactNode {
  const cur = get(value, field.key);
  if (field.type === "text") {
    return (
      <FieldRow key={field.key} label={field.label} hint={field.hint}>
        <input
          type="text"
          value={String(cur ?? "")}
          placeholder={field.placeholder}
          onChange={(e) => onChange(setKey(value, field.key, e.target.value))}
        />
      </FieldRow>
    );
  }
  if (field.type === "textarea") {
    return (
      <FieldRow key={field.key} label={field.label} hint={field.hint}>
        <textarea rows={4} value={String(cur ?? "")} onChange={(e) => onChange(setKey(value, field.key, e.target.value))} />
      </FieldRow>
    );
  }
  if (field.type === "list") {
    const arr = Array.isArray(cur) ? (cur as string[]) : [];
    return (
      <FieldRow key={field.key} label={field.label} hint={field.hint ?? "One item per line"}>
        <textarea
          rows={Math.max(3, arr.length + 1)}
          value={arr.join("\n")}
          onChange={(e) => onChange(setKey(value, field.key, e.target.value.split("\n").map((s) => s.trimEnd()).filter((s) => s.length)))}
        />
      </FieldRow>
    );
  }
  if (field.type === "group") {
    const sub = (cur && typeof cur === "object" ? cur : {}) as AnyObj;
    return (
      <div className="corp-repeat-item" key={field.key}>
        <strong>{field.label}</strong>
        {field.fields.map((f) => renderField(f, sub, (nv) => onChange(setKey(value, field.key, nv))))}
      </div>
    );
  }
  if (field.type !== "repeat") return null;
  const items = Array.isArray(cur) ? (cur as AnyObj[]) : [];
  const update = (next: AnyObj[]) => onChange(setKey(value, field.key, next));
  return (
    <div className="corp-editor-row" key={field.key}>
      <label>{field.label}</label>
      <div className="corp-repeat">
        {items.map((item, i) => (
          <div className="corp-repeat-item" key={i}>
            <button
              type="button"
              className="corp-btn-ghost corp-btn-sm rm"
              onClick={() => update(items.filter((_, j) => j !== i))}
              aria-label={`Remove item ${i + 1}`}
            >
              移除 / Remove
            </button>
            {field.fields.map((f) => renderField(f, item, (nv) => update(items.map((it, j) => (j === i ? nv : it)))))}
          </div>
        ))}
        <button type="button" className="corp-btn-ghost corp-btn-sm" onClick={() => update([...items, {}])}>
          + {field.addLabel ?? "Add"}
        </button>
      </div>
    </div>
  );
}

export function validate(schema: Field[], value: AnyObj): string[] {
  const errors: string[] = [];
  for (const f of schema) {
    if ((f.type === "text" || f.type === "textarea") && f.required) {
      const v = get(value, f.key);
      if (!v || !String(v).trim()) errors.push(`${f.label} is required`);
    }
  }
  return errors;
}

export function SchemaForm({ schema, value, onChange }: { schema: Field[]; value: AnyObj; onChange: (v: AnyObj) => void }) {
  return <div className="corp-editor">{schema.map((f) => renderField(f, value || {}, onChange))}</div>;
}
