import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberDecisionFeedPage() {
  const { loading, items } = usePageSlots([
    ["decisions.feed_table", "availability", "Decision cloud"],
    ["decisions.feed_table", "freshness", "Feed freshness"],
    ["decisions.summary_card", "availability", "Summary"],
    ["decisions.posture_chip", "availability", "Posture"],
    ["decisions.confidence_gauge", "freshness", "Confidence"],
    ["decisions.freshness_chip", "freshness", "Freshness chip"],
    ["decisions.posture_chart", "btc", "BTC context"],
  ]);

  return (
    <MemberPageChrome
      title="Decision Feed"
      subtitle="Atomic Decision Objects · record intent · never place exchange orders"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Decision Object list UNAVAILABLE - no synthetic live rows" />
    </MemberPageChrome>
  );
}
