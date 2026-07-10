import { DemoDataBadge } from "./DemoDataBadge";

export function SafetyBanner() {
  return (
    <div className="safety-banner" role="status">
      <DemoDataBadge />
      <span>READ-ONLY · RESEARCH MODE · NOT INVESTMENT ADVICE · NO LIVE TRADING</span>
    </div>
  );
}
