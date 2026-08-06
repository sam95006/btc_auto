import { Link } from "react-router-dom";
import {
  FORBIDDEN_FOUNDER_FIELD_NAMES,
  honestDisplay,
  type MarketPulseFirstScreenModel,
  type PulseAnswer,
} from "./marketPulseAnswers";

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
      {answer.id === "top_3_markets_contracts" && answer.markets?.length ? (
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
      {answer.id === "analysis_vs_actual_trading" ? (
        <p className="muted sm" data-testid="pulse-trading-flag">
          actually_traded={answer.actually_traded === true ? "YES" : "NO"} · analysis-only
        </p>
      ) : null}
    </li>
  );
}

/**
 * PUB17-B member first screen — Market Pulse + Top Opportunities.
 * Nine answers only. No Founder position size / leverage / entry / stop / order id.
 */
export function MarketPulseFirstScreen({ model }: { model: MarketPulseFirstScreenModel }) {
  // Defensive: never render forbidden founder field names as UI labels.
  const bannedHit = FORBIDDEN_FOUNDER_FIELD_NAMES.some((f) =>
    JSON.stringify(model).includes(`"${f}"`),
  );

  return (
    <section
      className="member-first-screen member-market-pulse"
      aria-label="Market Pulse and Top Opportunities"
      data-testid="market-pulse-first-screen"
      data-chrome={model.chromeLabel}
      data-mode={model.mode}
      data-posture={model.aiPosture}
    >
      <div className="member-first-head">
        <div>
          <p className="member-kicker">Market Pulse · Top Opportunities</p>
          <h2 className="member-hero-title">Know the pulse before you chase</h2>
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

      <ol className="member-five-answers pulse-nine-answers" data-testid="market-pulse-nine-answers">
        {model.answers.map((a, idx) => (
          <AnswerCard key={a.id} answer={a} index={idx} />
        ))}
      </ol>

      <p className="muted sm">
        Founder private fields blocked: position size, leverage, exact entry/stop, order ID,
        private thresholds, private strategy source.
      </p>
    </section>
  );
}
