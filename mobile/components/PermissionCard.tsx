import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { Shield, Check, CheckCheck, X } from "lucide-react-native";
import { themes } from "../constants/themes";
import { getTheme } from "../lib/storage";
import type { PermissionRequest } from "../constants/types";

interface PermissionCardProps {
  request: PermissionRequest;
  onAllowOnce: () => void;
  onAlwaysAllow?: () => void;
  onDeny: () => void;
}

export function PermissionCard({
  request,
  onAllowOnce,
  onAlwaysAllow,
  onDeny,
}: PermissionCardProps) {
  const theme = themes[getTheme()];

  return (
    <View style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
      <View style={styles.header}>
        <Shield size={18} color={theme.colors.warning} />
        <Text style={[styles.title, { color: theme.colors.text }]}>Permission Requested</Text>
      </View>

      <Text style={[styles.permission, { color: theme.colors.textSecondary }]}>
        {request.permission}
      </Text>

      {request.description ? (
        <Text style={[styles.description, { color: theme.colors.textMuted }]}>
          {request.description}
        </Text>
      ) : null}

      <View style={styles.actions}>
        <TouchableOpacity
          style={[styles.denyBtn, { backgroundColor: theme.colors.bgTertiary, borderColor: theme.colors.border }]}
          onPress={onDeny}
          activeOpacity={0.7}
        >
          <X size={14} color={theme.colors.danger} />
          <Text style={[styles.denyText, { color: theme.colors.danger }]}>Deny</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.allowBtn, { backgroundColor: theme.colors.accent }]}
          onPress={onAllowOnce}
          activeOpacity={0.7}
        >
          <Check size={14} color="#fff" />
          <Text style={styles.allowText}>Allow Once</Text>
        </TouchableOpacity>

        {onAlwaysAllow && (
          <TouchableOpacity
            style={[styles.alwaysBtn, { backgroundColor: theme.colors.success }]}
            onPress={onAlwaysAllow}
            activeOpacity={0.7}
          >
            <CheckCheck size={14} color="#fff" />
            <Text style={styles.allowText}>Always</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    gap: 8,
    marginVertical: 6,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  title: {
    fontSize: 14,
    fontWeight: "700",
  },
  permission: {
    fontSize: 13,
    fontWeight: "600",
    fontFamily: "monospace",
  },
  description: {
    fontSize: 12,
    lineHeight: 16,
  },
  actions: {
    flexDirection: "row",
    gap: 6,
    marginTop: 6,
  },
  denyBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
  },
  denyText: {
    fontSize: 12,
    fontWeight: "600",
  },
  allowBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justify.content: "center",
    gap: 4,
    paddingVertical: 8,
    borderRadius: 8,
  },
  alwaysBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justify.content: "center",
    gap: 4,
    paddingVertical: 8,
    borderRadius: 8,
  },
  allowText: {
    fontSize: 12,
    fontWeight: "600",
    color: "#FFFFFF",
  },
});
