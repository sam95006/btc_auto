import { useState } from "react";

/** Token icon with initials fallback. Broken icons must never fake a brand mark. */
export function TokenIcon({ symbol, size = 22 }: { symbol: string; size?: number }) {
  const base = symbol.replace(/USDT$/i, "").toUpperCase();
  const initials = base.slice(0, 2) || "?";
  const [broken, setBroken] = useState(false);
  // Optional public CDN — on failure fall back to initials (broken_icons = 0 visual).
  const src = `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/32/color/${base.toLowerCase()}.png`;

  if (broken) {
    return (
      <span
        className="mp2-token-icon fallback"
        style={{ width: size, height: size, fontSize: Math.max(9, size * 0.4) }}
        aria-hidden
        title={base}
      >
        {initials}
      </span>
    );
  }

  return (
    <img
      className="mp2-token-icon"
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setBroken(true)}
    />
  );
}
