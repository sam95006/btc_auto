import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { buildMarketSummary, deriveRegime } from "../market/marketSummary";
import { buildAiDailyBrief } from "../market/aiDailyBrief";

type PromptId =
  | "explain_page"
  | "find_long"
  | "find_short"
  | "explain_risk"
  | "daily_brief"
  | "why_blocked"
  | "market_pulse"
  | "portfolio_summary"
  | "alert_digest"
  | "symbol_context"
  | "learning_hint";

type AiAnswer = {
  mode: "RULE_BASED_SUMMARY" | "rules-only" | "unavailable";
  conclusion: string;
  evidence: string[];
  contradictingEvidence: string[];
  risk: string;
  invalidation: string;
  freshness: string;
  decisionTrace: string;
};

type PromptDef = { id: PromptId; label: string };

function promptsForPath(pathname: string): PromptDef[] {
  const base: PromptDef[] = [
    { id: "explain_page", label: "解釋此頁" },
    { id: "market_pulse", label: "市場怎麼了" },
    { id: "explain_risk", label: "目前風險" },
  ];
  if (pathname.includes("/opportunities")) {
    return [
      ...base,
      { id: "why_blocked", label: "為何未通過" },
      { id: "find_long", label: "做多候選" },
      { id: "find_short", label: "做空候選" },
    ];
  }
  if (pathname.includes("/scanner")) {
    return [
      ...base,
      { id: "why_blocked", label: "為何被擋" },
      { id: "symbol_context", label: "如何讀列" },
    ];
  }
  if (pathname.includes("/alerts")) {
    return [
      ...base,
      { id: "alert_digest", label: "警報摘要" },
      { id: "explain_risk", label: "風險優先" },
    ];
  }
  if (pathname.includes("/intelligence")) {
    return [
      ...base,
      { id: "daily_brief", label: "研究簡報" },
      { id: "symbol_context", label: "標的上下文" },
    ];
  }
  if (pathname.includes("/market/")) {
    return [
      { id: "symbol_context", label: "標的上下文" },
      { id: "explain_risk", label: "目前風險" },
      { id: "why_blocked", label: "失效／阻擋" },
      { id: "market_pulse", label: "市場怎麼了" },
    ];
  }
  if (pathname.includes("/overview") || pathname === "/") {
    return [
      { id: "daily_brief", label: "今日簡報" },
      { id: "market_pulse", label: "市場怎麼了" },
      { id: "explain_risk", label: "需要注意" },
      { id: "why_blocked", label: "為何沒機會" },
    ];
  }
  return [
    ...base,
    { id: "daily_brief", label: "今日簡報" },
    { id: "alert_digest", label: "警報摘要" },
  ];
}

function detectLlmAvailable(): boolean {
  return false;
}

/**
 * V18.2.9 UX — small command / contextual analyst drawer.
 * No glowing orb · context-aware prompts · Chinese-first · analyst not mascot.
 */
export function AiCommander() {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<PromptId>("daily_brief");
  const loc = useLocation();
  const { status, longs, shorts, loading } = useMarketScannerOverview();
  const llm = detectLlmAvailable();
  const prompts = useMemo(() => promptsForPath(loc.pathname), [loc.pathname]);

  useEffect(() => {
    const onOpen = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail === "summary") setActive("daily_brief");
      setOpen(true);
    };
    window.addEventListener("nexus-open-ai", onOpen);
    return () => window.removeEventListener("nexus-open-ai", onOpen);
  }, []);

  useEffect(() => {
    if (!prompts.some((p) => p.id === active)) {
      setActive(prompts[0]?.id ?? "daily_brief");
    }
  }, [prompts, active]);

  const answer: AiAnswer = useMemo(() => {
    const regime = deriveRegime({
      longCandidates: status?.longCandidates,
      shortCandidates: status?.shortCandidates,
      confirmedCandidates: status?.confirmedCandidates,
      highRiskCandidates: status?.highRiskCandidates,
      breadth: status?.breadth,
      symbolCount: status?.symbolCount,
      freshness: status?.freshness,
    });
    const summary = buildMarketSummary({
      longCandidates: status?.longCandidates,
      shortCandidates: status?.shortCandidates,
      confirmedCandidates: status?.confirmedCandidates,
      highRiskCandidates: status?.highRiskCandidates,
      breadth: status?.breadth,
      symbolCount: status?.symbolCount,
      freshness: status?.freshness,
    });
    const topL = longs[0];
    const topS = shorts[0];
    const freshness = status?.freshness || "更新時間未知";

    if (!llm) {
      const baseMeta = {
        mode: "RULE_BASED_SUMMARY" as const,
        freshness,
        decisionTrace: "規則引擎 · 尚未配置 LLM",
        invalidation: "研究模式 · 無下單權限",
      };

      if (loading && !status) {
        return {
          ...baseMeta,
          mode: "unavailable" as const,
          conclusion: "掃描器資料尚未就緒，無法產生可靠簡報。",
          evidence: [],
          contradictingEvidence: [],
          risk: "資料不足",
        };
      }

      switch (active) {
        case "explain_page":
          return {
            ...baseMeta,
            conclusion: `目前頁面：${loc.pathname}。這是研究介面，不是交易終端。`,
            evidence: [summary, `市場狀態：${regime}`],
            contradictingEvidence: ["規則引擎無法解讀頁面私有上下文以外的內容"],
            risk: "勿把介面說明當成投資建議",
          };
        case "find_long":
          return {
            ...baseMeta,
            conclusion: topL
              ? `規則摘要：最高做多候選 ${topL.symbol.replace("USDT", "")}（機會 ${Math.round(topL.opportunityScore)}）`
              : "目前沒有可列出的做多候選",
            evidence: topL?.reasons?.slice(0, 3) || [],
            contradictingEvidence: topL?.conflicts?.slice(0, 3) || [],
            risk: topL ? `風險分數 ${Math.round(topL.riskScore)}` : "無候選",
          };
        case "find_short":
          return {
            ...baseMeta,
            conclusion: topS
              ? `規則摘要：最高做空候選 ${topS.symbol.replace("USDT", "")}（機會 ${Math.round(topS.opportunityScore)}）`
              : "目前沒有可列出的做空候選",
            evidence: topS?.reasons?.slice(0, 3) || [],
            contradictingEvidence: topS?.conflicts?.slice(0, 3) || [],
            risk: topS ? `風險分數 ${Math.round(topS.riskScore)}` : "無候選",
          };
        case "explain_risk":
          return {
            ...baseMeta,
            conclusion: `高風險／過熱標的：${status?.highRiskCandidates ?? "尚無資料"}；Shadow 固定 25x · 最多 2 倉。`,
            evidence: ["風險閘與 shadow 政策由後端治理，前端只讀顯示"],
            contradictingEvidence: [],
            risk: "前端不會覆寫槓桿／保證金／倉位上限",
          };
        case "why_blocked":
          return {
            ...baseMeta,
            conclusion: "現在不能交易：研究／紙上模式、無 ARM、無實盤下單。",
            evidence: ["private_api=false", "real_order=false", "介面無下單控件"],
            contradictingEvidence: [],
            risk: "任何看似可交易的狀態僅為觀察用語",
          };
        case "market_pulse":
          return {
            ...baseMeta,
            conclusion: summary || "市場脈動尚未就緒",
            evidence: [
              `做多 ${status?.longCandidates ?? "—"} · 做空 ${status?.shortCandidates ?? "—"}`,
              `已確認 ${status?.confirmedCandidates ?? "—"}`,
            ],
            contradictingEvidence: [],
            risk: `偏向 ${regime}`,
          };
        case "portfolio_summary":
          return {
            ...baseMeta,
            conclusion: "Shadow 投資組合：固定 25x 標籤 · 最多 2 持倉 · 無實盤操作",
            evidence: ["詳見 /portfolio"],
            contradictingEvidence: [],
            risk: "非帳戶真實槓桿",
          };
        case "alert_digest":
          return {
            ...baseMeta,
            conclusion: `高風險候選 ${status?.highRiskCandidates ?? "尚無資料"} · 詳見警報串流`,
            evidence: ["異常 + 訊號 + 風險合併於警報頁"],
            contradictingEvidence: [],
            risk: "警報為觀察用途",
          };
        case "symbol_context": {
          const symMatch = loc.pathname.match(/\/market\/([^/]+)/);
          const sym = symMatch?.[1]?.replace("USDT", "") || "—";
          return {
            ...baseMeta,
            conclusion: symMatch
              ? `標的工作台：${sym} · 使用分頁檢視結構／風險／證據`
              : loc.pathname.includes("/scanner")
                ? "掃描列：點列開上下文，再進決策工作區或深入分析"
                : "請開啟標的頁以取得標的上下文",
            evidence: [],
            contradictingEvidence: [],
            risk: "—",
          };
        }
        case "learning_hint":
          return {
            ...baseMeta,
            conclusion: "學習中心連結 Academy 與 AI Learning Lab",
            evidence: ["/learning", "/ai-learning-lab", "/academy"],
            contradictingEvidence: [],
            risk: "教育內容非投資建議",
          };
        case "daily_brief":
        default: {
          const brief = buildAiDailyBrief({
            pulse: {
              longCandidates: status?.longCandidates,
              shortCandidates: status?.shortCandidates,
              confirmedCandidates: status?.confirmedCandidates,
              highRiskCandidates: status?.highRiskCandidates,
              breadth: status?.breadth,
              symbolCount: status?.symbolCount,
              freshness: status?.freshness,
            },
            longs,
            shorts,
            loading,
            llmAvailable: false,
          });
          return {
            mode: "RULE_BASED_SUMMARY",
            conclusion: brief.conclusion,
            evidence: brief.evidence,
            contradictingEvidence: brief.contradictingEvidence,
            risk: brief.risk,
            invalidation: brief.invalidation,
            freshness: brief.freshness,
            decisionTrace: brief.decisionTrace,
          };
        }
      }
    }

    return {
      mode: "unavailable",
      conclusion: "AI 供應商不可用",
      evidence: [],
      contradictingEvidence: [],
      risk: "—",
      invalidation: "—",
      freshness,
      decisionTrace: "—",
    };
  }, [active, llm, loading, loc.pathname, longs, shorts, status]);

  const modeLabel =
    answer.mode === "RULE_BASED_SUMMARY"
      ? "規則摘要"
      : answer.mode === "rules-only"
        ? "僅規則"
        : "不可用";

  return (
    <div className="floating-ai nx-ai-commander-w4 v1829-ai" aria-label="NEX AI 分析助手">
      {open ? (
        <div className="floating-ai-panel panel-card nx-ai-p7 v1829-ai-panel" role="dialog" aria-label="NEX AI">
          <div className="floating-ai-head">
            <strong>NEX AI</strong>
            <span className="v1829-ai-mode">{modeLabel}</span>
            <button type="button" className="v1829-btn v1829-btn-tertiary" onClick={() => setOpen(false)}>
              關閉
            </button>
          </div>
          <p className="muted sm" style={{ margin: "0 0 10px" }}>
            情境分析 · 無 LLM 時不捏造 · 非投資建議
          </p>
          <div className="copilot-prompt-grid">
            {prompts.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`copilot-prompt-btn${active === p.id ? " active" : ""}`}
                onClick={() => setActive(p.id)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="nx-ai-answer-frame v1829-ai-answer">
            <h4>結論</h4>
            <p>{answer.conclusion}</p>
            <h4>支持</h4>
            <ul>
              {answer.evidence.length ? answer.evidence.map((e) => <li key={e}>{e}</li>) : <li className="muted">—</li>}
            </ul>
            <h4>反對</h4>
            <ul>
              {answer.contradictingEvidence.length ? (
                answer.contradictingEvidence.map((e) => (
                  <li key={e} className="conflict">
                    {e}
                  </li>
                ))
              ) : (
                <li className="muted">—</li>
              )}
            </ul>
            <h4>風險</h4>
            <p>{answer.risk}</p>
            <h4>失效</h4>
            <p>{answer.invalidation}</p>
            <h4>新鮮度</h4>
            <p>{answer.freshness}</p>
            <h4>決策軌跡</h4>
            <p className="mono sm">{answer.decisionTrace}</p>
          </div>
          <Link to="/assistant" className="nx-link sm">
            完整助理頁 →
          </Link>
        </div>
      ) : null}
      <button
        type="button"
        className="floating-ai-fab v1829-ai-fab"
        aria-expanded={open}
        aria-label="開啟 NEX AI 分析"
        onClick={() => setOpen((v) => !v)}
        title="NEX AI 分析"
      >
        分析
      </button>
    </div>
  );
}
