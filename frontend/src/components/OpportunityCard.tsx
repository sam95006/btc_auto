import { useState } from "react";
import { Link } from "react-router-dom";
import {
  STAGE_LABEL_ZH,
  plainReason,
  sideLabelZh,
  type MarketCandidate,
} from "../market/scannerApi";
import { displayOrPending, fmtNum, freshnessLabel } from "../market/displayNull";
import { formatUsd } from "../market/freshness";
import { FavoriteToggle } from "./FavoriteToggle";

type Props = {
  candidate: MarketCandidate;
  simple?: boolean;
  defaultExpanded?: boolean;
};

function unavailable(v: unknown): boolean {
  return v == null || v === "" || (typeof v === "number" && Number.isNaN(v));
}

/**
 * Opportunity card — SIMPLE: Decision → Why → Risk → Invalidation → Freshness.
 * Missing fields show UNAVAILABLE (never coerce to 0).
 */
export function OpportunityCard({ candidate: c, simple = true, defaultExpanded = false }: Props) {
  const [open, setOpen] = useState(defaultExpanded);
  const whyNow = plainReason(c.reasons?.[0] || "結構仍在觀察", simple);
  const supporting = (c.reasons || []).slice(0, 4).map((r) => plainReason(r, simple));
  const contradicting = (c.conflicts || []).slice(0, 4).map((r) => plainReason(r, simple));
  const riskGate =
    c.stage === "OVEREXTENDED"
      ? "BLOCKED_OVEREXTENDED"
      : c.stage === "INSUFFICIENT_DATA"
        ? "PENDING_DATA"
        : !unavailable(c.riskScore) && (c.riskScore as number) >= 70
          ? "ELEVATED_RISK"
          : "PASS_OBSERVE";
  const doNotChase =
    c.stage === "OVEREXTENDED"
      ? "過熱勿追：動能可能已過度延伸"
      : c.conflicts?.[0]
        ? plainReason(c.conflicts[0], simple)
        : null;
  const invalidation = c.invalidationContext || null;
  const provider = c.source || null;
  const opp = c.opportunityScore;
  const conf = c.confirmationScore;
  const risk = c.riskScore;

  const decisionText =
    c.side === "LONG" || c.side === "SHORT"
      ? `${sideLabelZh(c.side)} · ${STAGE_LABEL_ZH[c.stage] || c.stage}`
      : "方向待確認";
  const decisionClass =
    c.side === "LONG" ? "long" : c.side === "SHORT" ? "short" : "unavailable";

  const riskText = unavailable(risk)
    ? "UNAVAILABLE"
    : `${fmtNum(risk)}${(risk as number) >= 70 ? " · 偏高" : ""}`;
  const invalidationText = displayOrPending(invalidation, "UNAVAILABLE");
  const freshText = freshnessLabel(c.freshness) || "UNAVAILABLE";

  if (simple) {
    return (
      <article
        className={`nx-opp-card nx-opp-v1827-simple side-${c.side.toLowerCase()}`}
        aria-label={`${c.symbol} opportunity`}
        data-testid="opp-simple-card"
      >
        <div className="nx-opp-card-head">
          <Link to={`/market/${c.symbol}`} className="nx-opp-sym mono">
            {c.symbol.replace("USDT", "")}
          </Link>
          <FavoriteToggle symbol={c.symbol} />
          <span className={`nx-side-mark side-${c.side.toLowerCase()}`}>
            {c.side === "LONG" ? "▲" : c.side === "SHORT" ? "▼" : "●"}
          </span>
        </div>
        <div className="nx-opp-simple-flow">
          <div className="nx-opp-flow-row">
            <span className="flow-k">決策</span>
            <p className={`flow-v ${decisionClass}`}>{decisionText}</p>
          </div>
          <div className="nx-opp-flow-row">
            <span className="flow-k">原因</span>
            <p className="flow-v">{whyNow}</p>
          </div>
          <div className="nx-opp-flow-row">
            <span className="flow-k">風險</span>
            <p className={`flow-v ${unavailable(risk) ? "unavailable" : (risk as number) >= 70 ? "risk-hot" : ""}`}>
              {riskText}
            </p>
          </div>
          <div className="nx-opp-flow-row">
            <span className="flow-k">失效</span>
            <p className={`flow-v ${invalidationText === "UNAVAILABLE" ? "unavailable" : ""}`}>
              {invalidationText}
            </p>
          </div>
          <div className="nx-opp-flow-row">
            <span className="flow-k">新鮮度</span>
            <p className="flow-v">{freshText}</p>
          </div>
        </div>
        <Link to={`/market/${c.symbol}`} className="nx-link" data-testid="opp-view-analysis">
          查看分析 →
        </Link>
      </article>
    );
  }

  return (
    <article className={`nx-opp-card side-${c.side.toLowerCase()}`} aria-label={`${c.symbol} opportunity`}>
      <div className="nx-opp-card-primary">
        <div className="nx-opp-card-head">
          <Link to={`/market/${c.symbol}`} className="nx-opp-sym mono">
            {c.symbol.replace("USDT", "")}
          </Link>
          <FavoriteToggle symbol={c.symbol} />
          <span className={`nx-side-mark side-${c.side.toLowerCase()}`}>
            {c.side === "LONG" ? "▲" : c.side === "SHORT" ? "▼" : "●"} {sideLabelZh(c.side)}
          </span>
          <span className={`nx-stage-badge nx-stage-${c.stage.toLowerCase()}`}>
            {STAGE_LABEL_ZH[c.stage] || c.stage}
          </span>
        </div>
        <div className="nx-opp-card-scores">
          <div>
            <span className="muted">機會</span>
            <strong className="mono">{unavailable(opp) ? "UNAVAILABLE" : fmtNum(opp)}</strong>
          </div>
          <div>
            <span className="muted">信心</span>
            <strong className="mono">{unavailable(conf) ? "UNAVAILABLE" : fmtNum(conf)}</strong>
          </div>
          <div className={!unavailable(risk) && (risk as number) >= 70 ? "hot" : undefined}>
            <span className="muted">風險</span>
            <strong className="mono">{unavailable(risk) ? "UNAVAILABLE" : fmtNum(risk)}</strong>
          </div>
          <div>
            <span className="muted">價格</span>
            <strong className="mono">
              {unavailable(c.currentPrice) ? "UNAVAILABLE" : formatUsd(c.currentPrice)}
            </strong>
          </div>
        </div>
        <p className="nx-opp-why">{whyNow}</p>
        <div className="nx-opp-card-foot muted">
          <span>{freshText}</span>
          <span>{displayOrPending(provider, "UNAVAILABLE")}</span>
        </div>
        <button
          type="button"
          className="nx-text-btn"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "收合證據" : "展開證據"}
        </button>
      </div>

      {open ? (
        <div className="nx-opp-card-evidence">
          <section>
            <h4>支持證據</h4>
            {supporting.length ? (
              <ul>
                {supporting.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">UNAVAILABLE</p>
            )}
          </section>
          <section>
            <h4>反方證據</h4>
            {contradicting.length ? (
              <ul>
                {contradicting.map((r) => (
                  <li key={r} className="conflict">
                    {r}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">目前未偵測到明顯反方證據</p>
            )}
          </section>
          <dl className="nx-kv mono">
            <div>
              <dt>階段</dt>
              <dd>{STAGE_LABEL_ZH[c.stage] || c.stage}</dd>
            </div>
            <div>
              <dt>風險閘門</dt>
              <dd>{riskGate}</dd>
            </div>
            <div>
              <dt>失效條件</dt>
              <dd>{invalidationText}</dd>
            </div>
            <div>
              <dt>勿追原因</dt>
              <dd>{displayOrPending(doNotChase, "UNAVAILABLE")}</dd>
            </div>
            <div>
              <dt>新鮮度</dt>
              <dd>{freshText}</dd>
            </div>
            <div>
              <dt>來源</dt>
              <dd>{displayOrPending(provider, "UNAVAILABLE")}</dd>
            </div>
            <div>
              <dt>詳情</dt>
              <dd>
                <Link to={`/market/${c.symbol}`}>標的工作台 →</Link>
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
    </article>
  );
}
