import { DecisionLink, MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { allCounterEvidence } from "../../member/demoCatalog";

export function MemberCounterEvidencePage() {
  const items = allCounterEvidence();
  return (
    <MemberPageChrome
      title="Counter Evidence"
      subtitle="Contradicting evidence · challenge before commit · Dual Calibration input"
    >
      {items.length === 0 ? (
        <EmptyState label="No counter-evidence rows" />
      ) : (
        <ul className="member-list">
          {items.map((e) => (
            <li key={`${e.decisionId}-${e.id}`} className="member-panel">
              <div className="member-card-meta">
                <strong>{e.title}</strong>
                <span className="member-chip warn">{e.polarity}</span>
              </div>
              <p>{e.summary}</p>
              <p className="muted sm">
                {e.source} · Decision <DecisionLink id={e.decisionId} />
              </p>
            </li>
          ))}
        </ul>
      )}
    </MemberPageChrome>
  );
}
