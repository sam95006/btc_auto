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

/** Contextual prompts — not a dominant "Ask AI anything" demo wall. */
const PROMPTS: { id: PromptId; label: string }[] = [
  { id: "explain_page", label: "解釋此頁" },
  { id: "market_pulse", label: "市場怎麼了" },
  { id: "explain_risk", label: "目前風險" },
  { id: "why_blocked", label: "為何未通過" },
  { id: "symbol_context", label: "標的上下文" },
  { id: "alert_digest", label: "警報摘要" },
];

function detectLlmAvailable(): boolean {
  return false;
}

/**
 * Wave 4 single AI instance — FAB + drawer.
 * RULE_BASED_SUMMARY when no LLM provider configured.
 */
export function AiCommander() {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<PromptId>("daily_brief");
  const loc = useLocation();
  const { status, longs, shorts, loading } = useMarketScannerOverview();
  const llm = detectLlmAvailable();

  useEffect(() => {
    const onOpen = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail === "summary") setActive("daily_brief");
      setOpen(true);
    };
    window.addEventListener("nexus-open-ai", onOpen);
    return () => window.removeEventListener("nexus-open-ai", onOpen);
  }, []);

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
        decisionTrace: "rules-engine · no LLM provider configured",
        invalidation: "研究模式 · 無下單權限 · Stage 4.19 blocked",
      };

      if (loading && !status) {
        return {
          ...baseMeta,
          mode: "unavailable",
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
            risk: "勿把 UI 說明當成投資建議",
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
            conclusion: `高風險／過熱標的：${status?.highRiskCandidates ?? "NO_DATA"}；Shadow 固定 25x · max 2 倉。`,
            evidence: ["Risk Gate 與 shadow policy 由後端治理，前端只讀顯示"],
            contradictingEvidence: [],
            risk: "前端不會覆寫 leverage／margin／position 上限",
          };
        case "why_blocked":
          return {
            ...baseMeta,
            conclusion: "現在不能交易：研究／PAPER 模式、無 ARM、無 live order、Stage 4.19 blocked。",
            evidence: ["private_api=false", "real_order=false", "UI 無下單控件"],
            contradictingEvidence: [],
            risk: "任何看似可交易的狀態僅為觀察用語",
          };
        case "market_pulse":
          return {
            ...baseMeta,
            conclusion: summary || "NO_DATA — 市場脈動尚未就緒",
            evidence: [
              `做多 ${status?.longCandidates ?? "NO_DATA"} · 做空 ${status?.shortCandidates ?? "NO_DATA"}`,
              `已確認 ${status?.confirmedCandidates ?? "NO_DATA"}`,
            ],
            contradictingEvidence: [],
            risk: `regime=${regime}`,
          };
        case "portfolio_summary":
          return {
            ...baseMeta,
            conclusion: "Shadow 投資組合：固定 25x 標籤 · max 2 持倉 · 無 live 操作",
            evidence: ["詳見 /portfolio", "NO_DATA 若 API 未回報持倉"],
            contradictingEvidence: [],
            risk: "非帳戶真實槓桿",
          };
        case "alert_digest":
          return {
            ...baseMeta,
            conclusion: `高風險候選 ${status?.highRiskCandidates ?? "NO_DATA"} · 詳見 /alerts`,
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
              ? `標的工作台：${sym} · 使用 Symbol Workbench 分頁檢視結構／風險／證據`
              : "請開啟 /market/:symbol 以取得標的上下文",
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
      conclusion: "AI provider unavailable",
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
      ? "RULE_BASED_SUMMARY"
      : answer.mode === "rules-only"
        ? "RULES-ONLY"
        : "UNAVAILABLE";

  return (
    <div className="floating-ai nx-ai-commander-w4 v1829-ai" aria-label="NEX AI">
      {open ? (
        <div className="floating-ai-panel panel-card nx-ai-p7" role="dialog" aria-label="NEX AI drawer">
          <div className="floating-ai-head">
            <strong>NEX AI</strong>
            <span className="tag tag-warn">{modeLabel}</span>
            <button type="button" className="ro-nav-chip ghost" onClick={() => setOpen(false)}>
              關閉
            </button>
          </div>
          <p className="muted sm">情境摘要 · 無 LLM 時不捏造 · 非投資建議</p>
          <div className="copilot-prompt-grid">
            {PROMPTS.map((p) => (
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
          <div className="nx-ai-answer-frame">
            <h4>Conclusion</h4>
            <p>{answer.conclusion}</p>
            <h4>Evidence</h4>
            <ul>
              {answer.evidence.length ? answer.evidence.map((e) => <li key={e}>{e}</li>) : <li className="muted">—</li>}
            </ul>
            <h4>Contradicting Evidence</h4>
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
            <h4>Risk</h4>
            <p>{answer.risk}</p>
            <h4>Invalidation</h4>
            <p>{answer.invalidation}</p>
            <h4>Freshness</h4>
            <p>{answer.freshness}</p>
            <h4>Decision Trace</h4>
            <p className="mono sm">{answer.decisionTrace}</p>
          </div>
          <Link to="/assistant" className="nx-link sm">
            完整助理頁 →
          </Link>
        </div>
      ) : null}
      <button
        type="button"
        className="floating-ai-fab"
        aria-expanded={open}
        aria-label="Open NEX AI"
        onClick={() => setOpen((v) => !v)}
        title="NEX AI"
      >
        AI
      </button>
    </div>
  );
}
