import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberDecisionMemoryPage() {
  const { loading, items } = usePageSlots([
    ["memory.decision_table", "availability", "Memory availability"],
    ["memory.summary_card", "freshness", "Summary"],
    ["memory.freshness_chip", "freshness", "Freshness"],
    ["memory.timeline_chart", "btc", "Timeline"],
  ]);

  return (
    <MemberPageChrome
      titleKey="pages.memory.title"
      subtitleKey="pages.memory.subtitle"

    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Decision memory UNAVAILABLE - no synthetic live history" />
    </MemberPageChrome>
  );
}
