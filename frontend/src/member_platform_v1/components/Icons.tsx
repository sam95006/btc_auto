import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...props }: IconProps) {
  return { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, ...props };
}

export function IconOverview(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}
export function IconChart(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 15l3-4 3 2 4-6" />
    </svg>
  );
}
export function IconStar(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3l2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 15.9 7.2 18l.9-5.4L4.2 8.7l5.4-.8L12 3z" />
    </svg>
  );
}
export function IconBell(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M6 9a6 6 0 1112 0c0 7 3 7 3 7H3s3 0 3-7" />
      <path d="M10 19a2 2 0 004 0" />
    </svg>
  );
}
export function IconCrown(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 17h18l-1.5-9-4.5 4L12 5l-3 7-4.5-4L3 17z" />
      <path d="M3 17h18v2H3z" />
    </svg>
  );
}
export function IconUser(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 19c1.8-3 4-4.5 7-4.5S17.2 16 19 19" />
    </svg>
  );
}
export function IconSearch(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-3.5-3.5" />
    </svg>
  );
}
export function IconShield(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3l7 3v5c0 5-3.2 8.2-7 10-3.8-1.8-7-5-7-10V6l7-3z" />
    </svg>
  );
}
export function IconMail(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 7l9 7 9-7" />
    </svg>
  );
}
export function IconLock(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="5" y="10" width="14" height="10" rx="2" />
      <path d="M8 10V7a4 4 0 018 0v3" />
    </svg>
  );
}
export function IconTrend(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 17l6-6 4 4 7-8" />
      <path d="M14 7h6v6" />
    </svg>
  );
}
export function IconAlert(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3l9 16H3L12 3z" />
      <path d="M12 10v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}
export function IconTarget(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="1" />
    </svg>
  );
}
