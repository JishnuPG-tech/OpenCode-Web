import React, { useState, useEffect } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  Modal,
  FlatList,
  TextInput,
  StyleSheet,
  ActivityIndicator,
} from "react-native";
import { ChevronDown, Check, Sparkles, Cpu, Search, Layers } from "lucide-react-native";
import { getModels, getProviders, patchConfig } from "../lib/api";
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
  const [providers, setProviders] = useState<Provider[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (modalVisible && models.length === 0) {
      fetchOpenCodeData();
    }
  }, [modalVisible]);

  const fetchOpenCodeData = async () => {
    setLoading(true);
    try {
      const [fetchedModels, fetchedProviders] = await Promise.all([
        getModels().catch(() => []),
        getProviders().catch(() => []),
      ]);

      if (fetchedModels && fetchedModels.length > 0) {
        setModels(fetchedModels);
      } else {
        // Fallback default OpenCode models
        setModels([
          { id: "groq/llama-3.3-70b-versatile", name: "Llama 3.3 70B (Groq LPU)", providerID: "groq" },
          { id: "google/gemini-2.0-flash-exp", name: "Gemini 2.0 Flash (Google)", providerID: "google" },
          { id: "github/gpt-4o", name: "GPT-4o (GitHub Copilot)", providerID: "github" },
          { id: "openrouter/meta-llama/llama-3.3-70b-instruct:free", name: "Llama 3.3 70B (OpenRouter)", providerID: "openrouter" },
          { id: "anthropic/claude-3-5-sonnet-20241022", name: "Claude 3.5 Sonnet (Anthropic)", providerID: "anthropic" },
        ] as Model[]);
      }

      if (fetchedProviders) {
        setProviders(fetchedProviders);
      }
    } catch (err) {
      console.warn("[ModelSelector] Error fetching OpenCode models:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (modelId: string) => {
    onSelectModel(modelId);
    setModalVisible(false);

    // Sync default model selection with OpenCode Serve backend config
    try {
      await patchConfig({ model: modelId });
    } catch {
      // ignore
    }
  };

  const getModelLabel = (id?: string) => {
    if (!id) return "Groq Llama 3.3 70B";
    const found = models.find((m) => m.id === id);
    if (found) return found.name || found.id;
    if (id.includes("groq")) return "Groq Llama 3.3 70B";
    if (id.includes("gemini")) return "Gemini 2.0 Flash";
    if (id.includes("gpt-4o")) return "GPT-4o";
    if (id.includes("claude")) return "Claude 3.5 Sonnet";
    return id.split("/").pop() || id;
  };

  const filteredModels = models.filter((m) => {
    const q = searchQuery.toLowerCase();
    return (
      m.id.toLowerCase().includes(q) ||
      (m.name && m.name.toLowerCase().includes(q)) ||
      (m.providerID && m.providerID.toLowerCase().includes(q))
    );
  });

  return (
    <View style={[styles.container, style]}>
      <TouchableOpacity
        style={styles.triggerButton}
        onPress={() => setModalVisible(true)}
        activeOpacity={0.75}
      >
        <Sparkles size={15} color="#60A5FA" style={styles.sparkleIcon} />
        <Text style={styles.triggerText} numberOfLines={1}>
          {getModelLabel(selectedModel)}
        </Text>
        <ChevronDown size={15} color="#9CA3AF" />
      </TouchableOpacity>

      <Modal
        visible={modalVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setModalVisible(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setModalVisible(false)}
        >
          <View style={styles.modalContent} onStartShouldSetResponder={() => true}>
            <View style={styles.modalHeader}>
              <View style={styles.headerTitleRow}>
                <Cpu size={18} color="#60A5FA" />
                <Text style={styles.modalTitle}>OpenCode Model Picker</Text>
              </View>
              <Text style={styles.modalSubtitle}>
                Models configured on your OpenCode Serve backend
              </Text>
            </View>

            {/* Filter Search Bar */}
            <View style={styles.searchContainer}>
              <Search size={16} color="#64748B" />
              <TextInput
                style={styles.searchInput}
                placeholder="Filter models or providers..."
                placeholderTextColor="#64748B"
                value={searchQuery}
                onChangeText={setSearchQuery}
                autoCapitalize="none"
              />
            </View>

            {loading ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="small" color="#60A5FA" />
                <Text style={styles.loadingText}>Fetching OpenCode providers & models...</Text>
              </View>
            ) : (
              <FlatList
                data={filteredModels}
                keyExtractor={(item) => item.id}
                contentContainerStyle={{ paddingBottom: 16 }}
                renderItem={({ item }) => {
                  const isSelected = selectedModel === item.id;
                  return (
                    <TouchableOpacity
                      style={[
                        styles.modelItem,
                        isSelected && styles.selectedModelItem,
                      ]}
                      onPress={() => handleSelect(item.id)}
                      activeOpacity={0.7}
                    >
                      <View style={styles.modelItemTextContainer}>
                        <View style={styles.modelNameRow}>
                          <Layers size={14} color="#60A5FA" />
                          <Text style={styles.modelItemName}>
                            {item.name || item.id}
                          </Text>
                        </View>
                        <Text style={styles.modelItemDetails}>
                          {item.id}
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
    maxWidth: 170,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.75)",
    justifyContent: "flex-end",
  },
  modalContent: {
    width: "100%",
    maxHeight: "75%",
    backgroundColor: "#0F172A",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderWidth: 1,
    borderColor: "#334155",
    paddingBottom: 24,
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
  searchContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "#1E293B",
    margin: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#334155",
  },
  searchInput: {
    flex: 1,
    color: "#F8FAFC",
    fontSize: 13,
    padding: 0,
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
  modelNameRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  modelItemName: {
    color: "#F8FAFC",
    fontSize: 14,
    fontWeight: "600",
  },
  modelItemDetails: {
    color: "#64748B",
    fontSize: 11,
    fontFamily: "monospace",
    marginTop: 3,
  },
  checkIcon: {
    marginLeft: 8,
  },
});
