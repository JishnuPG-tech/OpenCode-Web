import React from "react";
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  StyleSheet,
} from "react-native";
import { AlertCircle } from "lucide-react-native";
import { themes } from "../constants/themes";
import { getTheme } from "../lib/storage";

interface ConfirmDialogProps {
  visible: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  isDanger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  visible,
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  isDanger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const theme = themes[getTheme()];

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onCancel}
    >
      <TouchableOpacity style={styles.overlay} activeOpacity={1} onPress={onCancel}>
        <View
          style={[
            styles.dialog,
            { backgroundColor: theme.colors.surface, borderColor: theme.colors.border },
          ]}
          onStartShouldSetResponder={() => true}
        >
          <View style={styles.header}>
            <AlertCircle size={20} color={isDanger ? theme.colors.danger : theme.colors.warning} />
            <Text style={[styles.title, { color: theme.colors.text }]}>{title}</Text>
          </View>

          <Text style={[styles.message, { color: theme.colors.textSecondary }]}>
            {message}
          </Text>

          <View style={styles.actions}>
            <TouchableOpacity
              style={[styles.btn, { backgroundColor: theme.colors.bgTertiary }]}
              onPress={onCancel}
            >
              <Text style={[styles.btnText, { color: theme.colors.text }]}>{cancelText}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.btn,
                { backgroundColor: isDanger ? theme.colors.danger : theme.colors.primary },
              ]}
              onPress={onConfirm}
            >
              <Text style={[styles.btnText, { color: "#FFFFFF" }]}>{confirmText}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.75)",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  dialog: {
    width: "100%",
    maxWidth: 360,
    borderRadius: 24,
    borderWidth: 1,
    padding: 20,
    gap: 12,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: "700",
  },
  message: {
    fontSize: 14,
    lineHeight: 20,
  },
  actions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 10,
    marginTop: 8,
  },
  btn: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 10,
  },
  btnText: {
    fontSize: 14,
    fontWeight: "600",
  },
});
