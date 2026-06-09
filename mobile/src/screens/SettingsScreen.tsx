import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { ping, setBaseUrl } from '../services/chatApi';

interface Props {
  serverUrl: string;
  deviceName: string;
  onSaveUrl: (url: string) => void;
  onSaveDeviceName: (name: string) => void;
  onDisconnect: () => void;
}

export function SettingsScreen({
  serverUrl,
  deviceName,
  onSaveUrl,
  onSaveDeviceName,
  onDisconnect,
}: Props) {
  const [urlInput, setUrlInput] = useState(serverUrl);
  const [nameInput, setNameInput] = useState(deviceName);
  const [testing, setTesting] = useState(false);

  const handleSaveUrl = async () => {
    const clean = urlInput.trim().replace(/\/$/, '');
    setTesting(true);
    setBaseUrl(clean);
    try {
      const ok = await ping();
      if (ok) {
        onSaveUrl(clean);
        Alert.alert('Connected', 'Server connection verified.');
      } else {
        Alert.alert('Connection Failed', `Could not reach:\n${clean}`);
      }
    } catch {
      Alert.alert('Error', 'Network error.');
    } finally {
      setTesting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.sectionTitle}>SERVER</Text>
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>URL</Text>
          <TextInput
            style={styles.input}
            value={urlInput}
            onChangeText={setUrlInput}
            placeholder="http://192.168.1.x:25314"
            placeholderTextColor="#4b5563"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
          <TouchableOpacity
            style={[styles.saveBtn, testing && styles.saveBtnDisabled]}
            onPress={handleSaveUrl}
            disabled={testing}
          >
            {testing ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.saveBtnText}>TEST & SAVE</Text>
            )}
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionTitle}>DEVICE</Text>
        <View style={styles.card}>
          <Text style={styles.fieldLabel}>DEVICE NAME</Text>
          <TextInput
            style={styles.input}
            value={nameInput}
            onChangeText={setNameInput}
            placeholder="My iPhone"
            placeholderTextColor="#4b5563"
            returnKeyType="done"
            onSubmitEditing={() => onSaveDeviceName(nameInput.trim() || 'Mobile')}
          />
          <TouchableOpacity
            style={styles.saveBtn}
            onPress={() => {
              onSaveDeviceName(nameInput.trim() || 'Mobile');
              Alert.alert('Saved', 'Device name updated. Reconnect the node to apply.');
            }}
          >
            <Text style={styles.saveBtnText}>SAVE NAME</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity style={styles.disconnectBtn} onPress={onDisconnect}>
          <Text style={styles.disconnectText}>DISCONNECT & RESET</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  content: {
    padding: 16,
    gap: 16,
  },
  sectionTitle: {
    color: '#6b7280',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 2,
    marginBottom: -8,
  },
  card: {
    backgroundColor: '#111827',
    borderWidth: 1.5,
    borderColor: '#1f2937',
    borderRadius: 12,
    padding: 16,
    gap: 10,
  },
  fieldLabel: {
    color: '#9ca3af',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  input: {
    backgroundColor: '#1f2937',
    borderWidth: 1.5,
    borderColor: '#374151',
    borderRadius: 8,
    color: '#f3f4f6',
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  saveBtn: {
    backgroundColor: '#4f46e5',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
  },
  saveBtnDisabled: {
    opacity: 0.5,
  },
  saveBtnText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  disconnectBtn: {
    borderWidth: 1.5,
    borderColor: '#374151',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  disconnectText: {
    color: '#6b7280',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
  },
});
