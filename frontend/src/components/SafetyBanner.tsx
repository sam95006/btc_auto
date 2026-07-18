/**
 * Phase 4 product chrome — separates Live market wording from execution status.
 * Execution disabled lives in System Status; market data remains Live public.
 */
export function SafetyBanner() {
  return (
    <div className="safety-banner nx-safety-p4" role="status">
      <span className="nx-safety-primary">市場行情：LIVE（Bybit Public）</span>
      <span className="nx-safety-sep" aria-hidden>
        ·
      </span>
      <span className="nx-safety-secondary">交易執行：Disabled · 研究模式</span>
    </div>
  );
}
