import { Link } from "react-router-dom";
import type { FirstScreenModel } from "./firstScreenAnswers";
import { MemberUxStateChip } from "./MemberUxStateChip";
import { MEMBER_UX_STATES } from "./uxStates";
import { alerts, decisions, thesisMonitors } from "./demoCatalog";

function FirstScreenAnswers({
  model,
  view,
}: {
  model: FirstScreenModel;
  view: "simple" | "pro";
}) {
  return (
    <>
      <div className="member-first-head">
        <div>
          <p className="member-kicker">
            First screen · {view === "simple" ? "Simple View" : "Pro View"}
          </p>
          <h2 className="member-hero-title">Know before you chase</h2>
          <p className="muted sm">{model.note}</p>
        </div>
        <MemberUxStateChip state={model.shellState} />
      </div>

      <ol className="member-five-answers" data-testid="member-five-answers">
        {model.answers.map((a, idx) => (
          <li key={a.id} className="member-five-card" data-answer-id={a.id}>
            <div className="member-five-card-top">
              <span className="member-five-idx">{idx + 1}</span>
              <h3>{a.question}</h3>
              <MemberUxStateChip state={a.state} />
            </div>
            <p className="member-five-answer">{a.answer}</p>
            <p className="muted sm">{a.detail}</p>
            {a.href ? (
              <Link className="member-inline-link" to={a.href}>
                Open related →
              </Link>
            ) : null}
          </li>
        ))}
      </ol>

      <div className="member-first-metrics" aria-label="Scope counts">
        <article className="member-stat">
          <strong>{model.openDecisionCount}</strong>
          <span>Open Decisions</span>
        </article>
        <article className="member-stat">
          <strong>{model.highRiskCount}</strong>
          <span>HIGH risks</span>
        </article>
        <article className="member-stat">
          <strong>{model.pendingOutcomeCount}</strong>
          <span>Pending outcomes</span>
        </article>
        <article className="member-stat">
          <strong>{model.dataMode}</strong>
          <span>Data mode</span>
        </article>
      </div>
    </>
  );
}

export function MemberFirstScreenSimple({ model }: { model: FirstScreenModel }) {
  return (
    <section
      className="member-first-screen member-first-simple"
      aria-label="First screen Decision Integrity answers"
      data-testid="member-first-screen"
      data-shell-state={model.shellState}
      data-view="simple"
    >
      <FirstScreenAnswers model={model} view="simple" />
    </section>
  );
}

export function MemberFirstScreenPro({ model }: { model: FirstScreenModel }) {
  const focus = model.focusDecisionId
    ? decisions.find((d) => d.id === model.focusDecisionId)
    : undefined;
  const warnAlerts = alerts.filter((a) => a.severity !== "INFO");

  return (
    <section
      className="member-first-screen member-first-pro"
      aria-label="First screen Pro View"
      data-testid="member-first-screen"
      data-shell-state={model.shellState}
      data-view="pro"
    >
      <FirstScreenAnswers model={model} view="pro" />

      <div className="member-pro-grid">
        <section className="member-panel" aria-label="Focus Decision detail">
          <h2 className="nx-sec-title">Focus Decision · Pro</h2>
          {focus ? (
            <dl className="member-dl">
              <div>
                <dt>Symbol / posture</dt>
                <dd>
                  {focus.symbol} · {focus.posture}
                </dd>
              </div>
              <div>
                <dt>Confidence</dt>
                <dd>{focus.confidenceLabel}</dd>
              </div>
              <div>
                <dt>Human rationale</dt>
                <dd>{focus.humanRationale}</dd>
              </div>
              <div>
                <dt>AI challenge</dt>
                <dd>{focus.aiChallenge}</dd>
              </div>
              <div>
                <dt>Freshness</dt>
                <dd>
                  <MemberUxStateChip state={model.answers[1]?.state ?? model.shellState} />
                </dd>
              </div>
            </dl>
          ) : (
            <p className="muted">No focus Decision · empty/unavailable — not fabricated.</p>
          )}
          {focus ? (
            <p className="member-feed-actions">
              <Link to={`/decisions/${focus.id}`}>Decision detail</Link>
              <Link to="/counter-evidence">Counter evidence</Link>
              <Link to="/risk-conditions">Risk conditions</Link>
            </p>
          ) : null}
        </section>

        <section className="member-panel" aria-label="Thesis and alerts">
          <h2 className="nx-sec-title">Thesis Monitor · Alerts</h2>
          <ul className="member-list">
            {thesisMonitors.slice(0, 3).map((t) => (
              <li key={t.id}>
                <strong>{t.status}</strong> · {t.driftNote}
                <p className="muted sm">{t.invalidation}</p>
              </li>
            ))}
          </ul>
          <ul className="member-list">
            {warnAlerts.map((a) => (
              <li key={a.id}>
                <span className="member-chip warn">{a.severity}</span> {a.title}
              </li>
            ))}
          </ul>
        </section>

        <section className="member-panel member-ux-matrix" aria-label="UX state matrix">
          <h2 className="nx-sec-title">UX states</h2>
          <p className="muted sm">
            Required presentation states · unavailable never renders as a fabricated zero.
          </p>
          <ul className="member-ux-matrix-list" data-testid="member-ux-state-matrix">
            {MEMBER_UX_STATES.map((s) => (
              <li key={s}>
                <MemberUxStateChip state={s} showHint />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}
