/**
 * "What needs attention" — original NEXUS format (NOT long/short recommendation
 * cards). Each card is DERIVED from the real backend volatility/range bands for
 * that symbol — never a fabricated signal. Localized; unavailable is explicit.
 */
import { useMarket } from "../../context/MarketContext";
import { useLocale, type Locale } from "../../i18n";
import { symOf } from "../../lib/format";
import type { MarketSymbol } from "../../types";

const TXT: Record<Locale, { high: string; range: string; mod: string; stable: string; na: string }> = {
  "zh-TW": { high: "波動偏高，走勢較不穩定", range: "24H 區間正在擴大", mod: "波動維持中等", stable: "波動與區間受控", na: "暫無即時資料" },
  "en-US": { high: "Elevated volatility, less stable", range: "24H range is expanding", mod: "Volatility is moderate", stable: "Volatility and range are contained", na: "No live data" },
  "ja-JP": { high: "ボラティリティが高く不安定", range: "24H レンジが拡大中", mod: "ボラティリティは中程度", stable: "ボラティリティとレンジは抑制", na: "ライブデータなし" },
  "ko-KR": { high: "높은 변동성, 불안정", range: "24H 범위 확대 중", mod: "변동성 보통", stable: "변동성과 범위 통제", na: "실시간 데이터 없음" },
};

function assess(s: MarketSymbol, loc: Locale, t: (k: string) => string): { level: string; sev: "high" | "medium" | "info"; text: string } {
  const x = TXT[loc];
  if (s.availability !== "READY") return { level: t("st_unavailable"), sev: "info", text: x.na };
  if (s.volatility === "high") return { level: t("attn_high"), sev: "high", text: x.high };
  if (typeof s.range_pct === "number" && s.range_pct >= 6) return { level: t("attn_med"), sev: "medium", text: x.range };
  if (s.volatility === "moderate") return { level: t("attn_watch"), sev: "medium", text: x.mod };
  return { level: t("st_stable"), sev: "info", text: x.stable };
}

export function AttentionPanel() {
  const m = useMarket();
  const { locale, t } = useLocale();
  if (m.status !== "READY") {
    return <div className="corp-fs-loading" role="status">{m.status === "LOADING" ? t("st_loading") : t("st_unavailable")}</div>;
  }
  return (
    <div className="corp-fs-attn" data-testid="attention-panel">
      {m.data.symbols.map((s) => {
        const a = assess(s, locale, t);
        return (
          <div className="corp-fs-attn-card" key={s.symbol} data-sev={a.sev}>
            <div className="s">{symOf(s.symbol)}<span style={{ color: "var(--fs-muted-2)", fontWeight: 400 }}>  {a.level}</span></div>
            <div className="t">{a.text}</div>
            <div className="m">Source · {s.source || "binance_usdm_public"}</div>
          </div>
        );
      })}
    </div>
  );
}
