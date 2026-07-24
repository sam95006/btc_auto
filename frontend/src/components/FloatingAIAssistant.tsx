import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import { buildMarketSummary, deriveRegime } from "../market/marketSummary";
import { buildAiDailyBrief } from "../market/aiDailyBrief";

type PromptId =
  | "explain_page"
  | "find_long"
  | "find_short"
  | "explain_risk"
  | "daily_brief"
  | "why_blocked";

type AiAnswer = {
  mode: "rules-only" | "unavailable";
  conclusion: string;
  evidence: string[];
  /** Renamed from contradicting in 7.2 to match AiDailyBrief contract. */
  contradictingEvidence: string[];
  risk: string;
  invalidation: string;
  freshness: string;
  decisionTrace: string;
};

const PROMPTS: { id: PromptId; label: string }[] = [
  { id: "explain_page", label: "解釋目前頁面" },
  { id: "find_long", label: "找多頭機會" },
  { id: "find_short", label: "找空頭機會" },
  { id: "explain_risk", label: "找風險" },
  { id: "daily_brief", label: "每日簡報" },
  { id: "why_blocked", label: "為何不能進場" },
];

function detectLlmAvailable(): boolean {
  // Product 7: no client LLM wiring — always rules-only / unavailable.
  return false;
}

/**
 * Bottom-right FAB + drawer. Honest unavailable / rules-only when no LLM.
 */
export function FloatingAIAssistant() {
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
        mode: "rules-only" as const,
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
            conclusion: `高風險／過熱標的：${status?.highRiskCandidates ?? "—"}；生產限制 3x／20 USDT／最多 1 倉。`,
            evidence: ["Risk Gate 與 PAPER 限制由後端治理，前端只讀顯示"],
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
            mode: brief.mode,
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

  return (
    <div className="floating-ai" aria-label="AI Assistant">
      {open ? (
        <div className="floating-ai-panel panel-card nx-ai-p7" role="dialog" aria-label="AI drawer">
          <div className="floating-ai-head">
            <strong>AI 助理</strong>
            <span className={`tag ${answer.mode === "rules-only" ? "tag-warn" : "tag-warn"}`}>
              {answer.mode === "rules-only" ? "RULES-ONLY" : "UNAVAILABLE"}
            </span>
            <button type="button" className="ro-nav-chip ghost" onClick={() => setOpen(false)}>
              關閉
            </button>
          </div>
          <p className="muted sm">無 LLM provider · 不會捏造答案 · 非投資建議</p>
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
        </div>
      ) : null}
      <button
        type="button"
        className="floating-ai-fab"
        aria-expanded={open}
        aria-label="Open AI assistant"
        onClick={() => setOpen((v) => !v)}
        title="AI 助理"
      >
        AI
      </button>
    </div>
  );
}
