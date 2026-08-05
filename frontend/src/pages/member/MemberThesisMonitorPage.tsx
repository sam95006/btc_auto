import { DecisionLink, MemberPageChrome } from "../../member/MemberPageChrome";
import { thesisMonitors } from "../../member/demoCatalog";

export function MemberThesisMonitorPage() {
  return (
    <MemberPageChrome
      title="Thesis Monitor"
      subtitle="Thesis Integrity Monitor · alert without auto-trading"
    >
      <ul className="member-list">
        {thesisMonitors.map((t) => (
          <li key={t.id} className="member-panel">
            <div className="member-card-meta">
              <strong>{t.status}</strong>
              <span className="member-chip">{t.driftNote}</span>
            </div>
            <p>{t.thesis}</p>
            <p className="muted sm">Invalidation: {t.invalidation}</p>
            <p className="muted sm">
              Last checked {t.lastChecked} · <DecisionLink id={t.decisionId} />
            </p>
          </li>
        ))}
      </ul>
    </MemberPageChrome>
  );
}
