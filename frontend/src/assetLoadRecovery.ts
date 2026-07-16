/**
 * One-shot reload when hashed SPA assets 404 after deploy (stale HTML shell).
 * Does not intercept market WebSocket errors.
 */
const RELOAD_GUARD_KEY = "nexus_ui_asset_reload_guard";

function isAssetLoadFailure(message: string, source?: string): boolean {
  if (source && /\/assets\/index-[^/]+\.(js|css)/i.test(source)) {
    return true;
  }
  return /ChunkLoadError|Failed to fetch dynamically imported module|Loading chunk \d+ failed|Importing a module script failed/i.test(
    message
  );
}

function showAssetErrorUi(): void {
  const root = document.getElementById("root");
  if (!root || root.childElementCount > 0) {
    return;
  }
  root.innerHTML = [
    '<div style="font-family:system-ui,sans-serif;max-width:32rem;margin:2rem auto;padding:1rem 1.25rem;line-height:1.5">',
    "<strong>NEXUS UI could not load.</strong>",
    "<p>A newer version may have been deployed. Please refresh once. If this persists, clear site data for this domain.</p>",
    "<p><small>READ-ONLY · research UI · not investment advice</small></p>",
    "</div>",
  ].join("");
}

export function installAssetLoadRecovery(): void {
  if (typeof window === "undefined") {
    return;
  }

  const guard = sessionStorage.getItem(RELOAD_GUARD_KEY);
  if (guard === "failed") {
    showAssetErrorUi();
    return;
  }

  window.addEventListener(
    "error",
    (event) => {
      const target = event.target;
      if (!(target instanceof HTMLScriptElement) && !(target instanceof HTMLLinkElement)) {
        return;
      }
      const source = target instanceof HTMLScriptElement ? target.src : target.href;
      if (!source || !isAssetLoadFailure("", source)) {
        return;
      }
      const state = sessionStorage.getItem(RELOAD_GUARD_KEY);
      if (state === "1") {
        sessionStorage.setItem(RELOAD_GUARD_KEY, "failed");
        showAssetErrorUi();
        return;
      }
      sessionStorage.setItem(RELOAD_GUARD_KEY, "1");
      window.location.reload();
    },
    true
  );

  window.addEventListener("unhandledrejection", (event) => {
    const message = String((event.reason as Error | undefined)?.message ?? event.reason ?? "");
    if (!isAssetLoadFailure(message)) {
      return;
    }
    const state = sessionStorage.getItem(RELOAD_GUARD_KEY);
    if (state === "1") {
      sessionStorage.setItem(RELOAD_GUARD_KEY, "failed");
      showAssetErrorUi();
      return;
    }
    sessionStorage.setItem(RELOAD_GUARD_KEY, "1");
    window.location.reload();
  });
}

export function clearAssetLoadRecoveryGuard(): void {
  try {
    sessionStorage.removeItem(RELOAD_GUARD_KEY);
  } catch {
    // ignore private browsing
  }
}
