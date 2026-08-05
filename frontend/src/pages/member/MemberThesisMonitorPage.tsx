import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberThesisMonitorPage() {
  const { loading, items } = usePageSlots([
    ["thesis.monitor_table", "freshness", "Monitor freshness"],
    ["thesis.status_chip", "availability", "Status"],
    ["thesis.drift_card", "reflection", "Reflection V2.3"],
    ["thesis.freshness_chip", "freshness", "Freshness chip"],
    ["thesis.status_chart", "btc", "Status chart"],
  ]);

  return (
    <MemberPageChrome
      title="Thesis Monitor"
      subtitle="Thesis Integrity Monitor · alert without auto-trading"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Thesis monitor rows UNAVAILABLE - no synthetic live theses" />
    </MemberPageChrome>
  );
}
