import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { MessageSquare, Trash2, ChevronRight } from "lucide-react-native";
import { themes } from "../constants/themes";
import { getTheme } from "../lib/storage";

interface SessionCardProps {
  title: string;
  updatedAt: string | number;
  messageCount?: number;
  onPress: () => void;
  onDelete?: () => void;
}

export function SessionCard({
  title,
  updatedAt,
  messageCount,
  onPress,
  onDelete,
}: SessionCardProps) {
  const theme = themes[getTheme()];

  const formatDate = (val: string | number) => {
    try {
      const d = new Date(val);
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    } catch {
      return "Recent";
    }
  };

  return (
    <TouchableOpacity
      style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}
      onPress={onPress}
      activeOpacity={0.75}
    >
      <View style={styles.leftRow}>
        <View style={[styles.iconBox, { backgroundColor: theme.colors.bgTertiary }]}>
          <MessageSquare size={18} color={theme.colors.primary} />
        </View>
        <View style={styles.textCol}>
          <Text style={[styles.title, { color: theme.colors.text }]} numberOfLines={1}>
            {title || "Untitled Session"}
          </Text>
          <Text style={[styles.date, { color: theme.colors.textMuted }]}>
            {formatDate(updatedAt)} {messageCount ? `• ${messageCount} msgs` : ""}
          </Text>
        </View>
      </View>

      <View style={styles.rightRow}>
        {onDelete ? (
          <TouchableOpacity style={styles.deleteBtn} onPress={onDelete} activeOpacity={0.7}>
            <Trash2 size={16} color={theme.colors.danger} />
          </TouchableOpacity>
        ) : (
          <ChevronRight size={18} color={theme.colors.textMuted} />
        )}
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginVertical: 4,
  },
  leftRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    flex: 1,
  },
  iconBox: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  textCol: {
    flex: 1,
  },
  title: {
    fontSize: 15,
    fontWeight: "600",
  },
  date: {
    fontSize: 12,
    marginTop: 2,
  },
  rightRow: {
    flexDirection: "row",
    alignItems: "center",
    marginLeft: 8,
  },
  deleteBtn: {
    padding: 6,
  },
});
