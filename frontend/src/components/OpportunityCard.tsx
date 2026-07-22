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

type Props = {
  candidate: MarketCandidate;
  simple?: boolean;
  defaultExpanded?: boolean;
};

/**
 * Product 7 Opportunity Card — evidence / contradicting / risk / invalidation / freshness.
 * Never coerces null or missing provider fields to numeric 0.
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
        : c.riskScore >= 70
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

  return (
    <article className={`nx-opp-card side-${c.side.toLowerCase()}`} aria-label={`${c.symbol} opportunity`}>
      <div className="nx-opp-card-primary">
        <div className="nx-opp-card-head">
          <Link to={`/market/${c.symbol}`} className="nx-opp-sym mono">
            {c.symbol.replace("USDT", "")}
          </Link>
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
            <strong className="mono">{fmtNum(opp)}</strong>
          </div>
          <div>
            <span className="muted">信心</span>
            <strong className="mono">{fmtNum(conf)}</strong>
          </div>
          <div className={risk != null && risk >= 70 ? "hot" : undefined}>
            <span className="muted">風險</span>
            <strong className="mono">{fmtNum(risk)}</strong>
          </div>
          <div>
            <span className="muted">價格</span>
            <strong className="mono">{formatUsd(c.currentPrice)}</strong>
          </div>
        </div>
        <p className="nx-opp-why">{whyNow}</p>
        <div className="nx-opp-card-foot muted">
          <span>{freshnessLabel(c.freshness)}</span>
          <span>{displayOrPending(provider, "資料來源待接入")}</span>
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
            <h4>Supporting Evidence</h4>
            {supporting.length ? (
              <ul>
                {supporting.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">尚無支持證據</p>
            )}
          </section>
          <section>
            <h4>Contradicting Evidence</h4>
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
              <dt>market_phase</dt>
              <dd>{STAGE_LABEL_ZH[c.stage] || c.stage}</dd>
            </div>
            <div>
              <dt>risk_level</dt>
              <dd>{fmtNum(risk)}</dd>
            </div>
            <div>
              <dt>risk_gate_result</dt>
              <dd>{riskGate}</dd>
            </div>
            <div>
              <dt>entry_condition</dt>
              <dd>
                {c.stage === "CONFIRMED"
                  ? "條件已確認（研究觀察，非下單指令）"
                  : "等待確認 — 非進場指令"}
              </dd>
            </div>
            <div>
              <dt>invalidation_condition</dt>
              <dd>{displayOrPending(invalidation, "失效條件尚未提供")}</dd>
            </div>
            <div>
              <dt>invalidation_price</dt>
              <dd>資料尚不可用</dd>
            </div>
            <div>
              <dt>do_not_chase_reason</dt>
              <dd>{displayOrPending(doNotChase, "無特別追價警示")}</dd>
            </div>
            <div>
              <dt>data_freshness</dt>
              <dd>{freshnessLabel(c.freshness)}</dd>
            </div>
            <div>
              <dt>provider_status</dt>
              <dd>{displayOrPending(provider, "provider pending")}</dd>
            </div>
            <div>
              <dt>decision_trace_link</dt>
              <dd>
                <Link to={`/market/${c.symbol}`}>打開 Symbol Workbench → AI Evidence</Link>
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
    </article>
  );
}
