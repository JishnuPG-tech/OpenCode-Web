import { create } from "zustand";

interface AppState {
  serverUrl: string;
  activeSessionId: string | null;
  selectedModel: string;
  isConnected: boolean;
  setServerUrl: (url: string) => void;
  setActiveSessionId: (id: string | null) => void;
  setSelectedModel: (model: string) => void;
  setIsConnected: (connected: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  serverUrl: "https://glamorous-destruct-ladder.ngrok-free.dev",
  activeSessionId: null,
  selectedModel: "groq/llama-3.3-70b-versatile",
  isConnected: false,
  setServerUrl: (url) => set({ serverUrl: url }),
  setActiveSessionId: (id) => set({ activeSessionId: id }),
  setSelectedModel: (model) => set({ selectedModel: model }),
  setIsConnected: (connected) => set({ isConnected: connected }),
}));
