import { MemberPageChrome } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberAccountDeletionPage() {
  const { loading, items } = usePageSlots([
    ["deletion.request_card", "runtime", "Deletion runtime"],
    ["deletion.export_chip", "availability", "Export"],
  ]);

  return (
    <MemberPageChrome
      title="Account Deletion"
      subtitle="Request deletion / export · fail-closed until auth binds"
    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <p className="muted sm">Deletion mutation UNAVAILABLE - no synthetic live confirmation.</p>
    </MemberPageChrome>
  );
}
