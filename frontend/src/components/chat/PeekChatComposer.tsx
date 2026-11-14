import React, { useEffect, useRef, useState } from 'react';
import { ChatInputPanel } from '../ChatInputPanel';
import { QueuedMessages, type QueuedMessage } from './QueuedMessages';
import { useUnifiedFileUpload } from '../../hooks/useUnifiedFileUpload';
import type { VoiceSession } from '../../hooks/useVoiceSession';
import { getApiBase } from '../../lib/api';
import {
  normalizePermissionMode,
  normalizeThinkingEffort,
  type ChatConfig,
  type ConfigOptions,
  type FileAttachment,
} from '../../types/api';

interface PeekChatComposerProps {
  chatId: string;
  /** The chat's stored config; the composer's model and mode pickers start from it. */
  savedConfig: Partial<ChatConfig>;
  backendConfig: ConfigOptions | null;
  voice: VoiceSession;
  running: boolean;
  onSend: (text: string, config: ChatConfig, files?: FileAttachment[]) => Promise<boolean>;
  onImageClick?: (src: string) => void;
  queue: QueuedMessage[];
  onQueueChange: (update: (queue: QueuedMessage[]) => QueuedMessage[]) => void;
}

// How long a fresh send may take to show up as running before the queue moves on.
const START_GRACE_MS = 6000;

function seedConfig(saved: Partial<ChatConfig>, backend: ConfigOptions | null): ChatConfig {
  const prefs = backend?.userPreferences;
  return {
    ...saved,
    model: saved.model || prefs?.model || backend?.defaultModel || '',
    agent: saved.agent || prefs?.agent || backend?.agents?.[0] || '',
    tools: saved.tools ?? prefs?.tools ?? backend?.defaultTools ?? [],
    thinking: normalizeThinkingEffort(saved.thinking ?? prefs?.thinking),
    permission_mode: normalizePermissionMode(
      saved.permission_mode ?? backend?.defaultPermissionMode ?? 'auto'
    ),
  } as ChatConfig;
}

/**
 * The chat's own composer, in the side panel: the same input, attachments and
 * pickers, writing to the peeked chat. A running chat is redirected, as its
 * own composer would.
 */
export const PeekChatComposer: React.FC<PeekChatComposerProps> = ({
  chatId,
  savedConfig,
  backendConfig,
  voice,
  running,
  onSend,
  onImageClick,
  queue,
  onQueueChange,
}) => {
  const [input, setInput] = useState('');
  const [config, setConfig] = useState<ChatConfig>(() => seedConfig(savedConfig, backendConfig));
  const [stopping, setStopping] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    selectedFiles,
    setSelectedFiles,
    fileInputRef,
    handleFileSelect,
    handlePaste,
    removeFile,
    clearFiles,
    uploadFiles,
    uploadProgress,
    isUploading,
    error: fileError,
  } = useUnifiedFileUpload();

  // Between a send and the chat reporting itself running, nothing may leave the queue.
  const [starting, setStarting] = useState(false);
  const sending = useRef(false);
  useEffect(() => {
    if (running || !starting) {
      if (running) setStarting(false);
      return;
    }
    const timer = setTimeout(() => setStarting(false), START_GRACE_MS);
    return () => clearTimeout(timer);
  }, [running, starting]);

  const deliver = async (text: string, files: File[]): Promise<boolean> => {
    sending.current = true;
    try {
      let uploaded: FileAttachment[] | undefined;
      if (files.length > 0) {
        try {
          uploaded = (await uploadFiles(files, chatId)).fileMetadata;
        } catch {
          return false;
        }
      }
      const sent = await onSend(text, config, uploaded);
      if (sent) setStarting(true);
      return sent;
    } finally {
      sending.current = false;
    }
  };

  const send = async (): Promise<void> => {
    const text = input.trim();
    if (!text && selectedFiles.length === 0) return;
    // A redirect carries text only; attachments stay for the next message.
    const files = running ? [] : [...selectedFiles];
    if (await deliver(text, files)) {
      setInput('');
      if (!running) clearFiles();
    }
  };

  // Cmd/Ctrl+Enter: hold the message until the running turn ends.
  const queueMessage = (): void => {
    const text = input.trim();
    if (!text) return;
    if (!running && !starting) {
      void send();
      return;
    }
    const item: QueuedMessage = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      text,
      fileMentions: [],
      files: [...selectedFiles],
    };
    onQueueChange((items) => [...items, item]);
    setInput('');
    clearFiles();
  };

  useEffect(() => {
    if (running || starting || sending.current || queue.length === 0) return;
    const [next] = queue;
    onQueueChange((items) => items.filter((item) => item.id !== next.id));
    void deliver(next.text, next.files);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, starting, queue]);

  const steerQueued = (id: string): void => {
    const item = queue.find((queued) => queued.id === id);
    if (!item) return;
    onQueueChange((items) => items.filter((queued) => queued.id !== id));
    // A redirect carries text only: hand the attachments back to the composer.
    if (item.files.length > 0) setSelectedFiles((prev) => [...item.files, ...prev]);
    void deliver(item.text, []);
  };

  // No run name is known here; a stop without one stops whatever the chat runs.
  const stop = async (): Promise<void> => {
    setStopping(true);
    try {
      await fetch(`${getApiBase()}/chat/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId }),
      });
    } finally {
      setStopping(false);
    }
  };

  return (
    <div className="flex shrink-0 flex-col gap-2 px-2 pb-1 pt-2">
      {queue.length > 0 && (
        <QueuedMessages
          items={queue}
          onSteer={steerQueued}
          onRemove={(id) => onQueueChange((items) => items.filter((item) => item.id !== id))}
          onClear={() => onQueueChange(() => [])}
        />
      )}
      <ChatInputPanel
        input={input}
        setInput={setInput}
        selectedFiles={selectedFiles}
        handleFileSelect={handleFileSelect}
        removeFile={removeFile}
        uploadProgress={uploadProgress}
        isUploading={isUploading}
        fileError={fileError}
        send={() => void send()}
        queue={queueMessage}
        config={config}
        setConfig={setConfig}
        backendConfig={backendConfig}
        fileInputRef={fileInputRef}
        textareaRef={textareaRef}
        configReady={!!backendConfig}
        streamingForCurrentChat={running}
        stopStreaming={() => void stop()}
        stopInFlight={stopping}
        modelSelectDropUp
        modelValue={config.model}
        onModelChange={(model) => setConfig((previous) => ({ ...previous, model }))}
        onPaste={handlePaste}
        onImageClick={onImageClick}
        currentChatId={chatId}
        voice={{ ...voice, handsFree: null }}
      />
    </div>
  );
};
