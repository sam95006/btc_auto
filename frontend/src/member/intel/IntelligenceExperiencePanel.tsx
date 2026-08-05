import { IntelligenceFunnel } from "./IntelligenceFunnel";
import { IntelligenceStateChip } from "./IntelligenceStateChip";
import type { MemberIntelExperience } from "./types";

export function IntelligenceExperiencePanel({
  experience,
}: {
  experience: MemberIntelExperience;
}) {
  const similar = experience.similar_case_stats;
  return (
    <article
      className="member-intel-card"
      data-testid="member-intel-experience"
      data-case-id={experience.case_id}
      data-lifecycle={experience.lifecycle_state}
      data-posture={experience.posture}
      data-mode={experience.mode}
      data-chrome={experience.chrome_label}
      data-actually-ordered={String(experience.actually_ordered)}
    >
      <header className="member-intel-card-head">
        <div>
          <p className="member-kicker">
            {experience.symbol} · {experience.decision_id}
          </p>
          <h3 className="member-intel-posture">{experience.posture}</h3>
          <p className="muted sm">
            Regime: {experience.regime_label} · Freshness: {experience.data_freshness}
          </p>
        </div>
        <div className="member-intel-card-chips">
          <IntelligenceStateChip state={experience.lifecycle_state} />
          <span className="member-intel-mode-chip" data-mode={experience.chrome_label}>
            {experience.chrome_label}
          </span>
        </div>
      </header>

      <IntelligenceFunnel
        stages={experience.funnel.stages}
        summary={experience.funnel.summary}
        sourceMode={experience.funnel.source_mode}
      />

      <section aria-label="Why suggested">
        <h4>Why suggested</h4>
        {experience.why_suggested.length === 0 ? (
          <p className="muted">UNAVAILABLE — no fabricated rationale</p>
        ) : (
          <ul className="member-list">
            {experience.why_suggested.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Contradicting evidence">
        <h4>Contradicting evidence</h4>
        {experience.contradicting_evidence.length === 0 ? (
          <p className="muted">None listed · not invented</p>
        ) : (
          <ul className="member-list">
            {experience.contradicting_evidence.map((e, idx) => (
              <li key={`${e.evidence_summary}-${idx}`}>
                <strong>{e.evidence_polarity}</strong> · {e.evidence_summary}
                <span className="muted sm">
                  {" "}
                  · {e.source_label} · {e.evidence_freshness}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Similar-case stats">
        <h4>Similar-case stats</h4>
        <dl className="member-dl">
          <div>
            <dt>Summary</dt>
            <dd>{similar.similar_case_summary}</dd>
          </div>
          <div>
            <dt>Sample size</dt>
            <dd data-testid="similar-case-count">
              {similar.available
                ? similar.display_count ?? String(similar.similar_case_count)
                : "UNAVAILABLE"}
            </dd>
          </div>
          <div>
            <dt>Win rate</dt>
            <dd data-testid="similar-win-rate">
              {similar.win_rate == null ? "UNAVAILABLE — no guarantee published" : String(similar.win_rate)}
            </dd>
          </div>
          <div>
            <dt>Guarantee claimed</dt>
            <dd>{similar.guarantee_claimed ? "YES" : "NO"}</dd>
          </div>
        </dl>
      </section>

      <section aria-label="Order status">
        <h4>Actually ordered?</h4>
        <p data-testid="actually-ordered-display">
          <strong>{experience.actually_ordered_display}</strong>
          {experience.lifecycle_state === "AI_SUGGESTION" ? (
            <span className="muted sm"> · AI suggestion is not a filled order</span>
          ) : null}
          {experience.order_fill_claimed ? (
            <span className="tag tag-warn"> FILL CLAIMED (banned)</span>
          ) : (
            <span className="muted sm"> · no fill claimed</span>
          )}
        </p>
      </section>
    </article>
  );
}
