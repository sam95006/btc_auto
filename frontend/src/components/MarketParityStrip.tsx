import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fmtNum } from "../market/displayNull";
import { fetchAvgFundingMetric, type AvgFundingValue } from "../market/marketAvgFunding";
import { getMarketAvgRsiMetric, type AvgRsiValue } from "../market/marketAvgRsi";
import { pendingMetric, statusTag, type ParityMetric } from "../market/parityContracts";
import { fearGreedProvider } from "../market/providers/fearGreedProvider";
import { altcoinSeasonProvider } from "../market/providers/altcoinSeasonProvider";
import { newsProvider } from "../market/providers/newsProvider";

function MetricCell({
  metric,
  compact,
}: {
  metric: ParityMetric<unknown>;
  compact?: boolean;
}) {
  const tag = statusTag(metric.status);
  let valueText = "—";
  if (metric.status === "live" && metric.value != null) {
    const v = metric.value as Record<string, unknown>;
    if (typeof v.display === "string") valueText = v.display;
    else if (typeof v.avgRsi === "number") valueText = fmtNum(v.avgRsi, 1);
  } else if (metric.status === "error") {
    valueText = "錯誤";
  }

  return (
    <div className={`nx-parity-cell nx-parity-${metric.status}`} aria-label={metric.label}>
      <div className="nx-parity-cell-head">
        <span className="nx-parity-label">{metric.label}</span>
        <span className={`tag ${metric.status === "live" ? "" : "tag-warn"}`}>{tag}</span>
      </div>
      <div className="nx-parity-value mono">{valueText}</div>
      {!compact ? (
        <>
          <p className="muted sm">{metric.freshness}</p>
          {metric.coverageNote ? <p className="muted sm">{metric.coverageNote}</p> : null}
          {metric.sampleCount != null ? (
            <p className="muted sm">樣本 {metric.sampleCount}</p>
          ) : null}
          {metric.error ? <p className="muted sm">error: {metric.error}</p> : null}
        </>
      ) : (
        <p className="muted sm">{metric.freshness}</p>
      )}
    </div>
  );
}

/**
 * Product 7.1 parity strip — Simple keeps low density; Pro expands pending providers.
 */
export function MarketParityStrip({ expanded = false }: { expanded?: boolean }) {
  const [funding, setFunding] = useState<ParityMetric<AvgFundingValue>>(() => ({
    ...pendingMetric<AvgFundingValue>("市場平均 Funding", "scanner.candidates"),
    freshness: "載入中…",
  }));
  const [rsi] = useState<ParityMetric<AvgRsiValue>>(() => getMarketAvgRsiMetric());
  const [fear, setFear] = useState<ParityMetric<unknown> | null>(null);
  const [alt, setAlt] = useState<ParityMetric<unknown> | null>(null);
  const [news, setNews] = useState<ParityMetric<unknown> | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const f = await fetchAvgFundingMetric();
      if (alive) setFunding(f);
      if (expanded) {
        const [fg, as, nw] = await Promise.all([
          fearGreedProvider.getIndex(),
          altcoinSeasonProvider.getIndex(),
          newsProvider.getHeadlines(5),
        ]);
        if (!alive) return;
        setFear(fg);
        setAlt(as);
        setNews(nw);
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 20_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [expanded]);

  return (
    <section
      className={`nx-parity-strip ${expanded ? "nx-parity-expanded" : "nx-parity-compact"}`}
      aria-label="Parity market metrics"
    >
      <div className="nx-tops-head">
        <h2 className="nx-sec-title">{expanded ? "市場指標（Pro）" : "市場指標"}</h2>
        {!expanded ? (
          <span className="muted sm">低密度 · 缺值顯示 —</span>
        ) : (
          <Link to="/intelligence" className="nx-link">
            情報層 →
          </Link>
        )}
      </div>
      <div className="nx-parity-grid">
        <MetricCell metric={rsi} compact={!expanded} />
        <MetricCell metric={funding} compact={!expanded} />
        {expanded && fear ? <MetricCell metric={fear} /> : null}
        {expanded && alt ? <MetricCell metric={alt} /> : null}
        {expanded && news ? <MetricCell metric={news} /> : null}
      </div>
      {!expanded ? (
        <p className="muted sm">
          Fear/Greed、Altcoin Season、News 僅在 Pro／情報頁以 PENDING 顯示，不捏造數值。
        </p>
      ) : null}
    </section>
  );
}
