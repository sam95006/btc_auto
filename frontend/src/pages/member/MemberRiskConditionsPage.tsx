import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberRiskConditionsPage() {
  const { loading, items } = usePageSlots([
    ["risk.conditions_table", "qual", "Qualification"],
    ["risk.open_gauge", "ready_count", "Ready count"],
    ["risk.severity_chip", "qual", "Severity"],
    ["risk.alert_notification", "capture", "Capture health"],
    ["risk.severity_chart", "event", "Event study"],
  ]);

  return (
    <MemberPageChrome
      titleKey="pages.risk.title"
      subtitleKey="pages.risk.subtitle"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Risk condition rows UNAVAILABLE - no synthetic live risks" />
    </MemberPageChrome>
  );
}
