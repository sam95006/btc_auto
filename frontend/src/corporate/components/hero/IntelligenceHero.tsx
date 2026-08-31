/**
 * Backend-driven intelligence-network hero (Canvas 2D — no WebGL library, keeps
 * the bundle lean). It renders a living graph of instruments and intelligence
 * layers. The MOTION (drift, connectivity, pulse) and COLOR are modulated by the
 * backend's own regime/availability decision passed in as props — the frontend
 * never decides or displays a market value here. Labels are concept names only.
 *
 * Pauses when the tab is hidden; a single static frame under reduced motion.
 * Purely decorative (aria-hidden) — all meaningful text lives in the DOM hero.
 */
import { useEffect, useRef } from "react";
import { reducedMotion } from "../../hooks/useScrollScene";
import type { MarketRegime } from "../../types";

type Props = {
  energy: number; // 0..1, derived by the backend regime/risk (motion only)
  regime: MarketRegime;
  available: boolean;
};

// Concept anchors — labels only, never values.
const ANCHORS = ["BTC", "ETH", "SOL", "Data", "Context", "Risk", "Signal", "Intelligence"];

function regimeColor(regime: Props["regime"], available: boolean): [number, number, number] {
  if (!available) return [148, 163, 184]; // dim / honest when not READY
  if (regime === "RISK_ON") return [45, 212, 138];
  if (regime === "RISK_OFF") return [255, 107, 129];
  if (regime === "NEUTRAL") return [110, 160, 255];
  return [148, 163, 184];
}

export default function IntelligenceHero({ energy, regime, available }: Props) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  // live-updatable refs so prop changes don't reset the simulation
  const energyRef = useRef(energy);
  const colorRef = useRef(regimeColor(regime, available));
  energyRef.current = energy;
  colorRef.current = regimeColor(regime, available);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = reducedMotion();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0, h = 0, raf = 0, t = 0;
    // fewer nodes on small screens (designed mobile, not shrunk)
    const small = window.innerWidth < 640;
    const ambientCount = small ? 26 : 54;

    type Node = { x: number; y: number; vx: number; vy: number; label?: string; base: number };
    const rand = (a: number, b: number) => a + Math.random() * (b - a);
    const nodes: Node[] = [];
    ANCHORS.forEach((label, i) => {
      const ang = (i / ANCHORS.length) * Math.PI * 2;
      nodes.push({ x: 0.5 + Math.cos(ang) * 0.26, y: 0.42 + Math.sin(ang) * 0.24, vx: 0, vy: 0, label, base: 0 });
    });
    for (let i = 0; i < ambientCount; i++) {
      nodes.push({ x: Math.random(), y: Math.random(), vx: rand(-1, 1) * 0.0004, vy: rand(-1, 1) * 0.0004, base: rand(0.4, 1) });
    }

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      w = rect.width; h = rect.height;
      canvas.width = Math.floor(w * dpr); canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const frame = () => {
      const e = energyRef.current;
      const [cr, cg, cb] = colorRef.current;
      t += 0.006 * (0.5 + e);
      ctx.clearRect(0, 0, w, h);

      // RISK_ON expands the graph outward; RISK_OFF contracts it toward centre.
      const spread = 0.5 + (e - 0.5) * 0.5; // 0.25..0.75 gravity target radius factor
      const linkDist = (small ? 96 : 132) * (0.7 + e * 0.6);

      for (let i = 0; i < nodes.length; i++) {
        const p = nodes[i];
        if (p.label) {
          // anchors gently orbit; radius breathes with energy
          const ang = (i / ANCHORS.length) * Math.PI * 2 + t * 0.12;
          const r = 0.16 + spread * 0.16;
          p.x += ((0.5 + Math.cos(ang) * r) - p.x) * 0.02;
          p.y += ((0.44 + Math.sin(ang) * r) - p.y) * 0.02;
        } else {
          p.x += p.vx * (0.4 + e); p.y += p.vy * (0.4 + e);
          if (p.x < 0 || p.x > 1) p.vx *= -1;
          if (p.y < 0 || p.y > 1) p.vy *= -1;
        }
      }

      // links
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = (a.x - b.x) * w, dy = (a.y - b.y) * h;
          const d = Math.hypot(dx, dy);
          if (d < linkDist) {
            const alpha = (0.05 + 0.16 * e) * (1 - d / linkDist);
            ctx.strokeStyle = `rgba(${cr},${cg},${cb},${alpha})`;
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(a.x * w, a.y * h); ctx.lineTo(b.x * w, b.y * h); ctx.stroke();
          }
        }
      }
      // nodes
      for (const p of nodes) {
        const px = p.x * w, py = p.y * h;
        if (p.label) {
          const pulse = 0.6 + 0.4 * Math.sin(t * 2 + p.x * 6);
          ctx.fillStyle = `rgba(${cr},${cg},${cb},${0.85 * (available ? 1 : 0.6)})`;
          ctx.beginPath(); ctx.arc(px, py, 3 + pulse * (1 + e), 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = `rgba(210,224,255,${available ? 0.62 : 0.4})`;
          ctx.font = "600 11px Inter, system-ui, sans-serif";
          ctx.fillText(p.label, px + 8, py + 3);
        } else {
          ctx.fillStyle = `rgba(${cr},${cg},${cb},${0.28 + 0.3 * p.base * e})`;
          ctx.beginPath(); ctx.arc(px, py, 1.4, 0, Math.PI * 2); ctx.fill();
        }
      }
      raf = requestAnimationFrame(frame);
    };

    const start = () => { if (!raf && !document.hidden) raf = requestAnimationFrame(frame); };
    const stop = () => { cancelAnimationFrame(raf); raf = 0; };
    const onVis = () => (document.hidden ? stop() : start());

    if (reduce) {
      frame(); stop(); // single frame, no loop
    } else {
      start();
      document.addEventListener("visibilitychange", onVis);
    }
    return () => {
      stop();
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [available]);

  return <canvas ref={ref} className="corp-hero-canvas" aria-hidden data-testid="intelligence-hero" />;
}
