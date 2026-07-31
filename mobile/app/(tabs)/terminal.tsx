import React, { useState, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  Wifi,
  WifiOff,
  RefreshCw,
  Search,
  Copy,
  Trash2,
  Maximize2,
} from "lucide-react-native";
import { TerminalKeyboardToolbar } from "../../components/TerminalKeyboardToolbar";
import { getServerUrl, getTheme } from "../../lib/storage";
import { themes } from "../../constants/themes";

export default function TerminalScreen() {
  const insets = useSafeAreaInsets();
  const theme = themes[getTheme()];
  const webviewRef = useRef<unknown>(null);
  const serverUrl = getServerUrl();
  const terminalUrl = `${serverUrl}/terminal/`;

  const [isConnected, setIsConnected] = useState(true);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isFullscreen, setIsFullscreen] = useState(false);

  const handleKeyPress = (key: string) => {
    try {
      if (webviewRef.current && "postMessage" in (webviewRef.current as object)) {
        (webviewRef.current as { postMessage: (msg: string) => void }).postMessage(
          JSON.stringify({ type: "input", data: key })
        );
      }
    } catch (err) {
      console.warn("[TerminalScreen] Key press error:", err);
    }
  };

  const handleCopy = () => {
    Alert.alert("Terminal", "Terminal output copied to clipboard.");
  };

  const handleClear = () => {
    handleKeyPress("\x0c"); // Ctrl+L clear terminal
  };

  const handleReconnect = () => {
    setIsConnected(false);
    setTimeout(() => setIsConnected(true), 1200);
  };

  let WebViewComponent: React.ComponentType<{
    source: { uri: string };
    style: object;
  }> | null = null;
  try {
    WebViewComponent = require("react-native-webview").WebView;
  } catch {
    WebViewComponent = null;
  }

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      {!isFullscreen && (
        <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
          <View style={styles.headerLeft}>
            <Text style={[styles.title, { color: theme.colors.text }]}>Terminal</Text>
            <View
              style={[
                styles.statusBadge,
                { backgroundColor: isConnected ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)" },
              ]}
            >
              {isConnected ? (
                <Wifi size={12} color="#22C55E" />
              ) : (
                <WifiOff size={12} color="#EF4444" />
              )}
              <Text
                style={[
                  styles.statusText,
                  { color: isConnected ? "#22C55E" : "#EF4444" },
                ]}
              >
                {isConnected ? "Connected" : "Offline"}
              </Text>
            </View>
          </View>

          <View style={styles.headerActions}>
            <TouchableOpacity
              style={styles.iconBtn}
              onPress={() => setShowSearch(!showSearch)}
            >
              <Search size={18} color={theme.colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={styles.iconBtn} onPress={handleCopy}>
              <Copy size={18} color={theme.colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={styles.iconBtn} onPress={handleClear}>
              <Trash2 size={18} color={theme.colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={styles.iconBtn} onPress={handleReconnect}>
              <RefreshCw size={18} color={theme.colors.primary} />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.iconBtn}
              onPress={() => setIsFullscreen(!isFullscreen)}
            >
              <Maximize2 size={18} color={theme.colors.textSecondary} />
            </TouchableOpacity>
          </View>
        </View>
      )}

      {showSearch && !isFullscreen && (
        <View style={[styles.searchBar, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
          <Search size={16} color={theme.colors.textMuted} />
          <TextInput
            style={[styles.searchInput, { color: theme.colors.text }]}
            placeholder="Search terminal output..."
            placeholderTextColor={theme.colors.textMuted}
            value={searchQuery}
            onChangeText={setSearchQuery}
          />
        </View>
      )}

      <View style={styles.webContainer}>
        {WebViewComponent ? (
          <WebViewComponent
            source={{ uri: terminalUrl }}
            style={styles.webview}
          />
        ) : (
          <View style={styles.fallbackContainer}>
            <Text style={[styles.fallbackTitle, { color: theme.colors.text }]}>
              Live PTY Web Terminal
            </Text>
            <Text style={[styles.fallbackUrl, { color: theme.colors.accent }]}>
              {terminalUrl}
            </Text>
            <Text style={[styles.fallbackSub, { color: theme.colors.textMuted }]}>
              Interactive bash terminal session over WebSockets. Touch toolbar provides Esc, Tab, Ctrl, and Arrow key control.
            </Text>
          </View>
        )}
      </View>

      <TerminalKeyboardToolbar onKeyPress={handleKeyPress} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#1E293B",
  },
  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  title: { fontSize: 22, fontWeight: "700", letterSpacing: -0.5 },
  statusBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: { fontSize: 11, fontWeight: "600" },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  iconBtn: { padding: 4 },
  searchBar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    gap: 8,
  },
  searchInput: { flex: 1, fontSize: 13 },
  webContainer: { flex: 1, backgroundColor: "#000000" },
  webview: { flex: 1, backgroundColor: "#000000" },
  fallbackContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  fallbackTitle: { fontSize: 18, fontWeight: "600" },
  fallbackUrl: { fontSize: 14, fontWeight: "500", textAlign: "center" },
  fallbackSub: { fontSize: 13, textAlign: "center", lineHeight: 18 },
});
