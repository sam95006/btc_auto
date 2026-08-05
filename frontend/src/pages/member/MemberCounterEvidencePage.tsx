import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberCounterEvidencePage() {
  const { loading, items } = usePageSlots([
    ["counter.list_table", "freshness", "Counter freshness"],
    ["counter.summary_card", "availability", "Summary"],
    ["counter.polarity_chip", "availability", "Polarity"],
    ["counter.freshness_chip", "freshness", "Freshness chip"],
  ]);

  return (
    <MemberPageChrome
      title="Counter Evidence"
      subtitle="Contradicting evidence · required honesty surface"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Counter-evidence rows UNAVAILABLE - no synthetic live rows" />
    </MemberPageChrome>
  );
}
