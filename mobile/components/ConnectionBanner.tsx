import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Wifi, WifiOff, RefreshCw } from "lucide-react-native";
import { themes } from "../constants/themes";
import { getTheme } from "../lib/storage";

interface ConnectionBannerProps {
  isConnected: boolean;
  serverUrl?: string;
  onReconnect?: () => void;
  style?: object;
}

export function ConnectionBanner({
  isConnected,
  serverUrl = "https://glamorous-destruct-ladder.ngrok-free.dev",
  onReconnect,
  style,
}: ConnectionBannerProps) {
  const theme = themes[getTheme()];

  return (
    <View
      style={[
        styles.banner,
        {
          backgroundColor: isConnected ? "#064E3B" : "#7F1D1D",
          borderColor: isConnected ? "#059669" : "#DC2626",
        },
        style,
      ]}
    >
      <View style={styles.leftRow}>
        {isConnected ? (
          <Wifi size={16} color="#34D399" />
        ) : (
          <WifiOff size={16} color="#FCA5A5" />
        )}
        <View style={styles.textCol}>
          <Text style={styles.statusText}>
            {isConnected ? "Connected to Server" : "Server Disconnected"}
          </Text>
          <Text style={styles.urlText} numberOfLines={1}>
            {serverUrl}
          </Text>
        </View>
      </View>

      {!isConnected && onReconnect && (
        <TouchableOpacity
          style={styles.reconnectBtn}
          onPress={onReconnect}
          activeOpacity={0.7}
        >
          <RefreshCw size={14} color="#FFFFFF" />
          <Text style={styles.reconnectText}>Retry</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
    borderWidth: 1,
    marginVertical: 8,
  },
  leftRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    flex: 1,
  },
  textCol: {
    flex: 1,
  },
  statusText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  urlText: {
    color: "#D1D5DB",
    fontSize: 11,
    fontFamily: "monospace",
    marginTop: 2,
  },
  reconnectBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "rgba(255, 255, 255, 0.2)",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  reconnectText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "600",
  },
});
