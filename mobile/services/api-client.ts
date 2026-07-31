import axios from "axios";
import { useAppStore } from "../store";

export const apiClient = axios.create({
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const serverUrl = useAppStore.getState().serverUrl;
  if (serverUrl && !config.baseURL) {
    config.baseURL = serverUrl;
  }
  return config;
});
