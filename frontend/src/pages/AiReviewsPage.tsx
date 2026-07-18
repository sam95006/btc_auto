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

interface SessionsResponse {
  ok: boolean;
  sessions: ReviewSession[];
  count: number;
  generatedAt: number;
  error?: string;
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
          if (!cancelled) { setStatus(d); setError(null); setLoading(false); }
        })
        .catch((e: Error) => {
          if (!cancelled) { setError(e.message); setLoading(false); }
        });
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => { cancelled = true; clearInterval(id); };
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
          if (!cancelled) { setSessions(d.sessions ?? []); setLoading(false); }
        })
        .catch(() => { if (!cancelled) setLoading(false); });
    };
    fetch_();
    const id = setInterval(fetch_, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return { sessions, loading };
}

function stateLabel(state: ReviewSession["state"]): string {
  switch (state) {
    case "COMPLETED": return "完成";
    case "RUNNING":   return "進行中";
    case "PENDING":   return "等待中";
    case "SKIPPED":   return "已跳過";
    case "FAILED":    return "失敗";
    default:          return state;
  }
}

function stateClass(state: ReviewSession["state"]): string {
  switch (state) {
    case "COMPLETED": return "nx-badge-ok";
    case "RUNNING":   return "nx-badge-active";
    case "FAILED":    return "nx-badge-fail";
    case "SKIPPED":   return "nx-badge-dim";
    default:          return "nx-badge-dim";
  }
}

function formatTs(ts?: number | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" });
}

function SessionCard({ session }: { session: ReviewSession }) {
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
      {session.error && (
        <div className="nx-ai-reviews-error-note">錯誤：{session.error}</div>
      )}
      {session.summary && Object.keys(session.summary).length > 0 && (
        <div className="nx-ai-reviews-summary-hint muted">
          已收集摘要 · {Object.keys(session.summary).length} 個欄位
        </div>
      )}
    </div>
  );
}

function StatusCard({ status }: { status: AiReviewsStatus }) {
  const hours = status.scheduleHours ?? [];
  return (
    <div className="nx-ai-reviews-status-card">
      <div className="nx-ai-reviews-status-header">
        <span className="nx-ai-reviews-title">AI 檢討週期</span>
        <span className="nx-badge nx-badge-dim">研究模式 · 無實際交易</span>
      </div>
      <div className="nx-ai-reviews-status-grid">
        <div>
          <div className="nx-ai-reviews-label">排程時區</div>
          <div className="nx-ai-reviews-value">{status.scheduleTimezone}</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">週期時間</div>
          <div className="nx-ai-reviews-value">{hours.map(h => `${String(h).padStart(2,"0")}:00`).join(" · ")}</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">目前台北時 (H)</div>
          <div className="nx-ai-reviews-value">{status.currentTaipeiHour}:xx</div>
        </div>
        <div>
          <div className="nx-ai-reviews-label">下次週期</div>
          <div className="nx-ai-reviews-value">{String(status.nextScheduledHour).padStart(2,"0")}:00</div>
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
 * Read-only: shows structured review cycle cards. No fabricated AI chat.
 * Forbidden: /trade, /orders, /arm — this page only reads research endpoints.
 */
export function AiReviewsPage() {
  const { status, loading: statusLoading, error: statusError } = useAiReviewsStatus();
  const { sessions, loading: sessionsLoading } = useAiReviewSessions();

  return (
    <div className="nx-ai-reviews nx-page">
      <div className="nx-ai-reviews-page-header">
        <h1 className="nx-page-title">AI 檢討中心</h1>
        <p className="nx-page-subtitle muted">
          自動市場研究週期 · 純研究模式 · 不執行真實交易
        </p>
      </div>

      {statusLoading && (
        <div className="nx-ai-reviews-loading muted">載入週期狀態…</div>
      )}

      {statusError && !statusLoading && (
        <div className="nx-ai-reviews-error-banner">
          週期狀態無法載入：{statusError}
        </div>
      )}

      {status && !status.ok && (
        <div className="nx-ai-reviews-error-banner">
          後端回報錯誤：{status.error ?? "未知"}
        </div>
      )}

      {status && status.ok && (
        <StatusCard status={status} />
      )}

      <div className="nx-ai-reviews-sessions-section">
        <h2 className="nx-section-title">近期週期紀錄</h2>

        {sessionsLoading && (
          <div className="nx-ai-reviews-loading muted">載入紀錄…</div>
        )}

        {!sessionsLoading && sessions.length === 0 && (
          <div className="nx-ai-reviews-empty">
            <p className="muted">尚無週期紀錄。系統將在 Asia/Taipei 00:00 / 06:00 / 12:00 / 18:00 自動執行。</p>
          </div>
        )}

        <div className="nx-ai-reviews-sessions-list">
          {sessions.map((s) => (
            <SessionCard key={s.sessionId} session={s} />
          ))}
        </div>
      </div>

      <div className="nx-ai-reviews-footer muted">
        研究系統 · Phase 5 Gate B · researchOnly=true · privateApi=false
      </div>
    </div>
  );
}
