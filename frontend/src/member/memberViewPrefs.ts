/** Member Platform Simple / Pro view preference (local only). */

const KEY = "nexus_member_view_pref_v1";

export type MemberViewMode = "simple" | "pro";

export function loadMemberViewMode(): MemberViewMode {
  try {
    const v = localStorage.getItem(KEY);
    return v === "pro" ? "pro" : "simple";
  } catch {
    return "simple";
  }
}

export function saveMemberViewMode(mode: MemberViewMode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    /* ignore */
  }
}
