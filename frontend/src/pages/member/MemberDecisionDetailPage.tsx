import { useMemo, useState } from "react";
import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";
import {
  DecisionDetailTransparency,
  buildDemoDecisionDetail,
} from "../../member/decision_detail";

type DetailVariant =
  | "demo_wait"
  | "demo_abstain"
  | "provider_required"
  | "stale"
  | "unavailable";

/**
 * PUB18-B Decision Detail page — member learning transparency surface.
 * Live slot strip retained for binding health; primary content is the
 * twelve-field transparency panel (never private core).
 */
export function MemberDecisionDetailPage() {
  const { loading, items } = usePageSlots([
    ["detail.decision_summary", "availability", "Decision"],
    ["detail.thesis_card", "freshness", "Thesis"],
    ["detail.context_card", "btc", "Context BTC"],
    ["detail.evidence_table", "freshness", "Evidence"],
    ["detail.counter_evidence_table", "freshness", "Counter"],
    ["detail.risk_table", "qual", "Risk"],
    ["detail.confidence_gauge", "availability", "Confidence"],
    ["detail.freshness_chip", "freshness", "Freshness"],
    ["detail.outcome_card", "qual", "Outcome"],
    ["detail.calibration_chart", "funding", "Calibration"],
  ]);

  const [variant, setVariant] = useState<DetailVariant>("demo_wait");
  const model = useMemo(() => buildDemoDecisionDetail(variant), [variant]);

  return (
    <MemberPageChrome
      titleKey="pages.detail.title"
      subtitle="Decision Detail · Learning Transparency · no private graph / thresholds / CoT"
    >
      <div className="member-detail-toolbar">
        <label htmlFor="member-detail-variant">
          Transparency fixture
          <select
            id="member-detail-variant"
            value={variant}
            onChange={(e) => setVariant(e.target.value as DetailVariant)}
            data-testid="detail-variant-select"
          >
            <option value="demo_wait">DEMO WAIT</option>
            <option value="demo_abstain">FIXTURE ABSTAIN</option>
            <option value="stale">STALE</option>
            <option value="provider_required">PROVIDER_REQUIRED</option>
            <option value="unavailable">UNAVAILABLE</option>
          </select>
        </label>
      </div>

      <DecisionDetailTransparency model={model} />

      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
    </MemberPageChrome>
  );
}
