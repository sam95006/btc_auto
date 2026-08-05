import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberEvidencePage() {
  const { loading, items } = usePageSlots([
    ["evidence.list_table", "freshness", "Evidence freshness"],
    ["evidence.summary_card", "availability", "Summary"],
    ["evidence.polarity_chip", "availability", "Polarity"],
    ["evidence.freshness_chip", "freshness", "Freshness chip"],
    ["evidence.polarity_chart", "btc", "Polarity chart"],
  ]);

  return (
    <MemberPageChrome title="Evidence" subtitle="Supporting evidence · cited · no invention policy">
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Evidence rows UNAVAILABLE - no synthetic live citations" />
    </MemberPageChrome>
  );
}
