import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { ScannerPage } from "./ScannerPage";
import {
  cyclePreset,
  resolveColumnPreset,
  type ColumnPreset,
} from "../wave4/columnPresets";
import { saveViewMode, type ViewMode } from "../market/viewPrefs";
import { buildFunnelDisplay } from "../wave4/noDataFunnel";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { useRealShadowRuntime } from "../wave5/useRealShadowRuntime";

const PRESET_LABEL: Record<ColumnPreset, string> = {
  SIMPLE: "簡易",
  PRO: "專業",
  QUANT: "量化",
};

/**
 * Wave 4 Universe — wraps Scanner with funnel header + column presets.
 */
export function UniversePage() {
  const [preset, setPreset] = useState<ColumnPreset>(() => resolveColumnPreset());
  const { status, loading } = useMarketScannerOverview();
  const { status: shadowRt, hasRealData: hasShadowRt } = useRealShadowRuntime();

  useEffect(() => {
    const onView = (e: Event) => {
      const mode = (e as CustomEvent<ViewMode>).detail;
      if (mode === "simple") setPreset("SIMPLE");
      else if (mode === "advanced") setPreset("PRO");
    };
    window.addEventListener("nexus-view-mode", onView);
    return () => window.removeEventListener("nexus-view-mode", onView);
  }, []);

  const funnel = hasShadowRt
    ? buildFunnelDisplay(
        [
          { key: "symbols", label: "標的", value: shadowRt?.funnel?.marketsScanned },
          { key: "eligible", label: "合格", value: shadowRt?.funnel?.marketsEligible },
          { key: "candidates", label: "候選", value: shadowRt?.funnel?.candidatesGenerated },
          { key: "sixRole", label: "六角色", value: shadowRt?.funnel?.sixRoleReviewed },
          { key: "selected", label: "入選", value: shadowRt?.funnel?.portfolioSelected },
        ],
        true,
      )
    : buildFunnelDisplay(
        [
          { key: "symbols", label: "標的", value: status?.symbolCount },
          { key: "long", label: "做多", value: status?.longCandidates },
          { key: "short", label: "做空", value: status?.shortCandidates },
          { key: "confirmed", label: "確認", value: status?.confirmedCandidates },
          { key: "highRisk", label: "高風險", value: status?.highRiskCandidates },
        ],
        Boolean(status) && !loading,
      );

  const applyPreset = (next: ColumnPreset) => {
    setPreset(next);
    const mode: ViewMode = next === "SIMPLE" ? "simple" : "advanced";
    saveViewMode(mode);
    window.dispatchEvent(new CustomEvent("nexus-view-mode", { detail: mode }));
  };

  return (
    <div className="page-stack nx-universe-w4">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">全市場</h1>
        <p className="muted sm">
          Universe · {hasShadowRt ? "PUBLIC MARKET DATA · REAL SHADOW" : "Shadow 觀察"} · 非下單介面
        </p>
        <div className="nx-ov-meta">
          <Link to="/overview">← 總覽</Link>
          <Link to="/opportunities">機會</Link>
          <Link to="/crypto/sectors">版塊</Link>
        </div>
      </header>

      <section className="nx-card w4-universe-funnel" aria-label="Decision funnel">
        <h2 className="nx-sec-title">決策漏斗（掃描器）</h2>
        {!funnel.hasData ? (
          <p className="w4-no-data" aria-label="No funnel data">
            NO_DATA — 掃描器尚未回報漏斗計數
          </p>
        ) : (
          <div className="w4-funnel-grid">
            {funnel.stages.map((s) => (
              <div key={s.key} className="w4-funnel-step">
                <strong className="mono">{s.display}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}
        <p className="muted sm">不會使用合成預設值（128/24/6）</p>
      </section>

      <div className="w4-preset-bar" role="group" aria-label="Column preset">
        <span className="muted sm">欄位預設：</span>
        {(["SIMPLE", "PRO", "QUANT"] as ColumnPreset[]).map((p) => (
          <button
            key={p}
            type="button"
            className={preset === p ? "active" : undefined}
            aria-pressed={preset === p}
            onClick={() => applyPreset(p)}
          >
            {PRESET_LABEL[p]}
          </button>
        ))}
        <button
          type="button"
          className="nx-text-btn"
          onClick={() => applyPreset(cyclePreset(preset))}
        >
          循環
        </button>
        <span className="muted sm">顯示 {preset} 欄位組</span>
      </div>

      <ScannerPage columnPreset={preset} hideHeader />
    </div>
  );
}
