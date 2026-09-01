/**
 * Premium R3F (three.js) hero field — a slowly rotating structural lattice with
 * a drifting intelligence particle cloud. MOTION intensity and COLOUR are
 * modulated by the backend regime/energy passed in as props; the frontend never
 * decides or displays a market value here. Lazy-loaded (default export → its own
 * chunk); rendered ONLY on desktop, non-reduced-motion. Decorative (aria-hidden).
 */
import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { MarketRegime } from "../../types";

function regimeRGB(regime: MarketRegime, available: boolean): THREE.Color {
  if (!available) return new THREE.Color(0.58, 0.64, 0.72);
  if (regime === "RISK_ON") return new THREE.Color(0.14, 0.82, 0.55);
  if (regime === "RISK_OFF") return new THREE.Color(1.0, 0.42, 0.5);
  if (regime === "NEUTRAL") return new THREE.Color(0.31, 0.55, 1.0);
  return new THREE.Color(0.58, 0.64, 0.72);
}

function Lattice({ energy, color }: { energy: number; color: THREE.Color }) {
  const g1 = useRef<THREE.Mesh>(null);
  const g2 = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    const s = 0.06 + energy * 0.12;
    if (g1.current) { g1.current.rotation.y += dt * s; g1.current.rotation.x += dt * s * 0.4; }
    if (g2.current) { g2.current.rotation.y -= dt * s * 0.6; }
  });
  return (
    <group>
      <mesh ref={g1}>
        <icosahedronGeometry args={[2.5, 1]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.22} />
      </mesh>
      <mesh ref={g2} scale={1.6}>
        <icosahedronGeometry args={[2.5, 0]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.1} />
      </mesh>
    </group>
  );
}

function Cloud({ energy, color }: { energy: number; color: THREE.Color }) {
  const ref = useRef<THREE.Points>(null);
  const count = 900;
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 3.2 + Math.random() * 4.5;
      const th = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      arr[i * 3] = r * Math.sin(ph) * Math.cos(th);
      arr[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th) * 0.6;
      arr[i * 3 + 2] = r * Math.cos(ph);
    }
    return arr;
  }, []);
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.y += dt * (0.02 + energy * 0.05); });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial color={color} size={0.032} sizeAttenuation transparent opacity={0.5 + energy * 0.35} depthWrite={false} />
    </points>
  );
}

export default function IntelligenceR3F({ energy, regime, available }: { energy: number; regime: MarketRegime; available: boolean }) {
  const color = useMemo(() => regimeRGB(regime, available), [regime, available]);
  return (
    <Canvas
      className="corp-fs-hero-bg"
      camera={{ position: [0, 0, 9], fov: 55 }}
      dpr={[1, 1.6]}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      aria-hidden
      style={{ pointerEvents: "none" }}
    >
      <fog attach="fog" args={["#05070e", 8, 16]} />
      <Lattice energy={energy} color={color} />
      <Cloud energy={energy} color={color} />
    </Canvas>
  );
}
