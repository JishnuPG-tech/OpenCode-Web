import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Folder, FileText, ChevronRight, FileCode } from "lucide-react-native";
import { themes } from "../constants/themes";
import { getTheme } from "../lib/storage";

interface FileRowProps {
  name: string;
  type: "file" | "directory";
  size?: number;
  onPress: () => void;
  onLongPress?: () => void;
}

export function FileRow({
  name,
  type,
  size,
  onPress,
  onLongPress,
}: FileRowProps) {
  const theme = themes[getTheme()];

  const getIcon = () => {
    if (type === "directory") {
      return <Folder size={18} color={theme.colors.warning} />;
    }
    if (name.endsWith(".ts") || name.endsWith(".tsx") || name.endsWith(".js") || name.endsWith(".py")) {
      return <FileCode size={18} color={theme.colors.primary} />;
    }
    return <FileText size={18} color={theme.colors.textMuted} />;
  };

  return (
    <TouchableOpacity
      style={[styles.row, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}
      onPress={onPress}
      onLongPress={onLongPress}
      activeOpacity={0.7}
    >
      <View style={styles.iconContainer}>{getIcon()}</View>
      <Text style={[styles.fileName, { color: theme.colors.text }]} numberOfLines={1}>
        {name}
      </Text>
      {type === "directory" ? (
        <ChevronRight size={16} color={theme.colors.textMuted} />
      ) : size ? (
        <Text style={[styles.fileSize, { color: theme.colors.textMuted }]}>
          {(size / 1024).toFixed(1)} KB
        </Text>
      ) : null}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
    borderWidth: 1,
    marginVertical: 3,
    gap: 12,
  },
  iconContainer: {
    alignItems: "center",
    justifyContent: "center",
  },
  fileName: {
    flex: 1,
    fontSize: 14,
    fontWeight: "500",
  },
  fileSize: {
    fontSize: 11,
    fontFamily: "monospace",
  },
});
