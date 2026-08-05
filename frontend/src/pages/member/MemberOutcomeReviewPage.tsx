import { MemberPageChrome, EmptyState } from "../../member/MemberPageChrome";
import { LiveSlotStrip, usePageSlots } from "../../member/LiveSlotStrip";

export function MemberOutcomeReviewPage() {
  const { loading, items } = usePageSlots([
    ["outcome.review_table", "qual", "Qualification"],
    ["outcome.class_chip", "event", "Outcome class"],
    ["outcome.review_card", "reflection", "Review"],
    ["outcome.class_chart", "ready_count", "Class chart"],
  ]);

  return (
    <MemberPageChrome
      titleKey="pages.outcome.title"
      subtitleKey="pages.outcome.subtitle"

    >
      {loading ? <p className="muted">Loading live bindings...</p> : null}
      <LiveSlotStrip bindings={items} />
      <EmptyState label="Outcome review rows UNAVAILABLE - no synthetic live outcomes" />
    </MemberPageChrome>
  );
}
