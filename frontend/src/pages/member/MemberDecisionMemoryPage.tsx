import { Link } from "react-router-dom";
import { DecisionLink, MemberPageChrome } from "../../member/MemberPageChrome";
import { decisions } from "../../member/demoCatalog";

export function MemberDecisionMemoryPage() {
  return (
    <MemberPageChrome
      title="Decision Memory"
      subtitle="Longitudinal Decision Graph (public) · never private Founder Lesson Memory"
    >
      <ul className="member-feed">
        {decisions.map((d) => (
          <li key={d.id} className="member-feed-item">
            <div className="member-feed-top">
              <DecisionLink id={d.id}>{d.title}</DecisionLink>
              <span className="member-chip">{d.outcomeClass}</span>
            </div>
            <p className="muted sm">
              {d.symbol} · posture {d.posture} · updated {d.updatedAt}
            </p>
          </li>
        ))}
      </ul>
      <p className="muted sm">
        Replay stays versioned on Decision Objects.{" "}
        <Link to="/outcome-review">Continue to Outcome Review</Link>
      </p>
    </MemberPageChrome>
  );
}
