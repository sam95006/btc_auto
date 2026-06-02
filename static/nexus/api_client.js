function normalizeArray(value) {
  return Array.isArray(value) ? value : [];
}

export function normalizeNexusSnapshot(payload) {
  const snapshot = payload && typeof payload === "object" ? payload : {};
  return {
    ...snapshot,
    capital: snapshot.capital && typeof snapshot.capital === "object" ? snapshot.capital : {},
    loans: snapshot.loans && typeof snapshot.loans === "object" ? snapshot.loans : {},
    pnl: snapshot.pnl && typeof snapshot.pnl === "object" ? snapshot.pnl : {},
    system: snapshot.system && typeof snapshot.system === "object" ? snapshot.system : {},
    positions: normalizeArray(snapshot.positions),
    orders: normalizeArray(snapshot.orders),
    trades: normalizeArray(snapshot.trades),
    alerts: normalizeArray(snapshot.alerts),
    meetings: normalizeArray(snapshot.meetings),
    events: normalizeArray(snapshot.events),
  };
}

export async function fetchNexusState(timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch("/api/nexus/state", {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`state request failed: ${response.status}`);
    const raw = await response.text();
    try {
      return normalizeNexusSnapshot(JSON.parse(raw));
    } catch (error) {
      throw new Error(`state JSON parse failed: ${error?.message || String(error)}`);
    }
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`state request timed out after ${timeoutMs}ms`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function sendStationChat(channel, message, speaker = "指揮官") {
  const response = await fetch("/api/nexus/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel, message, speaker }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.error || `chat failed: ${response.status}`);
  return payload;
}

export async function fetchLayoutConfig() {
  const response = await fetch("/api/nexus/layout", { cache: "no-store" });
  if (!response.ok) throw new Error(`layout request failed: ${response.status}`);
  return response.json();
}

export async function saveLayoutConfig(layout) {
  const response = await fetch("/api/nexus/layout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(layout || {}),
  });
  if (!response.ok) throw new Error(`layout save failed: ${response.status}`);
  return response.json();
}

export function connectNexusSocket({ onSnapshot, onError, onOpen, onClose }) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/nexus`);

  socket.onopen = () => {
    if (typeof onOpen === "function") onOpen();
  };

  socket.onclose = () => {
    if (typeof onClose === "function") onClose();
  };

  socket.onerror = (error) => {
    if (typeof onError === "function") onError(error);
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload && payload.snapshot && typeof onSnapshot === "function") {
        onSnapshot(normalizeNexusSnapshot(payload.snapshot), "ws");
      }
    } catch (error) {
      if (typeof onError === "function") onError(error);
    }
  };

  return socket;
}
