import { Link } from "react-router-dom";
import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { decisions } from "../../member/demoCatalog";

export function MemberDecisionFeedPage() {
  if (decisions.length === 0) {
    return (
      <MemberPageChrome title="Decision Feed" subtitle="Public Decision Objects">
        <EmptyState label="No Decisions in DEMO catalog" />
      </MemberPageChrome>
    );
  }

  return (
    <MemberPageChrome
      title="Decision Feed"
      subtitle="Atomic Decision Objects · record intent · never place exchange orders"
    >
      <ul className="member-feed">
        {decisions.map((d) => (
          <li key={d.id} className="member-feed-item">
            <div className="member-feed-top">
              <Link to={`/decisions/${d.id}`} className="member-feed-title">
                {d.title}
              </Link>
              <span className="member-chip">{d.posture}</span>
            </div>
            <p className="muted sm">
              {d.symbol} · {d.confidenceLabel} · evidence {d.evidenceCount} · counter{" "}
              {d.counterEvidenceCount} · risks {d.riskOpenCount}
            </p>
            <p className="member-thesis-snip">{d.thesis}</p>
            <div className="member-feed-actions">
              <Link to={`/decisions/${d.id}`}>Detail</Link>
              <Link to={`/decisions/${d.id}#evidence`}>Evidence</Link>
              <Link to={`/decisions/${d.id}#counter-evidence`}>Counter</Link>
              <Link to={`/decisions/${d.id}#risks`}>Risks</Link>
            </div>
          </li>
        ))}
      </ul>
    </MemberPageChrome>
  );
}
