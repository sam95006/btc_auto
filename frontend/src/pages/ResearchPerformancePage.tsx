import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface StreamSummary {
  stream: string;
  sampleSize: number;
  uncertaintyLabel: "INSUFFICIENT" | "LOW" | "MODERATE" | "ADEQUATE";
  totalCases: number;
  decisionsByStatus: Record<string, number>;
  simEntries: number;
  openPositions: number;
  closedPositions: number;
  pnlGross: number;
  pnlNet: number;
  totalFees: number;
  totalSlippage: number;
  totalFunding: number;
  winners: number;
  losers: number;
  winRate: number;
  expectancy: number;
  profitFactor: number | null;
  maxDrawdownPct: number;
  avgMfePct: number;
  avgMaePct: number;
  avgHoldTimeMin: number;
  riskBlockCount: number;
  riskAllowCount: number;
  riskBlockEffectiveness: number;
  updatedAtMs: number;
  researchOnly: boolean;
  privateApi: boolean;
}

interface PerformanceSummaryResponse {
  ok: boolean;
  researchOnly: boolean;
  privateApi: boolean;
  streams: Record<string, StreamSummary>;
  streamIds: string[];
  note: string;
  generatedAt: number;
  error?: string;
}

interface ReviewEngineStatus {
  ok: boolean;
  researchOnly: boolean;
  reviewMode: string;
  providerName: string;
  reviewCount: number;
  lastReviewAt?: number | null;
  uiModeLabel: string;
  fabricatedChat: boolean;
  error?: string;
}

interface RiskBlocksResponse {
  ok: boolean;
  researchOnly: boolean;
  riskBlocks: Record<string, {
    riskBlockCount: number;
    riskAllowCount: number;
    total: number;
    blockRate: number;
    effectiveness: number;
    uncertaintyLabel: string;
  }>;
  generatedAt: number;
}

interface CalibrationResponse {
  ok: boolean;
  researchOnly: boolean;
  calibration: Record<string, {
    sampleSize: number;
    uncertaintyLabel: string;
    winRate: number;
    expectancy: number;
    profitFactor: number | null;
    note: string;
  }>;
  generatedAt: number;
}

// ── Hooks ────────────────────────────────────────────────────────────────────

function usePerformanceSummary() {
  const [data, setData] = useState<PerformanceSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchData = () => {
      fetch("/api/nexus/performance/summary")
        .then((r) => r.json())
        .then((d: PerformanceSummaryResponse) => {
          if (!cancelled) { setData(d); setError(null); setLoading(false); }
        })
        .catch((e: Error) => {
          if (!cancelled) { setError(e.message); setLoading(false); }
        });
    };
    fetchData();
    const id = setInterval(fetchData, 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return { data, loading, error };
}

function useReviewEngineStatus() {
  const [status, setStatus] = useState<ReviewEngineStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchData = () => {
      fetch("/api/nexus/review-engine/status")
        .then((r) => r.json())
        .then((d: ReviewEngineStatus) => {
          if (!cancelled) { setStatus(d); setLoading(false); }
        })
        .catch(() => { if (!cancelled) setLoading(false); });
    };
    fetchData();
    const id = setInterval(fetchData, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return { status, loading };
}

function useRiskBlocks() {
  const [data, setData] = useState<RiskBlocksResponse | null>(null);
  useEffect(() => {
    fetch("/api/nexus/performance/risk-blocks")
      .then((r) => r.json())
      .then((d: RiskBlocksResponse) => setData(d))
      .catch(() => {});
  }, []);
  return data;
}

function useCalibration() {
  const [data, setData] = useState<CalibrationResponse | null>(null);
  useEffect(() => {
    fetch("/api/nexus/performance/calibration")
      .then((r) => r.json())
      .then((d: CalibrationResponse) => setData(d))
      .catch(() => {});
  }, []);
  return data;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const STREAM_LABELS: Record<string, string> = {
  LIVE_PAPER: "Live Paper",
  SHADOW: "Shadow",
  REPLAY: "Replay",
  MANUAL_VALIDATION: "Manual Validation",
};

const STREAM_COLORS: Record<string, string> = {
  LIVE_PAPER: "#4ade80",
  SHADOW: "#60a5fa",
  REPLAY: "#f59e0b",
  MANUAL_VALIDATION: "#a78bfa",
};

function pct(v: number, decimals = 1): string {
  return `${(v * 100).toFixed(decimals)}%`;
}

function usd(v: number): string {
  return v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2);
}

function uncertaintyBadgeClass(label: string): string {
  if (label === "ADEQUATE") return "nx-badge-ok";
  if (label === "MODERATE") return "nx-badge-active";
  if (label === "LOW") return "nx-badge-warn";
  return "nx-badge-fail";
}

function reviewModeClass(mode: string): string {
  if (mode === "LLM_ASSISTED") return "nx-badge-ok";
  if (mode === "RULES_ONLY") return "nx-badge-dim";
  if (mode === "LLM_UNAVAILABLE") return "nx-badge-warn";
  if (mode === "DEGRADED") return "nx-badge-fail";
  return "nx-badge-dim";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ReviewModeBanner({ status }: { status: ReviewEngineStatus }) {
  const isLlm = status.reviewMode === "LLM_ASSISTED";
  return (
    <div className="nx-perf-review-mode-banner">
      <div className="nx-perf-review-mode-row">
        <span className="nx-perf-review-mode-label">分析引擎模式</span>
        <span className={`nx-badge ${reviewModeClass(status.reviewMode)}`}>
          {status.reviewMode}
        </span>
        {isLlm && (
          <span className="nx-badge nx-badge-active">{status.providerName}</span>
        )}
      </div>
      <div className="nx-perf-review-mode-desc muted">
        {status.uiModeLabel}
      </div>
      {status.fabricatedChat === false && (
        <div className="nx-perf-review-mode-desc muted">
          fabricatedChat=false · 無虛構聊天 · researchOnly=true
        </div>
      )}
      <div className="nx-perf-review-mode-desc muted">
        本週期審查次數：{status.reviewCount}
      </div>
    </div>
  );
}

function StreamCard({ stream, summary }: { stream: string; summary: StreamSummary }) {
  const color = STREAM_COLORS[stream] ?? "#94a3b8";
  const label = STREAM_LABELS[stream] ?? stream;
  const isEmpty = summary.closedPositions === 0 && summary.totalCases === 0;

  return (
    <div className="nx-perf-stream-card" style={{ borderTopColor: color }}>
      <div className="nx-perf-stream-header">
        <span className="nx-perf-stream-name" style={{ color }}>
          {label}
        </span>
        <span className={`nx-badge ${uncertaintyBadgeClass(summary.uncertaintyLabel)}`}>
          n={summary.sampleSize} · {summary.uncertaintyLabel}
        </span>
      </div>

      {isEmpty ? (
        <div className="muted nx-perf-stream-empty">
          尚無紀錄 · 等待 {label} 資料累積
        </div>
      ) : (
        <>
          <div className="nx-perf-grid">
            <div>
              <div className="nx-perf-label">案件</div>
              <div className="nx-perf-value">{summary.totalCases}</div>
            </div>
            <div>
              <div className="nx-perf-label">開倉</div>
              <div className="nx-perf-value">{summary.openPositions}</div>
            </div>
            <div>
              <div className="nx-perf-label">平倉</div>
              <div className="nx-perf-value">{summary.closedPositions}</div>
            </div>
            <div>
              <div className="nx-perf-label">勝率</div>
              <div className="nx-perf-value">{pct(summary.winRate)}</div>
            </div>
            <div>
              <div className="nx-perf-label">毛利 PnL</div>
              <div className={`nx-perf-value ${summary.pnlGross >= 0 ? "nx-text-ok" : "nx-text-warn"}`}>
                {usd(summary.pnlGross)}
              </div>
            </div>
            <div>
              <div className="nx-perf-label">淨利 PnL</div>
              <div className={`nx-perf-value ${summary.pnlNet >= 0 ? "nx-text-ok" : "nx-text-warn"}`}>
                {usd(summary.pnlNet)}
              </div>
            </div>
            <div>
              <div className="nx-perf-label">手續費</div>
              <div className="nx-perf-value">{usd(-summary.totalFees)}</div>
            </div>
            <div>
              <div className="nx-perf-label">資金費</div>
              <div className="nx-perf-value">{usd(-summary.totalFunding)}</div>
            </div>
            <div>
              <div className="nx-perf-label">期望值</div>
              <div className="nx-perf-value">{summary.expectancy.toFixed(4)}</div>
            </div>
            <div>
              <div className="nx-perf-label">Profit Factor</div>
              <div className="nx-perf-value">
                {summary.profitFactor !== null ? summary.profitFactor.toFixed(2) : "∞"}
              </div>
            </div>
            <div>
              <div className="nx-perf-label">Max DD</div>
              <div className="nx-perf-value nx-text-warn">
                {summary.maxDrawdownPct.toFixed(1)}%
              </div>
            </div>
            <div>
              <div className="nx-perf-label">平均持倉</div>
              <div className="nx-perf-value">{summary.avgHoldTimeMin.toFixed(0)}m</div>
            </div>
            <div>
              <div className="nx-perf-label">Risk 封鎖</div>
              <div className="nx-perf-value">{summary.riskBlockCount}</div>
            </div>
            <div>
              <div className="nx-perf-label">封鎖率</div>
              <div className="nx-perf-value">{pct(summary.riskBlockEffectiveness)}</div>
            </div>
          </div>

          {Object.keys(summary.decisionsByStatus).length > 0 && (
            <div className="nx-perf-decisions">
              <div className="nx-perf-label">決策分佈</div>
              <div className="nx-perf-decisions-row">
                {Object.entries(summary.decisionsByStatus).map(([status, count]) => (
                  <span key={status} className="nx-perf-decision-chip">
                    {status}:{count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StreamSeparationNotice() {
  return (
    <div className="nx-perf-separation-notice">
      <strong>資料流隔離原則</strong>
      <span className="muted">
        {" "}— Live Paper / Shadow / Replay / Manual Validation 四條資料流絕不合併計算。
        各自獨立追蹤，樣本不足時標示 INSUFFICIENT。
      </span>
    </div>
  );
}

function Phase6GateDMarker() {
  return (
    <div className="nx-perf-gate-marker">
      <span className="nx-badge nx-badge-dim">Phase 6 Gate D</span>
      <span className="nx-badge nx-badge-dim">Performance Validation</span>
      <span className="nx-badge nx-badge-dim">researchOnly=true</span>
      <span className="nx-badge nx-badge-dim">privateApi=false</span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

/**
 * Phase 6 Gate D — Research Performance Page.
 *
 * Shows:
 * - Runtime review mode (RULES_ONLY / LLM_ASSISTED) — never lies about generative AI
 * - Performance metrics per stream (LIVE_PAPER / SHADOW / REPLAY / MANUAL_VALIDATION)
 * - Risk block effectiveness
 * - Calibration (win rate, expectancy, profit factor)
 * - Clear separation labels — streams MUST NOT be merged
 */
export function ResearchPerformancePage() {
  const { data: summary, loading, error } = usePerformanceSummary();
  const { status: reviewStatus, loading: reviewLoading } = useReviewEngineStatus();
  const riskData = useRiskBlocks();
  const calibData = useCalibration();

  const streams = summary?.streams ?? {};
  const streamIds = summary?.streamIds ?? ["LIVE_PAPER", "SHADOW", "REPLAY", "MANUAL_VALIDATION"];

  return (
    <div className="nx-perf-page nx-page">
      <div className="nx-perf-page-header">
        <h1 className="nx-page-title">Research Performance</h1>
        <p className="nx-page-subtitle muted">
          Phase 6 Gate D · 研究績效驗證 · 純研究模式 · 不執行真實交易
        </p>
        <Phase6GateDMarker />
      </div>

      {/* Review Engine Mode Banner */}
      {!reviewLoading && reviewStatus && reviewStatus.ok && (
        <ReviewModeBanner status={reviewStatus} />
      )}
      {!reviewLoading && reviewStatus && !reviewStatus.ok && (
        <div className="nx-perf-error-note muted">
          Review Engine 狀態無法載入：{reviewStatus.error ?? "未知"}
        </div>
      )}

      <StreamSeparationNotice />

      {/* Stream cards */}
      {loading && <div className="nx-perf-loading muted">載入績效資料…</div>}
      {error && !loading && (
        <div className="nx-perf-error-banner">績效資料無法載入：{error}</div>
      )}
      {!loading && summary && !summary.ok && (
        <div className="nx-perf-error-banner">後端錯誤：{summary.error ?? "未知"}</div>
      )}

      {!loading && summary && summary.ok && (
        <div className="nx-perf-streams-grid">
          {streamIds.map((sid) => {
            const s = streams[sid];
            if (!s) return null;
            return <StreamCard key={sid} stream={sid} summary={s} />;
          })}
        </div>
      )}

      {/* Risk blocks section */}
      {riskData && riskData.ok && (
        <div className="nx-perf-section">
          <h2 className="nx-section-title">Risk Block 有效性</h2>
          <div className="nx-perf-table">
            <div className="nx-perf-table-header">
              <span>資料流</span>
              <span>封鎖</span>
              <span>允許</span>
              <span>封鎖率</span>
              <span>樣本</span>
            </div>
            {Object.entries(riskData.riskBlocks).map(([sid, rb]) => (
              <div key={sid} className="nx-perf-table-row">
                <span style={{ color: STREAM_COLORS[sid] ?? "#94a3b8" }}>
                  {STREAM_LABELS[sid] ?? sid}
                </span>
                <span>{rb.riskBlockCount}</span>
                <span>{rb.riskAllowCount}</span>
                <span>{pct(rb.blockRate)}</span>
                <span className={`nx-badge ${uncertaintyBadgeClass(rb.uncertaintyLabel)}`}>
                  {rb.total} · {rb.uncertaintyLabel}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Calibration section */}
      {calibData && calibData.ok && (
        <div className="nx-perf-section">
          <h2 className="nx-section-title">校準分析</h2>
          <div className="nx-perf-table">
            <div className="nx-perf-table-header">
              <span>資料流</span>
              <span>樣本</span>
              <span>勝率</span>
              <span>期望值</span>
              <span>PF</span>
              <span>不確定性</span>
            </div>
            {Object.entries(calibData.calibration).map(([sid, c]) => (
              <div key={sid} className="nx-perf-table-row">
                <span style={{ color: STREAM_COLORS[sid] ?? "#94a3b8" }}>
                  {STREAM_LABELS[sid] ?? sid}
                </span>
                <span>{c.sampleSize}</span>
                <span>{pct(c.winRate)}</span>
                <span>{c.expectancy.toFixed(4)}</span>
                <span>{c.profitFactor !== null ? c.profitFactor.toFixed(2) : "∞"}</span>
                <span className={`nx-badge ${uncertaintyBadgeClass(c.uncertaintyLabel)}`}>
                  {c.uncertaintyLabel}
                </span>
              </div>
            ))}
          </div>
          <div className="muted" style={{ marginTop: "0.5rem", fontSize: "0.78rem" }}>
            INSUFFICIENT → 少於 10 筆 · 不具統計意義 · LOW → 少於 30 筆
          </div>
        </div>
      )}

      <div className="nx-perf-footer muted">
        研究系統 · Phase 6 Gate D · researchOnly=true · privateApi=false ·
        四條資料流絕不合併 · 無虛構聊天對話
      </div>
    </div>
  );
}
