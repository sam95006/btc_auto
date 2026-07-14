import { Link } from "react-router-dom";
import type { DeepLinkAction } from "../demo/reportIndex";
import { DemoDataBadge } from "./DemoDataBadge";

/** Read-only quick navigation actions (documentation deep links only). */
export function DeepLinkActionCard({
  title,
  actions,
  footer,
}: {
  title: string;
  actions: DeepLinkAction[];
  footer?: string;
}) {
  return (
    <section className="panel-card" style={{ marginTop: "1rem" }}>
      <div className="meta-row" style={{ marginTop: 0 }}>
        <h2 style={{ margin: 0, fontSize: "1.05rem" }}>{title}</h2>
        <span className="demo-badge">READ ONLY</span>
        <span className="demo-badge">docs only</span>
        <DemoDataBadge />
      </div>
      <p className="muted">
        Documentation deep links only · NOT INVESTMENT ADVICE · no control buttons · no Start Stage
        4.19 · no Run 30m · no Run 60m
      </p>
      <ul className="deep-link-list">
        {actions.map((a) => (
          <li key={a.id}>
            <Link className="deep-link" to={a.to}>
              {a.label}
            </Link>
            <span className="muted"> — {a.description}</span>
          </li>
        ))}
      </ul>
      {footer ? (
        <p className="muted" style={{ marginTop: "0.65rem" }}>
          {footer}
        </p>
      ) : null}
    </section>
  );
}
