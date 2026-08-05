import { DecisionLink, MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { allRisks } from "../../member/demoCatalog";

export function MemberRiskConditionsPage() {
  const items = allRisks();
  return (
    <MemberPageChrome
      title="Risk Conditions"
      subtitle="Invalidation and risk notes · advisory · user-owned · not exchange stops"
    >
      {items.length === 0 ? (
        <EmptyState label="No open risk conditions" />
      ) : (
        <ul className="member-list">
          {items.map((r) => (
            <li key={`${r.decisionId}-${r.id}`} className="member-panel">
              <div className="member-card-meta">
                <strong>
                  {r.symbol} · {r.label}
                </strong>
                <span className="member-chip">
                  {r.severity} · {r.status}
                </span>
              </div>
              <p className="muted sm">{r.note}</p>
              <p className="muted sm">
                Decision <DecisionLink id={r.decisionId} />
              </p>
            </li>
          ))}
        </ul>
      )}
    </MemberPageChrome>
  );
}
