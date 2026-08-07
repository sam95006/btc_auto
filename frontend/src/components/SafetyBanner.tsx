/**
 * Member Platform safety chrome — compact strip for product surface.
 */
export function SafetyBanner() {
  return (
    <div className="safety-banner nx-safety-member" role="status">
      <span className="nx-safety-primary">NEXUS · 市場情報</span>
      <span className="nx-safety-sep" aria-hidden>
        ·
      </span>
      <span className="nx-safety-secondary">唯讀研究 · 非投資建議 · 不下單</span>
    </div>
  );
}
