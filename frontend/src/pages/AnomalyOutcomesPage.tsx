import { AnomalyOutcomesPanel } from "../components/AnomalyOutcomesPanel";

/** /anomaly-outcomes — read-only research outcome tracking (MVP-22D). */
export function AnomalyOutcomesPage() {
  return (
    <div className="page-stack mi-page mvp22d-outcomes-page">
      <AnomalyOutcomesPanel />
    </div>
  );
}
