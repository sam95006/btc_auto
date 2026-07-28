export const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 390, height: 844 },
} as const;

export const PRIMARY_ROUTES = [
  { path: "/overview", heading: "總覽" },
  { path: "/universe", heading: "全市場" },
  { path: "/opportunities", heading: "機會" },
  { path: "/alerts", heading: "警報" },
  { path: "/portfolio", heading: "投資組合" },
  { path: "/learning", heading: "學習" },
  { path: "/evidence", heading: "Evidence Center" },
] as const;

export const ARTIFACTS_AFTER_DIR = "../../artifacts/wave4/after";
export const ARTIFACTS_BEFORE_DIR = "../../artifacts/wave4/before";
