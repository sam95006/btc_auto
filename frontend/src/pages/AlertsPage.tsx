import { Link } from "react-router-dom";
import { useMemo } from "react";
import { useMarketAnomalies } from "../market/useMarketAnomalies";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { WatchStarButton } from "../components/WatchStarButton";
import { ANOMALY_TYPE_LABEL } from "../market/anomalyTypes";

type StreamItem = {
  id: string;
  what: string;
  why: string;
  asset: string;
  symbol?: string;
  href: string;
  time: string;
  ts: number;
};

function agoLabel(ts?: number | null) {
  if (!ts) return "—";
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return `${sec} 秒前`;
  if (sec < 3600) return `${Math.round(sec / 60)} 分鐘前`;
  return `${Math.round(sec / 3600)} 小時前`;
}

/**
 * V18.2.9 Alerts — chronological event stream (not another table / card wall).
 * Real anomalies + scanner events + risk candidates only — no fake alerts.
 */
export function AlertsPage() {
  const anomalies = useMarketAnomalies();
  const { longs, shorts, events, status } = useMarketScannerOverview();

  const stream = useMemo(() => {
    const items: StreamItem[] = [];

    for (const a of anomalies) {
      if (a.status !== "NEW" && a.status !== "ACTIVE" && a.status !== "COOLING") continue;
      items.push({
        id: `anom-${a.id}`,
        what: a.title || ANOMALY_TYPE_LABEL[a.type] || a.type,
        why: a.explanation || "市場結構出現需關注的變化",
        asset: a.symbol?.replace("USDT", "") || "—",
        symbol: a.symbol,
        href: a.symbol ? `/market/${a.symbol}` : "/alerts",
        time: agoLabel(a.lastSeenAt || a.observedAt),
        ts: a.lastSeenAt || a.observedAt || 0,
      });
    }

    for (const e of events) {
      items.push({
        id: `evt-${e.id}`,
        what: e.type || "掃描事件",
        why: e.explanation,
        asset: e.symbol.replace("USDT", ""),
        symbol: e.symbol,
        href: `/market/${e.symbol}`,
        time: agoLabel(e.timestamp),
        ts: e.timestamp || 0,
      });
    }

    for (const c of [...longs, ...shorts]) {
      if (!(c.riskScore >= 70 || c.stage === "OVEREXTENDED")) continue;
      items.push({
        id: `risk-${c.id}`,
        what: "風險條件升溫",
        why:
          c.stage === "OVEREXTENDED"
            ? "目前風險條件未通過 — 標的過熱／延伸"
            : `風險分數 ${Math.round(c.riskScore)} · 建議優先觀察而非進場`,
        asset: c.symbol.replace("USDT", ""),
        symbol: c.symbol,
        href: `/market/${c.symbol}`,
        time: agoLabel(c.lastUpdatedAt),
        ts: c.lastUpdatedAt || 0,
      });
    }

    items.sort((a, b) => b.ts - a.ts);
    const seen = new Set<string>();
    return items.filter((it) => {
      const key = `${it.asset}|${it.what}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [anomalies, events, longs, shorts]);

  return (
    <div className="v1829-alerts" data-testid="alerts-v1829" data-product-gen="v18_2_9">
      <header className="v1829-panel" style={{ marginBottom: 12 }}>
        <h1 className="v1829-page-title">警報</h1>
        <p className="v1829-page-sub" style={{ marginBottom: 8 }}>
          事件串流 · 發生了什麼／為何重要／標的／時間 · 非下單介面
        </p>
        <p className="muted" style={{ margin: 0, fontSize: "0.8125rem" }}>
          活躍串流 {stream.length}
          {status?.highRiskCandidates != null ? ` · 高風險候選 ${status.highRiskCandidates}` : ""}
          {status?.freshness ? ` · ${status.freshness}` : ""}
        </p>
      </header>

      {stream.length === 0 ? (
        <div className="v1829-panel">
          <p style={{ margin: 0, fontWeight: 600 }}>目前沒有新警報</p>
          <p className="muted" style={{ margin: "8px 0 0", fontSize: "0.875rem" }}>
            不會用假警報填空。可建立條件等待，或回到掃描器持續觀察。
          </p>
          <div className="v1829-action-strip">
            <Link to="/scanner" className="v1829-btn v1829-btn-primary">
              掃描全市場
            </Link>
            <Link to="/watchlist" className="v1829-btn v1829-btn-secondary">
              查看觀察清單
            </Link>
          </div>
        </div>
      ) : (
        <div className="v1829-alert-stream" role="feed" aria-label="警報事件串流">
          {stream.map((item) => (
            <article key={item.id} className="v1829-alert-item">
              <div>
                <p className="what">{item.what}</p>
                <p className="why">{item.why}</p>
              </div>
              <div className="asset mono">
                {item.symbol ? <Link to={item.href}>{item.asset}</Link> : item.asset}
              </div>
              <div className="time">{item.time}</div>
              <div className="v1829-alert-actions">
                <Link to={item.href} className="v1829-btn v1829-btn-tertiary">
                  查看
                </Link>
                {item.symbol ? <WatchStarButton symbol={item.symbol} /> : null}
                <Link to="/notification-settings" className="v1829-btn v1829-btn-tertiary">
                  調整警報
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
