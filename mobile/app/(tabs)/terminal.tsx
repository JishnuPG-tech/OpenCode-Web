import React, { useRef } from "react";
import { View, Text, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { TerminalKeyboardToolbar } from "../../components/TerminalKeyboardToolbar";
import { getServerUrl, getTheme } from "../../lib/storage";
import { themes } from "../../constants/themes";

export default function TerminalScreen() {
  const insets = useSafeAreaInsets();
  const theme = themes[getTheme()];
  const webviewRef = useRef<unknown>(null);
  const serverUrl = getServerUrl();
  const terminalUrl = `${serverUrl}/terminal/`;

  const handleKeyPress = (key: string) => {
    try {
      // Send key stroke to terminal webview if available
      if (webviewRef.current && "postMessage" in (webviewRef.current as object)) {
        (webviewRef.current as { postMessage: (msg: string) => void }).postMessage(
          JSON.stringify({ type: "input", data: key })
        );
      }
    } catch (err) {
      console.warn("[TerminalScreen] Key press error:", err);
    }
  };

  // Try loading React Native WebView
  let WebViewComponent: React.ComponentType<{ source: { uri: string }; style: object }> | null = null;
  try {
    WebViewComponent = require("react-native-webview").WebView;
  } catch {
    WebViewComponent = null;
  }

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.bg }]}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={[styles.title, { color: theme.colors.text }]}>Terminal</Text>
      </View>

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
              Open this link in your browser or install react-native-webview for embedded terminal.
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
    paddingHorizontal: 20,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#1E293B",
  },
  title: { fontSize: 24, fontWeight: "700", letterSpacing: -0.5 },
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
