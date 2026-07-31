import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ToolTimeline } from "./ToolTimeline";
import type { MessagePart, ToolPart } from "../constants/types";
import { themes } from "../constants/themes";
import { getTheme } from "../lib/storage";

interface MessageBubbleProps {
  role: "user" | "assistant" | "system";
  parts: MessagePart[];
}

export function MessageBubble({ role, parts }: MessageBubbleProps) {
  const theme = themes[getTheme()];
  const isUser = role === "user";

  const toolParts: ToolPart[] = [];
  const otherParts: MessagePart[] = [];

  for (const p of parts) {
    if (p.type === "tool") toolParts.push(p as ToolPart);
    else otherParts.push(p);
  }

  return (
    <View
      style={[
        styles.bubble,
        isUser
          ? { backgroundColor: theme.colors.primary, alignSelf: "flex-end", maxWidth: "85%" }
          : { backgroundColor: theme.colors.surface, alignSelf: "flex-start", maxWidth: "90%", borderColor: theme.colors.border, borderWidth: 1 },
      ]}
    >
      {otherParts.map((part, i) => {
        if (part.type === "text" && part.text) {
          return <MarkdownRenderer key={i} content={part.text} />;
        }
        if (part.type === "reasoning" && part.text) {
          return (
            <View key={i} style={[styles.reasoningBox, { backgroundColor: theme.colors.bgTertiary }]}>
              <Text style={[styles.reasoningTitle, { color: theme.colors.textMuted }]}>Reasoning</Text>
              <Text style={[styles.reasoningBody, { color: theme.colors.textMuted }]}>
                {part.text}
              </Text>
            </View>
          );
        }
        return null;
      })}

      {toolParts.length > 0 && <ToolTimeline parts={toolParts} />}
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    padding: 14,
    borderRadius: 14,
    marginVertical: 4,
    gap: 8,
  },
  reasoningBox: {
    padding: 10,
    borderRadius: 8,
    marginVertical: 4,
  },
  reasoningTitle: {
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    marginBottom: 2,
  },
  reasoningBody: {
    fontSize: 12,
    fontStyle: "italic",
    lineHeight: 16,
  },
});
