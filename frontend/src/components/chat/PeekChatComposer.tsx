import React, { useRef, useState } from 'react';
import { ChatInputPanel } from '../ChatInputPanel';
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
}

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
}) => {
  const [input, setInput] = useState('');
  const [config, setConfig] = useState<ChatConfig>(() => seedConfig(savedConfig, backendConfig));
  const [stopping, setStopping] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    selectedFiles,
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

  const send = async (): Promise<void> => {
    const text = input.trim();
    if (!text && selectedFiles.length === 0) return;
    let files: FileAttachment[] | undefined;
    if (selectedFiles.length > 0) {
      try {
        files = (await uploadFiles([...selectedFiles], chatId)).fileMetadata;
      } catch {
        return;
      }
    }
    if (await onSend(text, config, files)) {
      setInput('');
      clearFiles();
    }
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
    <div className="shrink-0 px-2 pb-1 pt-2">
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
