import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

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

  return (
    <MemberPageChrome
      titleKey="pages.detail.title"
      subtitle="Public Decision Object · lineage-bound · no exchange controls"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Decision detail UNAVAILABLE - no synthetic live object" />
    </MemberPageChrome>
  );
}
