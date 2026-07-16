import { MarketAnomaliesPanel } from "../components/MarketAnomaliesPanel";

/** /anomalies — read-only market anomaly radar (MVP-22C). */
export function AnomaliesPage() {
  return (
    <div className="page-stack mi-page mvp22c-anomalies-page">
      <MarketAnomaliesPanel />
    </div>
  );
}
