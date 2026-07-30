import React, { useState } from "react";
import {
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  Alert,
} from "react-native";
import { Paperclip } from "lucide-react-native";
import { uploadFile } from "../lib/api";

interface FileUploadButtonProps {
  onFileUploaded: (filePath: string) => void;
  style?: object;
}

export function FileUploadButton({ onFileUploaded, style }: FileUploadButtonProps) {
  const [uploading, setUploading] = useState(false);

  const handlePickAndUpload = async () => {
    try {
      // Lazy load document picker or fallback
      let result;
      try {
        const DocumentPicker = require("expo-document-picker");
        result = await DocumentPicker.getDocumentAsync({
          type: "*/*",
          copyToCacheDirectory: true,
        });
      } catch {
        Alert.alert(
          "Attachment",
          "File picker requires Expo DocumentPicker. Please select a file from workspace browser."
        );
        return;
      }

      if (result.canceled || !result.assets || result.assets.length === 0) {
        return;
      }

      const asset = result.assets[0];
      setUploading(true);

      const uploaded = await uploadFile({
        uri: asset.uri,
        name: asset.name || "upload_file",
        type: asset.mimeType || "application/octet-stream",
      });

      onFileUploaded(uploaded.path);
    } catch (err: unknown) {
      console.warn("[FileUploadButton] Upload error:", err);
      const msg = err instanceof Error ? err.message : "Upload failed";
      Alert.alert("Upload Failed", msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <TouchableOpacity
      style={[styles.button, style]}
      onPress={handlePickAndUpload}
      disabled={uploading}
      activeOpacity={0.7}
    >
      {uploading ? (
        <ActivityIndicator size="small" color="#60A5FA" />
      ) : (
        <Paperclip size={20} color="#94A3B8" />
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    padding: 8,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1E293B",
  },
});
