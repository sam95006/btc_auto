import { useEffect, useState } from "react";

interface AiReviewsStatus {
  ok: boolean;
  researchOnly: boolean;
  scheduleHours: number[];
  scheduleTimezone: string;
  currentTaipeiHour: number;
  nextScheduledHour: number;
  totalSessions: number;
  completedSessions: number;
  failedSessions: number;
  lastSession?: ReviewSession | null;
  currentSession?: ReviewSession | null;
  generatedAt: number;
  error?: string;
}

interface ReviewSession {
  sessionId: string;
  slotKey: string;
  triggerHour: number;
  state: "PENDING" | "RUNNING" | "COMPLETED" | "SKIPPED" | "FAILED";
  startedAt?: number | null;
  completedAt?: number | null;
  error?: string | null;
  summary?: Record<string, unknown>;
  createdAt: number;
  researchOnly: boolean;
}

interface RoleAssessment {
  role: string;
  verdict: string;
  rationale?: string;
  confidence?: number;
  analysisMode?: string;
  flags?: string[];
}

interface ReviewCase {
  caseId: string;
  symbol: string;
  direction: string;
  trigger: string;
  status: string;
  decision?: {
    decisionStatus?: string;
    summary?: string;
    analysisMode?: string;
    assessments?: RoleAssessment[];
  } | null;
  candidateScore?: number;
  candidateStage?: string;
  createdAt?: number;
  researchOnly?: boolean;
}

interface SessionsResponse {
  ok: boolean;
  sessions: ReviewSession[];
  count: number;
  generatedAt: number;
  error?: string;
}

interface CasesResponse {
  ok: boolean;
  cases: ReviewCase[];
  count: number;
}

function useAiReviewsStatus() {
  const [status, setStatus] = useState<AiReviewsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchStatus = () => {
      fetch("/api/nexus/ai-reviews/status")
        .then((r) => r.json())
        .then((d: AiReviewsStatus) => {
          if (!cancelled) {
            setStatus(d);
            setError(null);
            setLoading(false);
          }
        })
        .catch((e: Error) => {
          if (!cancelled) {
            setError(e.message);
            setLoading(false);
          }
        });
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return { status, loading, error };
}

function useAiReviewSessions() {
  const [sessions, setSessions] = useState<ReviewSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetch_ = () => {
      fetch("/api/nexus/ai-reviews/sessions?limit=10")
        .then((r) => r.json())
        .then((d: SessionsResponse) => {
          if (!cancelled) {
            setSessions(d.sessions ?? []);
            setLoading(false);
          }
        })
        .catch(() => {
          if (!cancelled) setLoading(false);
        });
    };
    fetch_();
    const id = setInterval(fetch_, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return { sessions, loading };
}

function useReviewCases() {
  const [cases, setCases] = useState<ReviewCase[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetch_ = () => {
      fetch("/api/nexus/review-cases?limit=20")
        .then((r) => r.json())
        .then((d: CasesResponse) => {
          if (!cancelled) {
            setCases(d.cases ?? []);
            setLoading(false);
          }
        })
        .catch(() => {
          if (!cancelled) setLoading(false);
        });
    };
    fetch_();
    const id = setInterval(fetch_, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return { cases, loading };
}

function stateLabel(state: ReviewSession["state"]): string {
  switch (state) {
    case "COMPLETED":
      return "完成";
    case "RUNNING":
      return "進行中";
    case "PENDING":
      return "等待中";
    case "SKIPPED":
      return "已跳過";
    case "FAILED":
      return "失敗";
    default:
      return state;
  }
}

function stateClass(state: ReviewSession["state"]): string {
  switch (state) {
    case "COMPLETED":
      return "nx-badge-ok";
    case "RUNNING":
      return "nx-badge-active";
    case "FAILED":
      return "nx-badge-fail";
    case "SKIPPED":
      return "nx-badge-dim";
    default:
      return "nx-badge-dim";
  }
}

function formatTs(ts?: number | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" });
}

function verdictClass(verdict: string): string {
  const v = verdict.toUpperCase();
  if (v.includes("BLOCK") || v.includes("UNFAVOR") || v.includes("WEAK") || v.includes("UNALIGN")) {
    return "nx-badge-fail";
  }
  if (v.includes("FAVOR") || v.includes("ALIGN") || v.includes("ACCEPT") || v === "OK") {
    return "nx-badge-ok";
  }
  return "nx-badge-dim";
}

function SessionCard({ session }: { session: ReviewSession }) {
  const reviewed = Array.isArray(session.summary?.casesReviewed)
    ? (session.summary?.casesReviewed as Array<Record<string, unknown>>)
    : [];
  return (
    <div className="nx-ai-reviews-session-card">
      <div className="nx-ai-reviews-session-header">
        <span className={`nx-badge ${stateClass(session.state)}`}>{stateLabel(session.state)}</span>
        <span className="nx-ai-reviews-slot">{session.slotKey}</span>
      </div>
      <div className="nx-ai-reviews-session-meta">
        <span>開始：{formatTs(session.startedAt)}</span>
        <span>結束：{formatTs(session.completedAt)}</span>
      </div>
      {session.error && <div className="nx-ai-reviews-error-note">錯誤：{session.error}</div>}
      {reviewed.length > 0 && (
        <div className="nx-ai-reviews-summary-hint">
          本週期審查案件 {reviewed.length} 筆
          <ul className="nx-ai-reviews-mini-list">
            {reviewed.slice(0, 5).map((r) => (
              <li key={String(r.caseId)}>
                {String(r.symbol)} · {String(r.decisionStatus)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {session.summary && reviewed.length === 0 && Object.keys(session.summary).length > 0 && (
        <div className="nx-ai-reviews-summary-hint muted">
          已收集摘要 · {Object.keys(session.summary).length} 個欄位（尚無案件審查）
        </div>
      )}
    </div>
  );
}

function CaseCard({ item }: { item: ReviewCase }) {
  const decision = item.decision;
  const assessments = decision?.assessments ?? [];
  const supporting = assessments.filter((a) =>
    /FAVOR|ALIGN|ACCEPT|OK|SUPPORT/i.test(a.verdict),
  );
  const opposing = assessments.filter((a) =>
    /BLOCK|UNFAVOR|UNALIGN|WEAK|CONFLICT|CAUTION/i.test(a.verdict),
  );
  return (
    <div className="nx-ai-reviews-case-card">
      <div className="nx-ai-reviews-session-header">
        <strong>
          {item.symbol} · {item.direction}
        </strong>
        <span className="nx-badge nx-badge-dim">{item.status}</span>
      </div>
      <div className="nx-ai-reviews-session-meta">
        <span>觸發：{item.trigger}</span>
        <span>階段：{item.candidateStage ?? "—"}</span>
        <span>決策：{decision?.decisionStatus ?? "尚未決策"}</span>
      </div>
      {decision?.summary && <p className="nx-ai-reviews-decision-summary">{decision.summary}</p>}
      <div className="nx-ai-reviews-role-meta muted">
        分析模式：{decision?.analysisMode ?? "RULES"}（規則式分析 · 非虛構聊天）
      </div>
      {assessments.length > 0 ? (
        <div className="nx-ai-reviews-role-grid">
          {assessments.map((a) => (
            <div key={`${item.caseId}-${a.role}`} className="nx-ai-reviews-role-card">
              <div className="nx-ai-reviews-session-header">
                <span>{a.role}</span>
                <span className={`nx-badge ${verdictClass(a.verdict)}`}>{a.verdict}</span>
              </div>
              <p>{a.rationale || "—"}</p>
              {a.flags && a.flags.length > 0 && (
                <div className="muted">風險標記：{a.flags.join(" · ")}</div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">尚無角色評估（案件可能仍在收集）</div>
      )}
      <div className="nx-ai-reviews-session-meta">
        <span>支持：{supporting.map((a) => a.role).join(", ") || "—"}</span>
        <span>反對／封鎖：{opposing.map((a) => a.role).join(", ") || "—"}</span>
      </div>
    </div>
  );
}

function StatusCard({ status }: { status: AiReviewsStatus }) {
  const hours = status.scheduleHours ?? [];
  return (
    <div className="nx-ai-reviews-status-card">
      <div className="nx-ai-reviews-status-header">
        <span className="nx-ai-reviews-title">AI 自我檢討會議</span>
        <span className="nx-badge nx-badge-dim">研究模式 · 無實際交易</span>
      </div>
      <div className="nx-ai-reviews-status-grid">
        <div>
          <div className="nx-ai-reviews-label">排程時區</div>
          <div className="nx-ai-reviews-value">{status.scheduleTimezone}</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">週期時間</div>
          <div className="nx-ai-reviews-value">
            {hours.map((h) => `${String(h).padStart(2, "0")}:00`).join(" · ")}
          </div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">目前台北時 (H)</div>
          <div className="nx-ai-reviews-value">{status.currentTaipeiHour}:xx</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">下次會議</div>
          <div className="nx-ai-reviews-value">
            {String(status.nextScheduledHour).padStart(2, "0")}:00
          </div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">總次數</div>
          <div className="nx-ai-reviews-value">{status.totalSessions}</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">已完成</div>
          <div className="nx-ai-reviews-value">{status.completedSessions}</div>
        </div>
        {status.failedSessions > 0 && (
          <div>
            <div className="nx-ai-reviews-label">失敗</div>
            <div className="nx-ai-reviews-value nx-text-warn">{status.failedSessions}</div>
          </div>
        )}
      </div>
      {status.lastSession && (
        <div className="nx-ai-reviews-current muted">
          上次會議：{status.lastSession.slotKey} · {stateLabel(status.lastSession.state)} ·{" "}
          {formatTs(status.lastSession.completedAt || status.lastSession.startedAt)}
        </div>
      )}
      {status.currentSession && (
        <div className="nx-ai-reviews-current">
          <span className="nx-badge nx-badge-active">正在執行</span>
          <span className="nx-ai-reviews-slot">{status.currentSession.slotKey}</span>
        </div>
      )}
    </div>
  );
}

/**
 * Phase 5 Gate B — AI Review Center page.
 * Read-only: structured role cards + decisions. No fabricated AI chat.
 */
export function AiReviewsPage() {
  const { status, loading: statusLoading, error: statusError } = useAiReviewsStatus();
  const { sessions, loading: sessionsLoading } = useAiReviewSessions();
  const { cases, loading: casesLoading } = useReviewCases();

  const riskBlocks = cases.filter((c) => c.decision?.decisionStatus === "RISK_BLOCKED").length;
  const readySim = cases.filter((c) => c.decision?.decisionStatus === "READY_FOR_SIMULATION").length;

  return (
    <div className="nx-ai-reviews nx-page">
      <div className="nx-ai-reviews-page-header">
        <h1 className="nx-page-title">AI 檢討中心</h1>
        <p className="nx-page-subtitle muted">
          即時候選審查案件 + 每六小時自我檢討 · 純研究模式 · 不執行真實交易
        </p>
      </div>

      {statusLoading && <div className="nx-ai-reviews-loading muted">載入週期狀態…</div>}
      {statusError && !statusLoading && (
        <div className="nx-ai-reviews-error-banner">週期狀態無法載入：{statusError}</div>
      )}
      {status && !status.ok && (
        <div className="nx-ai-reviews-error-banner">後端回報錯誤：{status.error ?? "未知"}</div>
      )}
      {status && status.ok && <StatusCard status={status} />}

      <div className="nx-ai-reviews-status-grid" style={{ marginTop: "1rem" }}>
        <div>
          <div className="nx-ai-reviews-label">審查案件</div>
          <div className="nx-ai-reviews-value">{cases.length}</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">Risk 封鎖</div>
          <div className="nx-ai-reviews-value">{riskBlocks}</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">可進入模擬</div>
          <div className="nx-ai-reviews-value">{readySim}</div>
        </div>
      </div>

      <div className="nx-ai-reviews-sessions-section">
        <h2 className="nx-section-title">動態審查案件（角色意見）</h2>
        {casesLoading && <div className="nx-ai-reviews-loading muted">載入案件…</div>}
        {!casesLoading && cases.length === 0 && (
          <div className="nx-ai-reviews-empty">
            <p className="muted">尚無審查案件。Top 5／Confirmed 候選出現時會即時建立（不必等六小時）。</p>
          </div>
        )}
        <div className="nx-ai-reviews-sessions-list">
          {cases.map((c) => (
            <CaseCard key={c.caseId} item={c} />
          ))}
        </div>
      </div>

      <div className="nx-ai-reviews-sessions-section">
        <h2 className="nx-section-title">六小時檢討週期紀錄</h2>
        {sessionsLoading && <div className="nx-ai-reviews-loading muted">載入紀錄…</div>}
        {!sessionsLoading && sessions.length === 0 && (
          <div className="nx-ai-reviews-empty">
            <p className="muted">
              尚無週期紀錄。系統將在 Asia/Taipei 00:00 / 06:00 / 12:00 / 18:00 自動執行全局反思。
            </p>
          </div>
        )}
        <div className="nx-ai-reviews-sessions-list">
          {sessions.map((s) => (
            <SessionCard key={s.sessionId} session={s} />
          ))}
        </div>
      </div>

      <div className="nx-ai-reviews-footer muted">
        研究系統 · Phase 5 · researchOnly=true · privateApi=false · 無虛構聊天對話
      </div>
    </div>
  );
}
