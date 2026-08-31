/** Static, dependency-free hero backdrop. Rendered under prefers-reduced-motion,
 * as the Suspense fallback for the animated hero, and on very small screens.
 * Purely decorative (aria-hidden); it encodes no market value. */
export function HeroFallback() {
  return (
    <svg className="corp-hero-canvas" viewBox="0 0 1200 700" preserveAspectRatio="xMidYMid slice" aria-hidden focusable="false">
      <defs>
        <radialGradient id="corp-hf-glow" cx="60%" cy="18%" r="70%">
          <stop offset="0%" stopColor="rgba(91,140,255,0.28)" />
          <stop offset="55%" stopColor="rgba(53,224,192,0.06)" />
          <stop offset="100%" stopColor="rgba(4,6,12,0)" />
        </radialGradient>
      </defs>
      <rect width="1200" height="700" fill="url(#corp-hf-glow)" />
      <g stroke="rgba(126,154,214,0.22)" strokeWidth="1" fill="none">
        <path d="M180 520 L360 360 L540 300 L760 380 L980 260" />
        <path d="M240 200 L420 300 L620 240 L820 320 L1020 420" />
        <path d="M360 360 L420 300" />
        <path d="M540 300 L620 240" />
        <path d="M760 380 L820 320" />
      </g>
      <g fill="rgba(140,180,255,0.85)">
        {[[180, 520], [360, 360], [540, 300], [760, 380], [980, 260], [240, 200], [420, 300], [620, 240], [820, 320], [1020, 420]].map(
          ([x, y], i) => <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 3.2 : 2} />,
        )}
      </g>
    </svg>
  );
}
