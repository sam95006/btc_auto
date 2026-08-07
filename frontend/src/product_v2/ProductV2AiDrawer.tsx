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
  | "alert_digest"
  | "symbol_context";

type PromptDef = { id: PromptId; label: string };

function promptsForPath(pathname: string): PromptDef[] {
  const base: PromptDef[] = [
    { id: "explain_page", label: "解釋此頁" },
    { id: "market_pulse", label: "市場怎麼了" },
    { id: "explain_risk", label: "目前風險" },
  ];
  if (pathname.includes("/opportunities") || pathname.includes("/overview")) {
    return [
      ...base,
      { id: "why_blocked", label: "為何未合格" },
      { id: "find_long", label: "多方 Radar" },
      { id: "find_short", label: "空方 Radar" },
      { id: "symbol_context", label: "解釋排名異動" },
    ];
  }
  if (pathname.includes("/market/")) {
    return [...base, { id: "symbol_context", label: "為何是此狀態" }, { id: "why_blocked", label: "為何未 READY" }];
  }
  if (pathname.includes("/scanner")) {
    return [...base, { id: "why_blocked", label: "為何被擋" }, { id: "symbol_context", label: "比較前三名" }];
  }
  if (pathname.includes("/alerts")) {
    return [...base, { id: "alert_digest", label: "警報摘要" }];
  }
  if (pathname.includes("/intelligence")) {
    return [...base, { id: "daily_brief", label: "研究簡報" }, { id: "symbol_context", label: "標的上下文" }];
  }
  return [...base, { id: "daily_brief", label: "今日簡報" }, { id: "alert_digest", label: "警報摘要" }];
}

/**
 * Product V2 NEX AI — top「分析」opens right contextual drawer.
 * No orb / mascot. Reuses headless market summary hooks only.
 */
export function ProductV2AiDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [active, setActive] = useState<PromptId>("daily_brief");
  const loc = useLocation();
  const { status, longs, shorts, loading } = useMarketScannerOverview();
  const prompts = useMemo(() => promptsForPath(loc.pathname), [loc.pathname]);

  useEffect(() => {
    const onOpen = () => {
      /* external open already handled by parent */
    };
    window.addEventListener("nexus-open-ai", onOpen);
    return () => window.removeEventListener("nexus-open-ai", onOpen);
  }, []);

  useEffect(() => {
    if (!prompts.some((p) => p.id === active)) {
      setActive(prompts[0]?.id ?? "daily_brief");
    }
  }, [prompts, active]);

  const answer = useMemo(() => {
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
    const baseMeta = {
      modeLabel: "規則摘要",
      freshness,
      decisionTrace: "規則引擎 · 尚未配置 LLM",
      invalidation: "研究模式 · 無下單權限",
    };

    if (loading && !status) {
      return {
        ...baseMeta,
        modeLabel: "不可用",
        conclusion: "掃描器資料尚未就緒，無法產生可靠簡報。",
        evidence: [] as string[],
        contradictingEvidence: [] as string[],
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
            ? `最高做多候選 ${topL.symbol.replace("USDT", "")}（機會 ${Math.round(topL.opportunityScore)}）`
            : "目前沒有可列出的做多候選",
          evidence: topL?.reasons?.slice(0, 3) || [],
          contradictingEvidence: topL?.conflicts?.slice(0, 3) || [],
          risk: topL ? `風險分數 ${Math.round(topL.riskScore)}` : "無候選",
        };
      case "find_short":
        return {
          ...baseMeta,
          conclusion: topS
            ? `最高做空候選 ${topS.symbol.replace("USDT", "")}（機會 ${Math.round(topS.opportunityScore)}）`
            : "目前沒有可列出的做空候選",
          evidence: topS?.reasons?.slice(0, 3) || [],
          contradictingEvidence: topS?.conflicts?.slice(0, 3) || [],
          risk: topS ? `風險分數 ${Math.round(topS.riskScore)}` : "無候選",
        };
      case "explain_risk":
        return {
          ...baseMeta,
          conclusion: `高風險／過熱標的：${status?.highRiskCandidates ?? "尚無資料"}`,
          evidence: ["風險閘與 shadow 政策由後端治理，前端只讀顯示"],
          contradictingEvidence: [],
          risk: "前端不會覆寫槓桿／保證金／倉位上限",
        };
      case "why_blocked":
        return {
          ...baseMeta,
          conclusion: "現在不能交易：研究／紙上模式、無 ARM、無實盤下單。",
          evidence: ["private_api=false", "real_order=false"],
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
          conclusion: symMatch ? `標的工作台：${sym}` : "請開啟標的頁以取得標的上下文",
          evidence: [],
          contradictingEvidence: [],
          risk: "—",
        };
      }
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
          modeLabel: "規則摘要",
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
  }, [active, loading, loc.pathname, longs, shorts, status]);

  if (!open) return null;

  return (
    <aside className="mp2-ai-drawer" role="dialog" aria-label="NEX AI 分析" data-testid="mp2-ai-drawer">
      <header>
        <strong>NEX AI · 分析</strong>
        <span className="muted" style={{ fontSize: "0.75rem" }}>
          {answer.modeLabel}
        </span>
        <button type="button" className="mp2-btn mp2-btn-ghost" style={{ marginLeft: "auto" }} onClick={onClose}>
          關閉
        </button>
      </header>
      <p className="muted" style={{ margin: "0 0 10px", fontSize: "0.75rem" }}>
        情境分析 · 無 LLM 時不捏造 · 非投資建議
      </p>
      <div className="mp2-ai-prompts">
        {prompts.map((p) => (
          <button
            key={p.id}
            type="button"
            className={active === p.id ? "active" : undefined}
            onClick={() => setActive(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="mp2-ai-answer">
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
              <li key={e}>{e}</li>
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
        <p className="mono" style={{ fontSize: "0.75rem" }}>
          {answer.decisionTrace}
        </p>
      </div>
      <Link to="/assistant" className="mp2-btn mp2-btn-ghost" style={{ marginTop: 10 }} onClick={onClose}>
        完整助理頁 →
      </Link>
    </aside>
  );
}

export function openProductV2Ai() {
  window.dispatchEvent(new CustomEvent("nexus-open-ai", { detail: "summary" }));
}
