import { Link } from "react-router-dom";
import { LiveFunnelPanel } from "./LiveFunnelPanel";
import {
  FORBIDDEN_FOUNDER_FIELD_NAMES,
  honestDisplay,
  type LiveFunnelFirstScreenModel,
  type PulseAnswer,
} from "./liveFunnelModels";

function StateChip({ state }: { state: string }) {
  const s = (state || "UNAVAILABLE").toUpperCase();
  return (
    <span className={`member-chip pulse-state pulse-state-${s.toLowerCase()}`} data-state={s}>
      {s}
    </span>
  );
}

function AnswerCard({ answer, index }: { answer: PulseAnswer; index: number }) {
  const display = honestDisplay(answer.answer, answer.state);
  return (
    <li className="member-five-card pulse-answer-card" data-answer-id={answer.id}>
      <div className="member-five-card-top">
        <span className="member-five-idx">{index + 1}</span>
        <h3>{answer.question}</h3>
        <StateChip state={answer.state} />
      </div>
      <p className="member-five-answer" data-testid={`pulse-answer-${answer.id}`}>
        {display}
      </p>
      <p className="muted sm">{answer.detail}</p>
      {answer.id === "top_3_opportunities" && answer.markets?.length ? (
        <ol className="pulse-top3" data-testid="pulse-top3">
          {answer.markets.slice(0, 3).map((m) => (
            <li key={`${m.rank}-${m.market}`}>
              <Link className="mono" to={`/market/${m.market}`}>
                {m.market}
              </Link>{" "}
              · {m.contract} · {m.side_hint}
              <span className="muted sm"> — {m.note}</span>
            </li>
          ))}
        </ol>
      ) : null}
      {answer.id === "crypto_derivatives_risk" && answer.metrics?.length ? (
        <ul className="pulse-metrics" data-testid="pulse-deriv-metrics">
          {answer.metrics.map((m) => (
            <li key={m.key}>
              <span className="muted">{m.key}</span>:{" "}
              <strong className="mono">{m.display}</strong>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * PUB18-A member first screen — Live Funnel + Market Pulse.
 * No Founder positions / leverage / private thresholds / order IDs / Lessons / trade buttons.
 */
export function LiveFunnelMarketPulseScreen({ model }: { model: LiveFunnelFirstScreenModel }) {
  const bannedHit = FORBIDDEN_FOUNDER_FIELD_NAMES.some((f) =>
    JSON.stringify(model).includes(`"${f}"`),
  );

  return (
    <section
      className="member-first-screen member-live-funnel-pulse"
      aria-label="Live Funnel and Market Pulse"
      data-testid="live-funnel-market-pulse-first-screen"
      data-chrome={model.chromeLabel}
      data-class={model.dataClass}
      data-posture={model.aiPosture}
      data-trade-buttons="false"
    >
      <div className="member-first-head">
        <div>
          <p className="member-kicker">Live Funnel · Market Pulse</p>
          <h2 className="member-hero-title">Read-only pulse before you chase</h2>
          <p className="muted sm">{model.note}</p>
        </div>
        <div className="pulse-head-chips">
          <StateChip state={model.chromeLabel} />
          <span className="member-chip" data-testid="pulse-ai-posture">
            AI {model.aiPosture}
          </span>
        </div>
      </div>

      {bannedHit ? (
        <div className="nx-banner-warn" role="alert">
          Blocked: Founder private field leak detected in model — not rendered.
        </div>
      ) : null}

      <LiveFunnelPanel
        stages={model.funnel.stages}
        summary={model.funnel.summary}
        dataClass={model.dataClass}
      />

      <ol className="member-five-answers pulse-nine-answers" data-testid="live-funnel-nine-answers">
        {model.answers.map((a, idx) => (
          <AnswerCard key={a.id} answer={a} index={idx} />
        ))}
      </ol>

      <p className="muted sm" data-testid="live-funnel-bans">
        Banned on this screen: Founder positions, exact leverage, private thresholds, real order
        IDs, private Lessons, trade buttons.
      </p>
    </section>
  );
}
