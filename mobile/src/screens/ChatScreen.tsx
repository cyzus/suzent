import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { MessageBubble } from '../components/MessageBubble';
import { fetchChatMessages, sendMessage, stopStream } from '../services/chatApi';
import { ChatMessage } from '../types';

interface Props {
  chatId: string | null;
  onChatIdChange: (id: string) => void;
}

export function ChatScreen({ chatId, onChatIdChange }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const listRef = useRef<FlatList>(null);
  const streamingMsgId = useRef<string | null>(null);

  const loadHistory = useCallback(async () => {
    if (!chatId) return;
    setLoading(true);
    try {
      const msgs = await fetchChatMessages(chatId);
      setMessages(msgs);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const scrollToEnd = () => {
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    setInput('');
    setStreaming(true);

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    const assistantId = `assistant-${Date.now()}`;
    streamingMsgId.current = assistantId;

    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    scrollToEnd();

    await sendMessage(text, chatId, {
      onToken: (delta) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + delta } : m
          )
        );
        scrollToEnd();
      },
      onDone: (finalChatId) => {
        setStreaming(false);
        streamingMsgId.current = null;
        if (finalChatId && finalChatId !== chatId) {
          onChatIdChange(finalChatId);
        }
      },
      onError: (err) => {
        setStreaming(false);
        streamingMsgId.current = null;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `⚠ Error: ${err}` }
              : m
          )
        );
      },
    });
  };

  const handleStop = async () => {
    if (chatId) await stopStream(chatId);
    setStreaming(false);
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color="#4f46e5" />
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.id}
          renderItem={({ item }) => <MessageBubble message={item} />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>SUZENT</Text>
              <Text style={styles.emptySubtitle}>How can I help?</Text>
            </View>
          }
          onContentSizeChange={scrollToEnd}
        />
      )}

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Message…"
          placeholderTextColor="#4b5563"
          multiline
          maxLength={4000}
          returnKeyType="send"
          onSubmitEditing={handleSend}
          blurOnSubmit={false}
          editable={!streaming}
        />
        {streaming ? (
          <TouchableOpacity style={styles.stopBtn} onPress={handleStop}>
            <Text style={styles.stopText}>■</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={[styles.sendBtn, !input.trim() && styles.sendBtnDisabled]}
            onPress={handleSend}
            disabled={!input.trim()}
          >
            <Text style={styles.sendText}>↑</Text>
          </TouchableOpacity>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  list: {
    paddingTop: 12,
    paddingBottom: 8,
  },
  empty: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 120,
    gap: 6,
  },
  emptyTitle: {
    color: '#1f2937',
    fontSize: 32,
    fontWeight: '900',
    letterSpacing: 6,
  },
  emptySubtitle: {
    color: '#374151',
    fontSize: 14,
    letterSpacing: 1,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: '#1f2937',
    gap: 8,
    backgroundColor: '#0a0a0a',
  },
  input: {
    flex: 1,
    backgroundColor: '#111827',
    borderWidth: 1.5,
    borderColor: '#1f2937',
    borderRadius: 10,
    color: '#f3f4f6',
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxHeight: 120,
  },
  sendBtn: {
    backgroundColor: '#4f46e5',
    width: 42,
    height: 42,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: '#1f2937',
  },
  sendText: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  stopBtn: {
    backgroundColor: '#7f1d1d',
    width: 42,
    height: 42,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#ef4444',
  },
  stopText: {
    color: '#ef4444',
    fontSize: 16,
    fontWeight: '700',
  },
});
