import React, { useState, useEffect } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  FlatList,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import { ChevronDown, Check, Sparkles, Cpu } from "lucide-react-native";
import { getModels, getProviders } from "../lib/api";
import type { Model, Provider } from "../constants/types";

interface ModelSelectorProps {
  selectedModel?: string;
  onSelectModel: (modelId: string) => void;
  style?: object;
}

export function ModelSelector({
  selectedModel,
  onSelectModel,
  style,
}: ModelSelectorProps) {
  const [modalVisible, setModalVisible] = useState(false);
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (modalVisible && models.length === 0) {
      fetchAvailableModels();
    }
  }, [modalVisible]);

  const fetchAvailableModels = async () => {
    setLoading(true);
    try {
      const availableModels = await getModels();
      setModels(availableModels);
    } catch (err) {
      console.warn("[ModelSelector] Failed to fetch models:", err);
      // Fallback default model options
      setModels([
        { id: "groq/llama-3.3-70b-versatile", name: "Groq Llama 3.3 70B (Fast LPU)", providerID: "groq" },
        { id: "google/gemini-2.0-flash-exp", name: "Gemini 2.0 Flash (Google)", providerID: "google" },
        { id: "github/gpt-4o", name: "GPT-4o (GitHub Copilot)", providerID: "github" },
        { id: "openrouter/meta-llama/llama-3.3-70b-instruct:free", name: "Llama 3.3 70B (OpenRouter Free)", providerID: "openrouter" },
      ] as Model[]);
    } finally {
      setLoading(false);
    }
  };

  const getModelLabel = (id?: string) => {
    if (!id) return "Groq Llama 3.3 70B";
    const found = models.find((m) => m.id === id);
    if (found) return found.name || found.id;
    if (id.includes("groq")) return "Groq Llama 3.3 70B";
    if (id.includes("gemini")) return "Gemini 2.0 Flash";
    if (id.includes("gpt-4o")) return "GPT-4o";
    return id.split("/").pop() || id;
  };

  return (
    <View style={[styles.container, style]}>
      <TouchableOpacity
        style={styles.triggerButton}
        onPress={() => setModalVisible(true)}
        activeOpacity={0.7}
      >
        <Sparkles size={16} color="#60A5FA" style={styles.sparkleIcon} />
        <Text style={styles.triggerText} numberOfLines={1}>
          {getModelLabel(selectedModel)}
        </Text>
        <ChevronDown size={16} color="#9CA3AF" />
      </TouchableOpacity>

      <Modal
        visible={modalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setModalVisible(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setModalVisible(false)}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <View style={styles.headerTitleRow}>
                <Cpu size={18} color="#60A5FA" />
                <Text style={styles.modalTitle}>Select AI Model</Text>
              </View>
              <Text style={styles.modalSubtitle}>
                Choose AI engine for completion speed & capabilities
              </Text>
            </View>

            {loading ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="small" color="#60A5FA" />
                <Text style={styles.loadingText}>Fetching available models...</Text>
              </View>
            ) : (
              <FlatList
                data={models}
                keyExtractor={(item) => item.id}
                renderItem={({ item }) => {
                  const isSelected = selectedModel === item.id;
                  return (
                    <TouchableOpacity
                      style={[
                        styles.modelItem,
                        isSelected && styles.selectedModelItem,
                      ]}
                      onPress={() => {
                        onSelectModel(item.id);
                        setModalVisible(false);
                      }}
                    >
                      <View style={styles.modelItemTextContainer}>
                        <Text style={styles.modelItemName}>
                          {item.name || item.id}
                        </Text>
                        <Text style={styles.modelItemProvider}>
                          {item.providerID || "AI Provider"}
                        </Text>
                      </View>

                      {isSelected && (
                        <Check size={18} color="#60A5FA" style={styles.checkIcon} />
                      )}
                    </TouchableOpacity>
                  );
                }}
              />
            )}
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignSelf: "center",
  },
  triggerButton: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1E293B",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#334155",
  },
  sparkleIcon: {
    marginRight: 6,
  },
  triggerText: {
    color: "#F8FAFC",
    fontSize: 13,
    fontWeight: "600",
    marginRight: 6,
    maxWidth: 160,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.7)",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  modalContent: {
    width: "100%",
    maxWidth: 400,
    maxHeight: 480,
    backgroundColor: "#0F172A",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#334155",
    overflow: "hidden",
  },
  modalHeader: {
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#1E293B",
  },
  headerTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  modalTitle: {
    color: "#F8FAFC",
    fontSize: 16,
    fontWeight: "700",
  },
  modalSubtitle: {
    color: "#94A3B8",
    fontSize: 12,
    marginTop: 4,
  },
  loadingContainer: {
    padding: 32,
    alignItems: "center",
    gap: 12,
  },
  loadingText: {
    color: "#94A3B8",
    fontSize: 13,
  },
  modelItem: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#1E293B",
  },
  selectedModelItem: {
    backgroundColor: "#1E293B",
  },
  modelItemTextContainer: {
    flex: 1,
  },
  modelItemName: {
    color: "#F8FAFC",
    fontSize: 14,
    fontWeight: "600",
  },
  modelItemProvider: {
    color: "#64748B",
    fontSize: 11,
    marginTop: 2,
    textTransform: "uppercase",
  },
  checkIcon: {
    marginLeft: 8,
  },
});
