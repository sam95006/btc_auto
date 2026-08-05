import { DecisionLink, MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { allEvidence } from "../../member/demoCatalog";

export function MemberEvidencePage() {
  const items = allEvidence();
  return (
    <MemberPageChrome
      title="Evidence"
      subtitle="Supporting evidence across Decision Objects · cited · no invention policy"
    >
      {items.length === 0 ? (
        <EmptyState label="No evidence rows" />
      ) : (
        <ul className="member-list">
          {items.map((e) => (
            <li key={`${e.decisionId}-${e.id}`} className="member-panel">
              <div className="member-card-meta">
                <strong>{e.title}</strong>
                <span className="member-chip">{e.polarity}</span>
              </div>
              <p>{e.summary}</p>
              <p className="muted sm">
                {e.source} · {e.asOf} · {e.freshness} · Decision{" "}
                <DecisionLink id={e.decisionId} />
              </p>
            </li>
          ))}
        </ul>
      )}
    </MemberPageChrome>
  );
}
