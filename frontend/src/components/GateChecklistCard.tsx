import type { ChecklistItem } from "../demo/reportIndex";
import { DemoDataBadge } from "./DemoDataBadge";

/** Generic read-only gate / safety checklist for Private Operator. */
export function GateChecklistCard({
  title,
  items,
  footer,
  id,
}: {
  title: string;
  items: ChecklistItem[];
  footer?: string;
  id?: string;
}) {
  const allOk = items.every((i) => i.ok);
  return (
    <section className="panel-card" id={id} style={{ marginTop: "1.25rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>{title}</h2>
        <span className="demo-badge">SANITIZED</span>
        <span className="demo-badge">{allOk ? "all clear" : "wait-for-condition"}</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Sanitized snapshot · READ ONLY · NOT INVESTMENT ADVICE · checklist only · no control
        buttons · no Stage 4.19 start
      </p>
      <ul className="gate-checklist" style={{ marginTop: "0.75rem" }}>
        {items.map((item) => (
          <li key={item.id} className={item.ok ? "gate-ok" : "gate-fail"}>
            <span className="gate-mark">{item.ok ? "✓" : "✗"}</span>
            <span>{item.label}</span>
            <span className="mono muted">{String(item.ok)}</span>
          </li>
        ))}
      </ul>
      {footer ? (
        <p className="muted" style={{ marginTop: "0.75rem" }}>
          {footer}
        </p>
      ) : null}
    </section>
  );
}
