import { DecisionLink, MemberPageChrome } from "../../member/MemberPageChrome";
import { decisions } from "../../member/demoCatalog";

export function MemberOutcomeReviewPage() {
  const reviewable = decisions.filter((d) => d.outcomeClass !== "PENDING" || d.reviewNote);

  return (
    <MemberPageChrome
      title="Outcome Review"
      subtitle="Process-vs-outcome calibration · counterfactual marks · user remains final judge"
    >
      <ul className="member-list">
        {(reviewable.length ? reviewable : decisions).map((d) => (
          <li key={d.id} className="member-panel">
            <div className="member-card-meta">
              <strong>{d.title}</strong>
              <span className="member-chip">{d.outcomeClass}</span>
            </div>
            <p>{d.reviewNote ?? "Pending user Outcome + Review entry (DEMO stub)."}</p>
            <p className="muted sm">
              Counterfactual uses public marks — not private Founder fills.{" "}
              <DecisionLink id={d.id} />
            </p>
          </li>
        ))}
      </ul>
    </MemberPageChrome>
  );
}
