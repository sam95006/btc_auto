import {
  FORBIDDEN_PRIVATE_FIELD_NAMES,
  honestDisplay,
  type DecisionDetailModel,
  type DetailField,
} from "./decisionDetailFields";

function StateChip({ state }: { state: string }) {
  const s = (state || "UNAVAILABLE").toUpperCase();
  return (
    <span className={`member-chip detail-state detail-state-${s.toLowerCase()}`} data-state={s}>
      {s}
    </span>
  );
}

function FieldCard({ field, index }: { field: DetailField; index: number }) {
  const display = honestDisplay(field.answer, field.state);
  return (
    <li className="member-five-card detail-field-card" data-field-id={field.id}>
      <div className="member-five-card-top">
        <span className="member-five-idx">{index + 1}</span>
        <h3>{field.label}</h3>
        <StateChip state={field.state} />
      </div>
      <p className="member-five-answer" data-testid={`detail-field-${field.id}`}>
        {display}
      </p>
      <p className="muted sm">{field.detail}</p>
      {field.id === "decision_timeline" && field.stages?.length ? (
        <ol className="detail-timeline" data-testid="detail-timeline">
          {field.stages.map((s) => (
            <li key={`${s.stage}-${s.at}`}>
              <strong className="mono">{s.stage}</strong>
              <span className="muted sm"> · {s.at}</span>
            </li>
          ))}
        </ol>
      ) : null}
      {(field.id === "evidence" || field.id === "counter_evidence") && field.items?.length ? (
        <ul className="detail-evidence" data-testid={`detail-${field.id}-items`}>
          {field.items.map((item, i) => (
            <li key={`${field.id}-${i}`}>
              {item.summary}
              {item.polarity ? <span className="muted sm"> · {item.polarity}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {field.id === "delayed_learning_summary" ? (
        <p className="muted sm" data-testid="detail-learning-flag">
          private_lesson_memory={field.private_lesson_memory === true ? "YES" : "NO"}
        </p>
      ) : null}
    </li>
  );
}

/**
 * PUB18-B member Decision Detail + Learning Transparency.
 * Twelve public-safe fields. No private graph / thresholds / weights / prompts / CoT / account.
 */
export function DecisionDetailTransparency({ model }: { model: DecisionDetailModel }) {
  const bannedHit = FORBIDDEN_PRIVATE_FIELD_NAMES.some((f) =>
    JSON.stringify(model).includes(`"${f}"`),
  );

  return (
    <section
      className="member-first-screen member-decision-detail-transparency"
      aria-label="Decision Detail and Learning Transparency"
      data-testid="decision-detail-transparency"
      data-chrome={model.chromeLabel}
      data-mode={model.mode}
      data-posture={model.aiPosture}
      data-decision-id={model.decisionId}
    >
      <div className="member-first-head">
        <div>
          <p className="member-kicker">Decision Detail · Learning Transparency</p>
          <h2 className="member-hero-title">See why — without the private core</h2>
          <p className="muted sm">{model.note}</p>
          <p className="muted sm mono">decision_id={model.decisionId}</p>
        </div>
        <div className="detail-head-chips">
          <StateChip state={model.chromeLabel} />
          <span className="member-chip" data-testid="detail-ai-posture">
            AI {model.aiPosture}
          </span>
        </div>
      </div>

      {bannedHit ? (
        <div className="nx-banner-warn" role="alert">
          Blocked: private field leak detected in model — not rendered.
        </div>
      ) : null}

      <ol className="member-five-answers detail-twelve-fields" data-testid="decision-detail-twelve-fields">
        {model.fields.map((f, idx) => (
          <FieldCard key={f.id} field={f} index={idx} />
        ))}
      </ol>

      <p className="muted sm">
        Member cannot see: private raw graph, exact proprietary thresholds, full private strategy
        weights, Founder entry/exit, internal prompts, raw CoT, account data.
      </p>
    </section>
  );
}
