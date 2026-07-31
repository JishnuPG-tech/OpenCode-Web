import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Server, CheckCircle2, AlertCircle } from "lucide-react-native";
import { themes } from "../constants/themes";
import { getTheme } from "../lib/storage";

interface ServerCardProps {
  url: string;
  version?: string;
  isOnline: boolean;
  username?: string;
}

export function ServerCard({
  url,
  version = "v1.18.3",
  isOnline,
  username = "no username",
}: ServerCardProps) {
  const theme = themes[getTheme()];

  return (
    <View style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
      <View style={styles.headerRow}>
        <View style={styles.urlRow}>
          <View
            style={[
              styles.statusDot,
              { backgroundColor: isOnline ? "#22C55E" : "#EF4444" },
            ]}
          />
          <Text style={[styles.urlText, { color: theme.colors.text }]} numberOfLines={1}>
            {url}
          </Text>
        </View>

        {isOnline ? (
          <CheckCircle2 size={16} color="#22C55E" />
        ) : (
          <AlertCircle size={16} color="#EF4444" />
        )}
      </View>

      <Text style={[styles.metaText, { color: theme.colors.textMuted }]}>
        {version} • {username}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginVertical: 6,
    gap: 6,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  urlRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    flex: 1,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  urlText: {
    fontSize: 14,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  metaText: {
    fontSize: 12,
    marginLeft: 16,
  },
});
