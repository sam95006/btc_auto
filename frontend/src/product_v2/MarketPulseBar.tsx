import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useLiveMarketFeed } from "../market/useLiveMarketFeed";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { deriveRegime } from "../market/marketSummary";
import { memberDataTrustLabel } from "../market/marketMetricFunnel";
import { mapMarketFreshnessDisplay } from "../market/dataTruthFreshness";
import { MetricSpark } from "./MetricSpark";

const PULSE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] as const;

function fmtPrice(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
  if (n >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function fmtPct(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

/**
 * Persistent MARKET PULSE under global nav — real ticker data + live spark.
 */
export function MarketPulseBar() {
  const feed = useLiveMarketFeed();
  const { status, longs, shorts, loading, error } = useMarketScannerOverview();
  const [flash, setFlash] = useState<Record<string, "up" | "down" | "">>({});
  const prev = useRef<Record<string, number>>({});
  const sparkBuf = useRef<Record<string, number[]>>({});
  const [, tick] = useState(0);

  useEffect(() => {
    const nextFlash: Record<string, "up" | "down" | ""> = {};
    let sparkChanged = false;
    for (const sym of PULSE_SYMBOLS) {
      const px = feed.bySymbol[sym]?.lastPrice ?? feed.bySymbol[sym]?.markPrice;
      if (px == null || !Number.isFinite(px)) continue;
      const p = prev.current[sym];
      if (p != null && px !== p) {
        nextFlash[sym] = px > p ? "up" : "down";
      }
      prev.current[sym] = px;
      const arr = sparkBuf.current[sym] ?? [];
      if (arr[arr.length - 1] !== px) {
        arr.push(px);
        if (arr.length > 20) arr.shift();
        sparkBuf.current[sym] = arr;
        sparkChanged = true;
      }
    }
    if (sparkChanged) tick((n) => n + 1);
    if (Object.keys(nextFlash).length) {
      setFlash((f) => ({ ...f, ...nextFlash }));
      const t = window.setTimeout(() => {
        setFlash((f) => {
          const cleared = { ...f };
          for (const k of Object.keys(nextFlash)) cleared[k] = "";
          return cleared;
        });
      }, 320);
      return () => window.clearTimeout(t);
    }
  }, [feed.bySymbol]);

  const pulse = {
    longCandidates: status?.longCandidates,
    shortCandidates: status?.shortCandidates,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    breadth: status?.breadth,
    symbolCount: status?.symbolCount,
    freshness: status?.freshness,
  };
  const regime = loading && !status ? "—" : deriveRegime(pulse);
  const breadth = status?.breadth
    ? `升 ${status.breadth.rising}／降 ${status.breadth.falling}／中性 ${status.breadth.neutral}`
    : "—";
  const fresh = mapMarketFreshnessDisplay(status?.freshness, {
    wsConnected: status?.wsConnected,
    lastError: status?.lastError ?? error,
    source: status?.source,
  });
  const trust = memberDataTrustLabel({
    scannerFreshness: error ? "DEGRADED" : status?.freshness,
    confirmedCandidates: status?.confirmedCandidates,
    highRiskCandidates: status?.highRiskCandidates,
    wsConnected: status?.wsConnected,
    lastError: status?.lastError,
  }).label_zh;

  void longs;
  void shorts;

  return (
    <div className="mp2-pulse-bar" data-testid="market-pulse-bar" aria-label="市場脈動">
      {PULSE_SYMBOLS.map((sym) => {
        const row = feed.bySymbol[sym];
        const px = row?.lastPrice ?? row?.markPrice;
        const ch = row?.change24hPct;
        const fl = flash[sym];
        return (
          <Link
            key={sym}
            to={`/market/${sym}`}
            className={`mp2-pulse-item${fl === "up" ? " flash-up" : fl === "down" ? " flash-down" : ""}`}
            data-symbol={sym}
          >
            <span className="sym">{sym.replace("USDT", "")}</span>
            <span className="px mono">{fmtPrice(px)}</span>
            <span className={`ch mono ${(ch ?? 0) >= 0 ? "pos" : "neg"}`}>{fmtPct(ch)}</span>
            <MetricSpark values={sparkBuf.current[sym] ?? []} positive={(ch ?? 0) >= 0} width={48} height={18} />
          </Link>
        );
      })}
      <div className="mp2-pulse-item">
        <span className="sym">廣度</span>
        <span className="px" style={{ fontSize: "0.75rem" }}>
          {breadth}
        </span>
      </div>
      <div className="mp2-pulse-item">
        <span className="sym">Regime</span>
        <span className={`px${regime.includes("多") ? " pos" : regime.includes("空") ? " neg" : ""}`}>
          {regime}
        </span>
      </div>
      <div className="mp2-pulse-item mp2-pulse-status" title={trust}>
        <span className="sym">資料</span>
        <span className="px">{fresh.label}</span>
      </div>
    </div>
  );
}
