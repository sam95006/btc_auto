import { DecisionLink, MemberPageChrome } from "../../member/MemberPageChrome";
import { alerts } from "../../member/demoCatalog";

export function MemberAlertsPage() {
  return (
    <MemberPageChrome
      title="Alerts"
      subtitle="Thesis · risk · freshness · outcome alerts · Shadow observation only"
    >
      <ul className="member-list">
        {alerts.map((a) => (
          <li key={a.id} className="member-panel">
            <div className="member-card-meta">
              <strong>{a.title}</strong>
              <span className={`member-chip ${a.severity === "HIGH" ? "warn" : ""}`}>
                {a.kind} · {a.severity}
              </span>
            </div>
            <p>{a.body}</p>
            <p className="muted sm">
              {a.createdAt}
              {a.decisionId ? (
                <>
                  {" "}
                  · <DecisionLink id={a.decisionId} />
                </>
              ) : null}
            </p>
          </li>
        ))}
      </ul>
    </MemberPageChrome>
  );
}
