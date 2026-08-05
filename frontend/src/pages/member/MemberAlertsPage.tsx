import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberAlertsPage() {
  const { loading, items } = usePageSlots([
    ["alerts.notification_list", "capture", "Capture alerts"],
    ["alerts.severity_chip", "qual", "Severity"],
    ["alerts.kind_table", "runtime", "Runtime"],
    ["alerts.count_gauge", "ready_count", "Alert gauge"],
  ]);

  return (
    <MemberPageChrome
      title="Alerts"
      subtitle="Thesis · risk · freshness · outcome alerts · observation only"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Alert list UNAVAILABLE - no synthetic live alerts" />
    </MemberPageChrome>
  );
}
