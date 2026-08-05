import { Link, useParams } from "react-router-dom";
import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { getDecision } from "../../member/demoCatalog";

export function MemberDecisionDetailPage() {
  const { decisionId = "" } = useParams();
  const d = getDecision(decisionId);

  if (!d) {
    return (
      <MemberPageChrome title="Decision Detail" subtitle={decisionId || "missing"}>
        <EmptyState label="Decision UNAVAILABLE in DEMO catalog" />
        <p>
          <Link to="/decisions">Back to Decision Feed</Link>
        </p>
      </MemberPageChrome>
    );
  }

  return (
    <MemberPageChrome title="Decision Detail" subtitle={`${d.symbol} · ${d.id}`}>
      <section className="member-panel">
        <div className="member-card-meta">
          <h2>{d.title}</h2>
          <span className="member-chip">{d.posture}</span>
        </div>
        <p>{d.thesis}</p>
        <p className="muted sm">
          Updated {d.updatedAt} · freshness {d.freshness} · outcome {d.outcomeClass}
        </p>
      </section>

      <section className="member-panel" id="context">
        <h2 className="nx-sec-title">Context Snapshot</h2>
        <p>{d.contextNote}</p>
      </section>

      <section className="member-panel" id="human-ai">
        <h2 className="nx-sec-title">Human &amp; AI record</h2>
        <p>
          <strong>Human:</strong> {d.humanRationale}
        </p>
        <p>
          <strong>AI challenge:</strong> {d.aiChallenge}
        </p>
      </section>

      <section className="member-panel" id="evidence">
        <h2 className="nx-sec-title">Evidence</h2>
        <ul className="member-list">
          {d.evidence.map((e) => (
            <li key={e.id}>
              <strong>{e.title}</strong>
              <span className="member-chip">{e.polarity}</span>
              <p className="muted sm">
                {e.source} · {e.asOf} · {e.freshness}
              </p>
              <p>{e.summary}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="member-panel" id="counter-evidence">
        <h2 className="nx-sec-title">Counter Evidence</h2>
        <ul className="member-list">
          {d.counterEvidence.map((e) => (
            <li key={e.id}>
              <strong>{e.title}</strong>
              <span className="member-chip warn">{e.polarity}</span>
              <p className="muted sm">
                {e.source} · {e.asOf}
              </p>
              <p>{e.summary}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="member-panel" id="risks">
        <h2 className="nx-sec-title">Risk &amp; Invalidation</h2>
        {d.risks.length === 0 ? (
          <p className="muted">No open risk conditions</p>
        ) : (
          <ul className="member-list">
            {d.risks.map((r) => (
              <li key={r.id}>
                <strong>{r.label}</strong>
                <span className="member-chip">
                  {r.severity} · {r.status}
                </span>
                <p className="muted sm">{r.note}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="member-panel" id="review">
        <h2 className="nx-sec-title">Outcome &amp; Review</h2>
        <p>Class: {d.outcomeClass}</p>
        <p>{d.reviewNote ?? "Review pending — complete in Outcome Review."}</p>
        <div className="member-cta-row">
          <Link className="member-btn" to="/outcome-review">
            Outcome Review
          </Link>
          <Link className="member-btn" to="/thesis-monitor">
            Thesis Monitor
          </Link>
          <Link className="member-btn" to="/nex-ai">
            Ask NEX AI
          </Link>
        </div>
      </section>
    </MemberPageChrome>
  );
}
