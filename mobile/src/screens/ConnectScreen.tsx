import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { ping } from '../services/chatApi';

interface Props {
  currentUrl: string;
  onSave: (url: string) => void;
}

export function ConnectScreen({ currentUrl, onSave }: Props) {
  const [url, setUrl] = useState(currentUrl);
  const [testing, setTesting] = useState(false);

  const handleSave = async () => {
    const clean = url.trim().replace(/\/$/, '');
    if (!clean) return;

    setTesting(true);
    try {
      const ok = await ping();
      if (ok) {
        onSave(clean);
      } else {
        Alert.alert('Connection Failed', `Could not reach suzent at:\n${clean}\n\nMake sure the server is running and your phone is on the same network.`);
      }
    } catch {
      Alert.alert('Connection Error', 'Network error. Check the URL and your network.');
    } finally {
      setTesting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.inner}>
        <Text style={styles.logo}>SUZENT</Text>
        <Text style={styles.tagline}>Your Sovereign Geist</Text>

        <View style={styles.card}>
          <Text style={styles.label}>SERVER URL</Text>
          <TextInput
            style={styles.input}
            value={url}
            onChangeText={setUrl}
            placeholder="http://192.168.1.x:25314"
            placeholderTextColor="#4b5563"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
            onSubmitEditing={handleSave}
          />
          <Text style={styles.hint}>
            Enter the IP and port of your suzent server on the local network.
          </Text>
        </View>

        <TouchableOpacity
          style={[styles.button, testing && styles.buttonDisabled]}
          onPress={handleSave}
          disabled={testing}
          activeOpacity={0.8}
        >
          {testing ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.buttonText}>CONNECT</Text>
          )}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  inner: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
    gap: 20,
  },
  logo: {
    color: '#e0e7ff',
    fontSize: 36,
    fontWeight: '900',
    letterSpacing: 6,
    textAlign: 'center',
  },
  tagline: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 2,
    textAlign: 'center',
    textTransform: 'uppercase',
    marginTop: -12,
  },
  card: {
    backgroundColor: '#111827',
    borderWidth: 2,
    borderColor: '#1f2937',
    borderRadius: 12,
    padding: 20,
    gap: 10,
  },
  label: {
    color: '#9ca3af',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.5,
  },
  input: {
    backgroundColor: '#1f2937',
    borderWidth: 2,
    borderColor: '#374151',
    borderRadius: 8,
    color: '#f3f4f6',
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  hint: {
    color: '#4b5563',
    fontSize: 12,
    lineHeight: 18,
  },
  button: {
    backgroundColor: '#4f46e5',
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#6366f1',
    paddingVertical: 16,
    alignItems: 'center',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '800',
    letterSpacing: 2,
  },
});
