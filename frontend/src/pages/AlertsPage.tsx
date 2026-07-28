import { Link } from "react-router-dom";
import { useMemo } from "react";
import { MarketAnomaliesPanel } from "../components/MarketAnomaliesPanel";
import { DemoDataBadge } from "../components/DemoDataBadge";
import { SignalStatusBadge } from "../components/SignalStatusBadge";
import { getSignals } from "../demo/nexusDataAdapter";
import { useMarketAnomalies } from "../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../market/useMarketScanner";

/**
 * Wave 4 Alerts — anomalies + signals + risk in one workspace.
 */
export function AlertsPage() {
  const anomalies = useMarketAnomalies();
  const { longs, shorts, status } = useMarketScannerOverview();
  const signals = getSignals();

  const riskAlerts = useMemo(() => {
    return [...longs, ...shorts]
      .filter((c) => c.riskScore >= 70 || c.stage === "OVEREXTENDED")
      .slice(0, 8)
      .map((c) => ({
        id: `risk-${c.id}`,
        symbol: c.symbol,
        text: `${c.symbol.replace("USDT", "")} · 風險 ${Math.round(c.riskScore)} · ${c.stage}`,
        href: `/market/${c.symbol}`,
      }));
  }, [longs, shorts]);

  const activeAnom = anomalies.filter(
    (a) => a.status === "NEW" || a.status === "ACTIVE",
  ).length;

  return (
    <div className="page-stack nx-alerts-w4">
      <header>
        <h1>警報</h1>
        <p className="muted">
          異常 · 訊號 · 風險 — Shadow 觀察 · 非下單介面
        </p>
        <div className="nx-ov-meta">
          <Link to="/anomalies">異常中心</Link>
          <Link to="/signals">訊號列表</Link>
          <Link to="/risk-evidence">風險證據</Link>
        </div>
      </header>

      <section className="nx-card" aria-label="Alert summary">
        <div className="w4-funnel-grid">
          <div className="w4-funnel-step">
            <strong>{activeAnom || "NO_DATA"}</strong>
            <span>活躍異常</span>
          </div>
          <div className="w4-funnel-step">
            <strong>{signals.length || "NO_DATA"}</strong>
            <span>訊號列</span>
          </div>
          <div className="w4-funnel-step">
            <strong>{status?.highRiskCandidates ?? "NO_DATA"}</strong>
            <span>高風險候選</span>
          </div>
          <div className="w4-funnel-step">
            <strong>{riskAlerts.length || "NO_DATA"}</strong>
            <span>風險警報</span>
          </div>
        </div>
      </section>

      <section className="nx-card" aria-label="Risk alerts">
        <h2 className="nx-sec-title">風險警報</h2>
        {riskAlerts.length === 0 ? (
          <p className="muted">NO_DATA — 目前無高風險候選</p>
        ) : (
          <ul className="nx-p7-alerts">
            {riskAlerts.map((a) => (
              <li key={a.id}>
                <Link to={a.href}>{a.text}</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="nx-card" aria-label="Signals">
        <h2 className="nx-sec-title">訊號</h2>
        {signals.length === 0 ? (
          <p className="muted">NO_DATA</p>
        ) : (
          <div className="list-stack">
            {signals.slice(0, 6).map((s) => (
              <article key={s.id} className="panel-card compact">
                <div className="meta-row">
                  <strong>{s.symbol}</strong>
                  <DemoDataBadge />
                  <SignalStatusBadge status={s.status} />
                </div>
                <p className="muted sm">{s.reason}</p>
              </article>
            ))}
          </div>
        )}
        <Link to="/signals" className="nx-link">
          全部訊號 →
        </Link>
      </section>

      <section aria-label="Anomalies panel">
        <MarketAnomaliesPanel />
      </section>
    </div>
  );
}
