/**
 * "什麼值得注意" — attention/risk intelligence. Original NEXUS format (NOT
 * long/short recommendation cards). Each card is DERIVED from the real backend
 * volatility/range bands for that symbol — never a fabricated signal. Symbols
 * without a supporting backend band render as "穩定 / stable".
 */
import { useMarket } from "../../context/MarketContext";
import { symOf } from "../../lib/format";
import type { MarketSymbol } from "../../types";

function assess(s: MarketSymbol): { level: string; sev: "high" | "medium" | "info"; text: string } {
  if (s.availability !== "READY") return { level: "資料不可用", sev: "info", text: "暫無即時資料" };
  if (s.volatility === "high") return { level: "高度關注", sev: "high", text: "波動偏高，走勢較不穩定" };
  if (typeof s.range_pct === "number" && s.range_pct >= 6) return { level: "留意", sev: "medium", text: "24H 區間正在擴大" };
  if (s.volatility === "moderate") return { level: "中度關注", sev: "medium", text: "波動維持中等" };
  return { level: "穩定", sev: "info", text: "波動與區間受控" };
}

export function AttentionPanel() {
  const m = useMarket();
  if (m.status !== "READY") {
    return <div className="corp-fs-loading" role="status">{m.status === "LOADING" ? "分析市場關注度…" : "關注度資料暫不可用"}</div>;
  }
  return (
    <div className="corp-fs-attn" data-testid="attention-panel">
      {m.data.symbols.map((s) => {
        const a = assess(s);
        return (
          <div className="corp-fs-attn-card" key={s.symbol} data-sev={a.sev}>
            <div className="s">{symOf(s.symbol)}<span style={{ color: "var(--fs-muted-2)", fontWeight: 400 }}>  {a.level}</span></div>
            <div className="t">{a.text}</div>
            <div className="m">來源 · {s.source || "binance_usdm_public"}</div>
          </div>
        );
      })}
    </div>
  );
}
