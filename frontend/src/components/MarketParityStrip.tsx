import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fmtNum } from "../market/displayNull";
import { fetchAvgFundingMetric, type AvgFundingValue } from "../market/marketAvgFunding";
import { fetchMarketAvgRsiMetric, getMarketAvgRsiMetric, type AvgRsiValue } from "../market/marketAvgRsi";
import { pendingMetric, statusTag, statusTagColor, type ParityMetric } from "../market/parityContracts";
import { fearGreedProvider } from "../market/providers/fearGreedProvider";
import { altcoinSeasonProvider } from "../market/providers/altcoinSeasonProvider";
import { newsProvider } from "../market/providers/newsProvider";

/** Format ISO timestamp to short locale time, or dash if missing. */
function fmtAttempt(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function MetricCell({
  metric,
  compact,
}: {
  metric: ParityMetric<unknown>;
  compact?: boolean;
}) {
  const tag = statusTag(metric.status);
  const color = statusTagColor(metric.status);
  let valueText = "—";
  if (metric.status === "live" && metric.value != null) {
    const v = metric.value as Record<string, unknown>;
    if (typeof v.display === "string") valueText = v.display;
    else if (typeof v.avgRsi === "number") valueText = fmtNum(v.avgRsi, 1);
  } else if (metric.status === "stale" && metric.value != null) {
    const v = metric.value as Record<string, unknown>;
    if (typeof v.display === "string") valueText = `${v.display}（過期）`;
    else if (typeof v.avgRsi === "number") valueText = `${fmtNum(v.avgRsi, 1)}（過期）`;
  } else if (metric.status === "error") {
    valueText = "錯誤";
  }

  const tagClass =
    color === "ok"
      ? "tag tag-ok"
      : color === "err"
        ? "tag tag-err"
        : color === "muted"
          ? "tag"
          : "tag tag-warn";

  return (
    <div
      className={`nx-parity-cell nx-parity-${metric.status}`}
      aria-label={metric.label}
    >
      <div className="nx-parity-cell-head">
        <span className="nx-parity-label">{metric.label}</span>
        <span className={tagClass}>{tag}</span>
      </div>
      <div className="nx-parity-value mono">{valueText}</div>
      {!compact ? (
        <>
          <p className="muted sm nx-parity-fresh">{metric.freshness}</p>
          {metric.lastAttempted ? (
            <p className="muted sm">最後嘗試：{fmtAttempt(metric.lastAttempted)}</p>
          ) : null}
          {metric.coverageNote ? (
            <p className="muted sm nx-parity-coverage">{metric.coverageNote}</p>
          ) : null}
          {metric.sampleCount != null ? (
            <p className="muted sm">樣本 {metric.sampleCount}</p>
          ) : null}
          {metric.error ? (
            <p className="muted sm nx-parity-err">⚠ {metric.error}</p>
          ) : null}
        </>
      ) : (
        <p className="muted sm">{metric.freshness}</p>
      )}
    </div>
  );
}

/**
 * Product 7.2 parity strip — richer state rendering, STALE support,
 * lastAttempted visibility, coverage notes, mobile-friendly density.
 * Simple View: low density; Pro View: expands all provider details.
 */
export function MarketParityStrip({ expanded = false }: { expanded?: boolean }) {
  const [funding, setFunding] = useState<ParityMetric<AvgFundingValue>>(() => ({
    ...pendingMetric<AvgFundingValue>("市場平均 Funding", "scanner.candidates"),
    freshness: "載入中…",
  }));
  const [rsi, setRsi] = useState<ParityMetric<AvgRsiValue>>(() => getMarketAvgRsiMetric());
  const [fear, setFear] = useState<ParityMetric<unknown> | null>(null);
  const [alt, setAlt] = useState<ParityMetric<unknown> | null>(null);
  const [news, setNews] = useState<ParityMetric<unknown> | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const [f, r] = await Promise.all([fetchAvgFundingMetric(), fetchMarketAvgRsiMetric()]);
      if (!alive) return;
      setFunding(f);
      setRsi(r);
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
        <h2 className="nx-sec-title">
          {expanded ? "市場指標（Pro）" : "市場指標"}
        </h2>
        {!expanded ? (
          <span className="muted sm">低密度 · 缺值顯示 —</span>
        ) : (
          <Link to="/intelligence" className="nx-link">
            情報層 →
          </Link>
        )}
      </div>

      {/* RSI + Funding: always shown, fully live-derived */}
      <div className="nx-parity-grid">
        <MetricCell metric={rsi} compact={!expanded} />
        <MetricCell metric={funding} compact={!expanded} />
      </div>

      {/* External providers: only expanded; honest about PENDING/UNAVAILABLE */}
      {expanded ? (
        <>
          {fear || alt || news ? (
            <div className="nx-parity-grid nx-parity-grid-ext">
              {fear ? <MetricCell metric={fear} /> : null}
              {alt ? <MetricCell metric={alt} /> : null}
              {news ? <MetricCell metric={news} /> : null}
            </div>
          ) : (
            <p className="muted sm">外部指標載入中…</p>
          )}
          <p className="muted sm nx-parity-ext-note">
            Fear/Greed · Altcoin Season · News: PROVIDER_PENDING — 無外部數據源時顯示 UNAVAILABLE，不捏造數值。
          </p>
        </>
      ) : (
        <p className="muted sm nx-parity-simple-note">
          Fear/Greed · Altcoin Season · News: 僅在 Pro 頁展開，保持 Simple View 低密度。
        </p>
      )}

      {/* Coverage disclaimer for derived metrics */}
      {expanded && (
        <p className="muted sm nx-parity-coverage-note">
          RSI: BTC/ETH/SOL 5m rsi_14 平均（非全市場） · Funding: 掃描候選 fundingRate 平均（非全市場保證）
        </p>
      )}
    </section>
  );
}
