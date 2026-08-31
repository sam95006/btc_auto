import { useEffect, useRef } from "react";

/** Lightweight animated intelligence network (Canvas 2D). Pauses under
 * prefers-reduced-motion and when the tab is hidden. Not required for first
 * paint; purely decorative depth behind the hero. */
export function IntelligenceField({ density = 42 }: { density?: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let w = 0;
    let h = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const n = Math.max(12, Math.min(density, 60));
    const nodes = Array.from({ length: n }, () => ({
      x: Math.random(), y: Math.random(), vx: (Math.random() - 0.5) * 0.0006, vy: (Math.random() - 0.5) * 0.0006,
    }));

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas.width = Math.floor(w * dpr); canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (const p of nodes) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > 1) p.vx *= -1;
        if (p.y < 0 || p.y > 1) p.vy *= -1;
      }
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = (a.x - b.x) * w, dy = (a.y - b.y) * h;
          const d = Math.hypot(dx, dy);
          if (d < 120) {
            ctx.strokeStyle = `rgba(90,140,255,${0.12 * (1 - d / 120)})`;
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(a.x * w, a.y * h); ctx.lineTo(b.x * w, b.y * h); ctx.stroke();
          }
        }
      }
      for (const p of nodes) {
        ctx.fillStyle = "rgba(120,170,255,0.55)";
        ctx.beginPath(); ctx.arc(p.x * w, p.y * h, 1.6, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    };

    const start = () => { if (!raf && !document.hidden) raf = requestAnimationFrame(draw); };
    const stop = () => { cancelAnimationFrame(raf); raf = 0; };

    if (reduced) {
      draw(); stop(); // one static frame, no animation loop
    } else {
      start();
      document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
    }
    return () => { stop(); window.removeEventListener("resize", resize); };
  }, [density]);

  return <canvas ref={ref} className="corp-field" aria-hidden data-testid="intelligence-field" />;
}
