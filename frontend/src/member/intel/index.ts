export { LIFECYCLE_STATES, MEMBER_POSTURES, LIFECYCLE_HINT } from "./lifecycleStates";
export type { LifecycleState, MemberPosture } from "./lifecycleStates";
export { FUNNEL_STAGE_DEFS, formatFunnelCount, buildFunnelStages } from "./funnel";
// NEXUS-EXPERIENCE-1B: production must NOT depend on demo/fixture catalogs. Test
// fixtures live only in isolated test dirs. Intelligence data comes from the
// backend; when unavailable the UI shows an honest COMING_SOON/empty state.
export { IntelligenceFunnel } from "./IntelligenceFunnel";
export { IntelligenceStateChip } from "./IntelligenceStateChip";
export { IntelligenceExperiencePanel } from "./IntelligenceExperiencePanel";
export type { MemberIntelExperience } from "./types";
