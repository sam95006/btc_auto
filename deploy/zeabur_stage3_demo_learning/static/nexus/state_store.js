import { connectNexusSocket, fetchNexusState } from "./api_client.js";

const POLL_INTERVAL_MS = 2000;
const WS_SAFETY_POLL_MS = 10000;

const listeners = new Set();
let state = null;
let socket = null;
let reconnectTimer = null;
let pollingTimer = null;
let started = false;

const transport = {
  connected: false,
  source: "init",
  lastSyncAt: null,
  lastRestAt: null,
  lastSocketAt: null,
  lastError: null,
};

function notify() {
  listeners.forEach((listener) => listener(state));
}

function mergeState(snapshot) {
  if (!snapshot) return;
  state = {
    ...(state || {}),
    ...snapshot,
    transport: { ...transport },
  };
  notify();
}

function setTransportPatch(patch) {
  Object.assign(transport, patch);
  if (state) {
    state = { ...state, transport: { ...transport } };
    notify();
  }
}

async function refreshFromRest(source = "poll") {
  try {
    const snapshot = await fetchNexusState();
    setTransportPatch({
      connected: true,
      source,
      lastSyncAt: new Date().toISOString(),
      lastRestAt: new Date().toISOString(),
      lastError: null,
    });
    mergeState(snapshot);
  } catch (error) {
    const lastRestAt = transport.lastRestAt ? new Date(transport.lastRestAt).getTime() : 0;
    const isStale = !lastRestAt || Date.now() - lastRestAt > 15000;
    setTransportPatch({
      connected: isStale ? false : transport.connected,
      source,
      lastError: error?.message || String(error),
    });
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    connectSocket();
  }, 3000);
}

function connectSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) return;
  try {
    socket = connectNexusSocket({
      onSnapshot: (snapshot, source) => {
        setTransportPatch({
          connected: true,
          source,
          lastSyncAt: new Date().toISOString(),
          lastSocketAt: new Date().toISOString(),
          lastError: null,
        });
        mergeState(snapshot);
      },
      onOpen: () => {
        setTransportPatch({
          connected: true,
          source: "ws",
          lastSocketAt: new Date().toISOString(),
          lastError: null,
        });
      },
      onClose: () => {
        const lastRestAt = transport.lastRestAt ? new Date(transport.lastRestAt).getTime() : 0;
        const restHealthy = lastRestAt && Date.now() - lastRestAt <= 15000;
        setTransportPatch({ connected: restHealthy ? true : false, source: restHealthy ? "poll" : "ws" });
        scheduleReconnect();
      },
      onError: (error) => {
        const lastRestAt = transport.lastRestAt ? new Date(transport.lastRestAt).getTime() : 0;
        const restHealthy = lastRestAt && Date.now() - lastRestAt <= 15000;
        setTransportPatch({
          connected: restHealthy ? true : false,
          source: restHealthy ? "poll" : "ws",
          lastError: error?.message || String(error),
        });
      },
    });
  } catch (error) {
    setTransportPatch({
      connected: false,
      source: "ws",
      lastError: error?.message || String(error),
    });
    scheduleReconnect();
  }
}

export function getState() {
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  if (state) listener(state);
  return () => listeners.delete(listener);
}

export async function refreshNexusState(source = "manual") {
  return refreshFromRest(source);
}

export async function startStateStore() {
  if (started) return;
  started = true;

  await refreshFromRest("boot");
  connectSocket();

  pollingTimer = window.setInterval(() => {
    const socketOpen = socket && socket.readyState === WebSocket.OPEN;
    if (!socketOpen) {
      refreshFromRest("poll");
      return;
    }
    const lastRestAt = transport.lastRestAt ? new Date(transport.lastRestAt).getTime() : 0;
    if (!lastRestAt || Date.now() - lastRestAt > WS_SAFETY_POLL_MS) {
      refreshFromRest("safety");
    }
  }, POLL_INTERVAL_MS);
}
