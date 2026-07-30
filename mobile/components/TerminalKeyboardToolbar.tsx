import React from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
} from "react-native";
import { CornerDownLeft, ArrowUp, ArrowDown, ArrowLeft, ArrowRight } from "lucide-react-native";

interface TerminalKeyboardToolbarProps {
  onKeyPress: (key: string) => void;
}

export function TerminalKeyboardToolbar({ onKeyPress }: TerminalKeyboardToolbarProps) {
  const keys = [
    { label: "Esc", val: "\x1b" },
    { label: "Tab", val: "\t" },
    { label: "Ctrl+C", val: "\x03" },
    { label: "Ctrl+D", val: "\x04" },
    { label: "Ctrl+L", val: "\x0c" },
    { label: "/", val: "/" },
    { label: "-", val: "-" },
    { label: "~", val: "~" },
    { label: "|", val: "|" },
  ];

  return (
    <View style={styles.container}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        {keys.map((k) => (
          <TouchableOpacity
            key={k.label}
            style={styles.keyButton}
            onPress={() => onKeyPress(k.val)}
            activeOpacity={0.7}
          >
            <Text style={styles.keyText}>{k.label}</Text>
          </TouchableOpacity>
        ))}

        <TouchableOpacity
          style={styles.keyButtonIcon}
          onPress={() => onKeyPress("\x1b[A")} // Up arrow
          activeOpacity={0.7}
        >
          <ArrowUp size={16} color="#94A3B8" />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.keyButtonIcon}
          onPress={() => onKeyPress("\x1b[B")} // Down arrow
          activeOpacity={0.7}
        >
          <ArrowDown size={16} color="#94A3B8" />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.keyButtonIcon}
          onPress={() => onKeyPress("\x1b[D")} // Left arrow
          activeOpacity={0.7}
        >
          <ArrowLeft size={16} color="#94A3B8" />
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.keyButtonIcon}
          onPress={() => onKeyPress("\x1b[C")} // Right arrow
          activeOpacity={0.7}
        >
          <ArrowRight size={16} color="#94A3B8" />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.keyButtonIcon, styles.enterKey]}
          onPress={() => onKeyPress("\r")} // Enter
          activeOpacity={0.7}
        >
          <CornerDownLeft size={16} color="#60A5FA" />
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#0F172A",
    borderTopWidth: 1,
    borderTopColor: "#1E293B",
    paddingVertical: 6,
  },
  scrollContent: {
    paddingHorizontal: 8,
    alignItems: "center",
    gap: 6,
  },
  keyButton: {
    backgroundColor: "#1E293B",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#334155",
    minWidth: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  keyButtonIcon: {
    backgroundColor: "#1E293B",
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#334155",
    alignItems: "center",
    justify.content: "center",
  },
  enterKey: {
    backgroundColor: "#1E293B",
    borderColor: "#3B82F6",
  },
  keyText: {
    color: "#F8FAFC",
    fontSize: 12,
    fontWeight: "600",
    fontFamily: "monospace",
  },
});
