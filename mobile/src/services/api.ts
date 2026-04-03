/**
 * api.ts — Serviço de API para Personal AI Mobile (React Native)
 * Consome a mesma API FastAPI do backend.
 * Suporta modo offline com fila local SQLite.
 */
import axios, { AxiosInstance, AxiosRequestConfig } from "axios";
import AsyncStorage from "@react-native-async-storage/async-storage";
import NetInfo from "@react-native-community/netinfo";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";

// ── Configuração ─────────────────────────────────────────────────────────────
const API_URL = process.env.EXPO_PUBLIC_API_URL || "https://your-domain.com";
const WS_URL  = API_URL.replace("https://", "wss://").replace("http://", "ws://");

const KEYS = {
  TOKEN:   "personal_ai_token",
  API_URL: "personal_ai_api_url",
};

// ── Axios instance ────────────────────────────────────────────────────────────
let _axios: AxiosInstance | null = null;

export async function getApiClient(): Promise<AxiosInstance> {
  if (_axios) return _axios;
  const baseURL = (await AsyncStorage.getItem(KEYS.API_URL)) || API_URL;
  const token   = await SecureStore.getItemAsync(KEYS.TOKEN);

  _axios = axios.create({
    baseURL,
    timeout: 30_000,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  // Interceptor: salva/atualiza token se retornado
  _axios.response.use(
    (res) => {
      if (res.data?.token) SecureStore.setItemAsync(KEYS.TOKEN, res.data.token);
      return res;
    },
    (err) => Promise.reject(err)
  );

  return _axios;
}

// ── Offline Queue (SQLite local) ──────────────────────────────────────────────
let _db: SQLite.SQLiteDatabase | null = null;

async function getLocalDB(): Promise<SQLite.SQLiteDatabase> {
  if (_db) return _db;
  _db = await SQLite.openDatabaseAsync("personal_ai_offline.db");
  await _db.execAsync(`
    CREATE TABLE IF NOT EXISTS offline_queue (
      id          TEXT PRIMARY KEY,
      method      TEXT NOT NULL,
      endpoint    TEXT NOT NULL,
      payload     TEXT DEFAULT '{}',
      created_at  TEXT DEFAULT (datetime('now')),
      synced      INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS local_cache (
      key         TEXT PRIMARY KEY,
      value       TEXT,
      expires_at  TEXT,
      updated_at  TEXT DEFAULT (datetime('now'))
    );
  `);
  return _db;
}

async function enqueueOffline(method: string, endpoint: string, payload: any) {
  const db = await getLocalDB();
  const id = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
  await db.runAsync(
    "INSERT INTO offline_queue (id, method, endpoint, payload) VALUES (?,?,?,?)",
    id, method, endpoint, JSON.stringify(payload)
  );
}

export async function syncOfflineQueue(): Promise<number> {
  const state = await NetInfo.fetch();
  if (!state.isConnected) return 0;
  const db = await getLocalDB();
  const rows = await db.getAllAsync<any>(
    "SELECT * FROM offline_queue WHERE synced = 0 ORDER BY created_at ASC LIMIT 50"
  );
  let synced = 0;
  const api = await getApiClient();
  for (const row of rows) {
    try {
      const payload = JSON.parse(row.payload);
      if (row.method === "POST")   await api.post(row.endpoint, payload);
      else if (row.method === "PUT") await api.put(row.endpoint, payload);
      else if (row.method === "DELETE") await api.delete(row.endpoint);
      await db.runAsync("UPDATE offline_queue SET synced = 1 WHERE id = ?", row.id);
      synced++;
    } catch (e) {
      console.warn(`Sync failed for ${row.endpoint}:`, e);
    }
  }
  return synced;
}

// ── Tipo de retorno genérico ──────────────────────────────────────────────────
type ApiResult<T> = { data: T | null; error: string | null; offline: boolean };

async function safeRequest<T>(
  fn: (api: AxiosInstance) => Promise<T>,
  fallbackFn?: () => Promise<T>
): Promise<ApiResult<T>> {
  const state = await NetInfo.fetch();
  if (!state.isConnected) {
    if (fallbackFn) {
      try {
        const data = await fallbackFn();
        return { data, error: null, offline: true };
      } catch (e: any) {
        return { data: null, error: e.message, offline: true };
      }
    }
    return { data: null, error: "Sem conexão", offline: true };
  }
  try {
    const api = await getApiClient();
    const data = await fn(api);
    return { data, error: null, offline: false };
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || "Erro desconhecido";
    return { data: null, error: msg, offline: false };
  }
}

// ── API Functions ─────────────────────────────────────────────────────────────

export const personalAI = {
  // ── Health ──────────────────────────────────────────────────────────────────
  health: () =>
    safeRequest((api) => api.get("/health").then((r) => r.data)),

  status: () =>
    safeRequest((api) => api.get("/api/status").then((r) => r.data)),

  // ── Chat ────────────────────────────────────────────────────────────────────
  sendMessage: async (message: string, conversationId?: string, voiceResponse = false) => {
    const state = await NetInfo.fetch();
    if (!state.isConnected) {
      await enqueueOffline("POST", "/api/chat", { message, conversation_id: conversationId });
      return { data: { response: "[Mensagem salva para envio offline]", offline: true }, error: null, offline: true };
    }
    return safeRequest((api) =>
      api.post("/api/chat", {
        message,
        conversation_id: conversationId,
        platform: "mobile",
        voice_response: voiceResponse,
      }).then((r) => r.data)
    );
  },

  getConversations: () =>
    safeRequest((api) => api.get("/api/conversations").then((r) => r.data)),

  getMessages: (conversationId: string) =>
    safeRequest((api) => api.get(`/api/conversations/${conversationId}/messages`).then((r) => r.data)),

  deleteConversation: (id: string) =>
    safeRequest((api) => api.delete(`/api/conversations/${id}`).then((r) => r.data)),

  // ── Memory ──────────────────────────────────────────────────────────────────
  getMemories: (query?: string) =>
    safeRequest((api) =>
      api.get("/api/memory", { params: query ? { query, limit: 20 } : { limit: 30 } }).then((r) => r.data)
    ),

  addMemory: (content: string, type = "fact", importance = 0.7) =>
    safeRequest((api) =>
      api.post("/api/memory", { content, type, importance }).then((r) => r.data)
    ),

  deleteMemory: (id: string) =>
    safeRequest((api) => api.delete(`/api/memory/${id}`).then((r) => r.data)),

  // ── Calendar ─────────────────────────────────────────────────────────────────
  getCalendar: (date?: string) =>
    safeRequest((api) =>
      api.get("/api/calendar/agenda", { params: date ? { date } : {} }).then((r) => r.data)
    ),

  createEvent: (event: any) =>
    safeRequest((api) => api.post("/api/calendar/events", event).then((r) => r.data)),

  updateEvent: (id: string, data: any) =>
    safeRequest((api) => api.put(`/api/calendar/events/${id}`, data).then((r) => r.data)),

  deleteEvent: (id: string) =>
    safeRequest((api) => api.delete(`/api/calendar/events/${id}`).then((r) => r.data)),

  // ── Voice ────────────────────────────────────────────────────────────────────
  textToSpeech: (text: string, voice?: string) =>
    safeRequest((api) =>
      api.post("/api/voice/tts", { text, voice }, { responseType: "blob" }).then((r) => r.data)
    ),

  getVoiceProfiles: () =>
    safeRequest((api) => api.get("/api/voice/profiles").then((r) => r.data)),

  // ── Bluetooth ─────────────────────────────────────────────────────────────────
  scanBluetooth: (duration = 10) =>
    safeRequest((api) =>
      api.post("/api/bluetooth/scan", { duration }).then((r) => r.data)
    ),

  connectBluetooth: (mac: string) =>
    safeRequest((api) => api.post(`/api/bluetooth/connect/${mac}`).then((r) => r.data)),

  disconnectBluetooth: (mac: string) =>
    safeRequest((api) => api.post(`/api/bluetooth/disconnect/${mac}`).then((r) => r.data)),

  getTrustedDevices: () =>
    safeRequest((api) => api.get("/api/bluetooth/trusted").then((r) => r.data)),

  // ── Telephony ─────────────────────────────────────────────────────────────────
  dialNumber: (number: string, via = "sip") =>
    safeRequest((api) => api.post("/api/telephony/dial", { number, via }).then((r) => r.data)),

  hangupCall: () =>
    safeRequest((api) => api.post("/api/telephony/hangup").then((r) => r.data)),

  getCallHistory: () =>
    safeRequest((api) => api.get("/api/telephony/history").then((r) => r.data)),

  // ── Routines ──────────────────────────────────────────────────────────────────
  getRoutines: () =>
    safeRequest((api) => api.get("/api/routines").then((r) => r.data)),

  createRoutine: (data: any) =>
    safeRequest((api) => api.post("/api/routines", data).then((r) => r.data)),

  toggleRoutine: (id: string, enabled: boolean) =>
    safeRequest((api) => api.put(`/api/routines/${id}`, { enabled }).then((r) => r.data)),

  // ── Jobs ──────────────────────────────────────────────────────────────────────
  getJobs: (status?: string) =>
    safeRequest((api) =>
      api.get("/api/jobs/list", { params: status ? { status } : {} }).then((r) => r.data)
    ),

  getJobStats: () =>
    safeRequest((api) => api.get("/api/jobs/stats").then((r) => r.data)),

  // ── Apps / Plataformas ────────────────────────────────────────────────────────
  getApps: () =>
    safeRequest((api) => api.get("/api/apps/list").then((r) => r.data)),

  launchApp: (appId: string, query?: string) =>
    safeRequest((api) => api.post(`/api/apps/launch/${appId}`, { query }).then((r) => r.data)),

  // ── Self-monitoring ───────────────────────────────────────────────────────────
  getMetrics: () =>
    safeRequest((api) => api.get("/api/monitoring/metrics").then((r) => r.data)),

  getPatches: () =>
    safeRequest((api) => api.get("/api/improvements/list").then((r) => r.data)),

  applyPatch: (id: string) =>
    safeRequest((api) => api.post(`/api/improvements/${id}/apply`).then((r) => r.data)),

  // ── Sync ─────────────────────────────────────────────────────────────────────
  getSyncStatus: () =>
    safeRequest((api) => api.get("/api/sync/status").then((r) => r.data)),

  forceSync: () =>
    safeRequest((api) => api.post("/api/sync/push").then((r) => r.data)),

  // ── Config ────────────────────────────────────────────────────────────────────
  getConfig: () =>
    safeRequest((api) => api.get("/api/config").then((r) => r.data)),

  updateConfig: (data: any) =>
    safeRequest((api) => api.put("/api/config", data).then((r) => r.data)),

  // ── Integrações ────────────────────────────────────────────────────────────────
  spotifySearch: (query: string) =>
    safeRequest((api) => api.get("/api/spotify/search", { params: { q: query } }).then((r) => r.data)),

  spotifyPlay: (uri: string) =>
    safeRequest((api) => api.post("/api/spotify/play", { uri }).then((r) => r.data)),

  sendWhatsApp: (to: string, message: string) =>
    safeRequest((api) => api.post("/api/whatsapp/send", { to, message }).then((r) => r.data)),
};

// ── WebSocket Manager ─────────────────────────────────────────────────────────
type WSListener = (data: any) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private listeners: Map<string, WSListener[]> = new Map();
  private reconnectTimer: any = null;
  private reconnectDelay = 3000;

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    try {
      this.ws = new WebSocket(`${WS_URL}/ws`);
      this.ws.onopen = () => {
        console.log("🔌 WebSocket conectado");
        this.reconnectDelay = 3000;
        this.emit("connected", {});
      };
      this.ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          this.emit(msg.type, msg.data);
          this.emit("*", msg);
        } catch (e) {}
      };
      this.ws.onclose = () => {
        console.log("WebSocket desconectado");
        this.emit("disconnected", {});
        this.scheduleReconnect();
      };
      this.ws.onerror = (e) => {
        console.warn("WebSocket error:", e);
        this.emit("error", e);
      };
    } catch (e) {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 30_000);
      this.connect();
    }, this.reconnectDelay);
  }

  send(type: string, data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...data }));
    }
  }

  on(event: string, listener: WSListener) {
    if (!this.listeners.has(event)) this.listeners.set(event, []);
    this.listeners.get(event)!.push(listener);
    return () => this.off(event, listener);
  }

  off(event: string, listener: WSListener) {
    const arr = this.listeners.get(event) || [];
    this.listeners.set(event, arr.filter((l) => l !== listener));
  }

  private emit(event: string, data: any) {
    (this.listeners.get(event) || []).forEach((l) => l(data));
  }

  disconnect() {
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}

export const wsManager = new WebSocketManager();
