/**
 * appStore.ts — Store global com Zustand
 * Estado global do app: chat, config, status, offline
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import AsyncStorage from "@react-native-async-storage/async-storage";

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  audio_url?: string;
  offline?: boolean;
}

export interface AppStatus {
  online: boolean;
  health_score: number;
  cpu_percent: number;
  memory_percent: number;
  version: string;
  pending_sync: number;
}

interface AppStore {
  // ── Estado ────────────────────────────────────────────────────────────────
  messages: Message[];
  conversationId: string | null;
  status: AppStatus;
  isListening: boolean;
  isSpeaking: boolean;
  theme: "dark" | "light" | "auto";
  language: string;
  serverUrl: string;
  wakeWord: string;
  alwaysListen: boolean;
  isConnected: boolean;
  pendingOfflineMessages: number;

  // ── Actions ───────────────────────────────────────────────────────────────
  addMessage: (msg: Message) => void;
  clearMessages: () => void;
  setConversationId: (id: string | null) => void;
  updateStatus: (s: Partial<AppStatus>) => void;
  setListening: (v: boolean) => void;
  setSpeaking: (v: boolean) => void;
  setTheme: (t: "dark" | "light" | "auto") => void;
  setLanguage: (l: string) => void;
  setServerUrl: (url: string) => void;
  setWakeWord: (w: string) => void;
  setAlwaysListen: (v: boolean) => void;
  setConnected: (v: boolean) => void;
  setPendingOffline: (n: number) => void;
}

export const useAppStore = create<AppStore>()(
  persist(
    (set) => ({
      // ── Estado inicial ───────────────────────────────────────────────────
      messages: [],
      conversationId: null,
      status: {
        online: false,
        health_score: 0,
        cpu_percent: 0,
        memory_percent: 0,
        version: "2.0.0",
        pending_sync: 0,
      },
      isListening: false,
      isSpeaking: false,
      theme: "dark",
      language: "pt-BR",
      serverUrl: process.env.EXPO_PUBLIC_API_URL || "https://your-domain.com",
      wakeWord: "LAS",
      alwaysListen: false,
      isConnected: false,
      pendingOfflineMessages: 0,

      // ── Actions ───────────────────────────────────────────────────────────
      addMessage: (msg) =>
        set((state) => ({
          messages: [...state.messages.slice(-100), msg],
        })),

      clearMessages: () => set({ messages: [], conversationId: null }),

      setConversationId: (id) => set({ conversationId: id }),

      updateStatus: (s) =>
        set((state) => ({ status: { ...state.status, ...s } })),

      setListening: (v) => set({ isListening: v }),
      setSpeaking:  (v) => set({ isSpeaking: v }),
      setTheme:     (t) => set({ theme: t }),
      setLanguage:  (l) => set({ language: l }),
      setServerUrl: (url) => set({ serverUrl: url }),
      setWakeWord:  (w) => set({ wakeWord: w }),
      setAlwaysListen: (v) => set({ alwaysListen: v }),
      setConnected: (v) => set({ isConnected: v }),
      setPendingOffline: (n) => set({ pendingOfflineMessages: n }),
    }),
    {
      name: "personal-ai-store",
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        theme: state.theme,
        language: state.language,
        serverUrl: state.serverUrl,
        wakeWord: state.wakeWord,
        alwaysListen: state.alwaysListen,
        conversationId: state.conversationId,
        messages: state.messages.slice(-50),
      }),
    }
  )
);
