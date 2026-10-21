import React from 'react';
import { BrutalSelect } from './BrutalSelect';
import { BrutalDialog } from './BrutalDialog';
import {
  ConfigOptions,
  ChatConfig,
  normalizePermissionMode,
  normalizeThinkingEffort,
  type PermissionMode,
  type ThinkingEffort,
} from '../types/api';
import { FileIcon } from './FileIcon';
import {
  PaperClipIcon,
  ArrowUpIcon,
  ArrowUturnRightIcon,
  StopIcon,
  XMarkIcon,
  FolderIcon,
  ChatBubbleLeftRightIcon,
} from '@heroicons/react/24/outline';
import { FolderContextPicker } from './chat/FolderContextPicker';
import { FOCAL_CHAT_ID } from '../lib/focalAgent';
import { useI18n } from '../i18n';
import { useSlashCommands } from '../hooks/useSlashCommands';
import { getApiBase, setChatPermissionMode, setDefaultPermissionMode } from '../lib/api';
import { buildMountedVolumes } from '../lib/volumeMounts';
import { MentionTextArea, type MentionTextAreaHandle } from './chat/MentionTextArea';
import { ghostRemainder } from '../lib/inputSuggestion';
import { ThinkingSlider } from './chat/ThinkingSlider';
import { useAcpAgents } from '../hooks/useAcpAgents';
import { buildEngineOptions, engineValue, parseEngineValue } from '../lib/engineOptions';
import { detectDesktopPlatform } from '../lib/titleBarPlatform';
import {
  MENTION_CATEGORIES,
  groupMentionSuggestions,
  type MentionCategory,
} from '../lib/mentionGroups';
import { isImeComposing } from '../lib/ime';

interface ChatInputPanelProps {
  input: string;
  setInput: React.Dispatch<React.SetStateAction<string>>;
  selectedFiles: File[];
  handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  removeFile: (index: number) => void;
  uploadProgress?: number;
  isUploading?: boolean;
  fileError?: string | null;
  send: () => void;
  /** Cmd/Ctrl+Enter: hold the message until the running turn ends. */
  queue?: () => void;
  config: ChatConfig;
  setConfig: React.Dispatch<React.SetStateAction<ChatConfig>>;
  backendConfig: ConfigOptions | null;
  fileInputRef: React.RefObject<HTMLInputElement>;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  configReady: boolean;
  streamingForCurrentChat: boolean;
  stopStreaming?: () => void; // Optional because only used in footer sometimes
  stopInFlight?: boolean;
  modelSelectDropUp?: boolean;
  modelValue?: string;
  onModelChange?: (model: string) => void;
  onPaste?: (files: File[]) => void;
  onImageClick?: (src: string) => void;
  currentChatId?: string | null;
  onFileMentionSelected?: (mention: FileMentionSelection) => void;
  /** Predicted next message, shown as ghost text the user can accept. */
  inputSuggestion?: string | null;
}

export interface FileMentionSelection {
  name: string;
  path: string;
  type?: 'file' | 'directory';
}

interface FileMentionSuggestion extends Omit<FileMentionSelection, 'type'> {
  type?: 'file' | 'directory' | 'chat';
  root: string;
  size: number;
  mime_type: string;
}

const INPUT_TEXT_METRIC_CLASS =
  'text-lg leading-7 tracking-normal font-sans font-medium [tab-size:4]';
const PERMISSION_MODES: PermissionMode[] = ['default', 'auto', 'full_access'];

/** Shared look for the muted selects under the composer. */
const FOOTER_SELECT_BUTTON_CLASS =
  '!h-6 !w-auto !gap-1.5 !border-0 !bg-transparent dark:!bg-transparent !px-0 !py-0 !font-sans !text-xs !font-medium !normal-case !tracking-normal !text-neutral-600 dark:!text-neutral-400 !shadow-none !translate-x-0 !translate-y-0 hover:!bg-transparent hover:!text-brutal-black dark:hover:!bg-transparent dark:hover:!text-white';

const ImagePreviewThumbnail: React.FC<{
  file: File;
  onImageClick?: (src: string) => void;
}> = ({ file, onImageClick }) => {
  const [previewUrl, setPreviewUrl] = React.useState<string>('');

  React.useEffect(() => {
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);

    // Cleanup URL on unmount or when file changes
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [file]);

  if (!previewUrl) return null;

  return (
    <img
      src={previewUrl}
      alt={file.name}
      className="w-16 h-16 object-cover border-3 border-brutal-black cursor-pointer hover:opacity-80 transition-opacity"
      onClick={() => onImageClick?.(previewUrl)}
    />
  );
};

export const ChatInputPanel: React.FC<ChatInputPanelProps> = ({
  input,
  setInput,
  selectedFiles,
  handleFileSelect,
  removeFile,
  uploadProgress = 0,
  isUploading = false,
  fileError = null,
  send,
  queue,
  config,
  setConfig,
  backendConfig,
  fileInputRef,
  textareaRef,
  configReady,
  streamingForCurrentChat,
  stopStreaming,
  stopInFlight = false,
  modelSelectDropUp = true,
  modelValue,
  onModelChange,
  onPaste,
  onImageClick,
  currentChatId,
  onFileMentionSelected,
  inputSuggestion = null,
}) => {
  const isFocal = currentChatId === FOCAL_CHAT_ID;
  // --- Volume Mounting Logic ---
  const { t } = useI18n();
  const queueKey = React.useMemo(
    () =>
      detectDesktopPlatform(navigator.userAgent, navigator.platform) === 'macos'
        ? '⌘+Enter'
        : 'Ctrl+Enter',
    []
  );
  const [selectedSuggestion, setSelectedSuggestion] = React.useState(0);
  const [mentionSuggestions, setMentionSuggestions] = React.useState<FileMentionSuggestion[]>([]);
  const [mentionCategory, setMentionCategory] = React.useState<MentionCategory>('all');
  const mentionGroups = React.useMemo(
    () => groupMentionSuggestions(mentionSuggestions, mentionCategory),
    [mentionSuggestions, mentionCategory]
  );
  const visibleMentions = React.useMemo(
    () => mentionGroups.flatMap((group) => group.items),
    [mentionGroups]
  );
  const mentionListRef = React.useRef<HTMLDivElement>(null);
  const [selectedMentionSuggestion, setSelectedMentionSuggestion] = React.useState(0);
  // The `@…` query the caret is currently sitting in, or null when there is
  // no active mention search. Driven by the contenteditable editor.
  const [mentionQuery, setMentionQuery] = React.useState<string | null>(null);
  const [isMentionLoading, setIsMentionLoading] = React.useState(false);
  const [isSavingPermissionMode, setIsSavingPermissionMode] = React.useState(false);
  const [pendingPermissionMode, setPendingPermissionMode] = React.useState<PermissionMode | null>(
    null
  );
  const editorRef = React.useRef<MentionTextAreaHandle | null>(null);
  const isComposingRef = React.useRef(false);
  const mentionActive = mentionQuery !== null;
  const suggestions = useSlashCommands(input);
  const ghostOverlayRef = React.useRef<HTMLDivElement | null>(null);
  const [dismissedSuggestion, setDismissedSuggestion] = React.useState<string | null>(null);
  // Every new turn clears the suggestion before predicting again, so an Esc
  // only hides the guess on screen, not the same text on a later turn.
  React.useEffect(() => setDismissedSuggestion(null), [inputSuggestion]);
  const ghost =
    configReady &&
    !streamingForCurrentChat &&
    !mentionActive &&
    suggestions.length === 0 &&
    inputSuggestion !== dismissedSuggestion
      ? ghostRemainder(input, inputSuggestion)
      : null;
  const permissionMode = normalizePermissionMode(config.permission_mode);
  const thinkingEffort = normalizeThinkingEffort(config.thinking);
  const isAcpRuntime = config.runtime === 'acp' || Boolean(config.acp_agent_id);
  const acpAgents = useAcpAgents();

  // The runtime is only choosable while the chat is still new: an ACP chat is
  // bound to a session owned by one agent, and a native chat's history means
  // nothing to an external agent, so neither can be swapped mid-conversation.
  const canChooseRuntime = !currentChatId;

  const engineOptions = React.useMemo(
    () =>
      buildEngineOptions({
        models: backendConfig?.models ?? [],
        agents: acpAgents,
        canChooseRuntime,
        selectedAgentId: config.acp_agent_id,
        labels: {
          models: t('chatInput.engineGroups.models'),
          acp: t('chatInput.engineGroups.acp'),
          notInstalled: t('chatInput.acpNotInstalled'),
          installHint: t('chatInput.acpInstallHint'),
        },
      }),
    [acpAgents, backendConfig, canChooseRuntime, config.acp_agent_id, t]
  );

  const selectedEngine = engineValue({
    isAcpRuntime,
    acpAgentId: config.acp_agent_id,
    model: modelValue ?? config.model,
  });

  const onEngineChange = React.useCallback(
    (next: string) => {
      const selection = parseEngineValue(next);
      if (selection.kind === 'acp') {
        const agent = acpAgents.find((item) => item.id === selection.agentId);
        setConfig((prev) => ({
          ...prev,
          runtime: 'acp',
          acp_agent_id: selection.agentId,
          acp_agent_name: agent?.name || selection.agentId,
          acp_session_id: undefined,
        }));
        return;
      }
      if (isAcpRuntime) {
        setConfig((prev) => ({
          ...prev,
          runtime: 'native',
          acp_agent_id: undefined,
          acp_agent_name: undefined,
          acp_session_id: undefined,
          model: selection.model,
        }));
        return;
      }
      if (onModelChange) onModelChange(selection.model);
      else setConfig((prev) => ({ ...prev, model: selection.model }));
    },
    [acpAgents, isAcpRuntime, onModelChange, setConfig]
  );
  React.useEffect(() => {
    setSelectedSuggestion(0);
  }, [suggestions.length]);
  React.useEffect(() => {
    setSelectedMentionSuggestion(0);
  }, [visibleMentions]);
  React.useEffect(() => {
    if (mentionQuery === null) setMentionCategory('all');
  }, [mentionQuery]);
  React.useEffect(() => {
    mentionListRef.current
      ?.querySelector('[data-selected="true"]')
      ?.scrollIntoView({ block: 'nearest' });
  }, [selectedMentionSuggestion]);

  const applyPermissionMode = React.useCallback(
    async (nextMode: PermissionMode) => {
      if (isSavingPermissionMode || nextMode === permissionMode) return;

      const previous = permissionMode;
      setConfig((prev) => ({ ...prev, permission_mode: nextMode }));

      setIsSavingPermissionMode(true);
      try {
        if (currentChatId) {
          const state = await setChatPermissionMode(currentChatId, nextMode);
          setConfig((prev) => ({ ...prev, permission_mode: state.mode }));
        } else {
          const state = await setDefaultPermissionMode(nextMode);
          setConfig((prev) => ({ ...prev, permission_mode: state.mode }));
        }
      } catch {
        setConfig((prev) => ({ ...prev, permission_mode: previous }));
      } finally {
        setIsSavingPermissionMode(false);
      }
    },
    [currentChatId, isSavingPermissionMode, permissionMode, setConfig]
  );

  const changeThinkingEffort = React.useCallback(
    (next: ThinkingEffort) => {
      if (next === thinkingEffort) return;
      // The chat store persists the chat config and mirrors it into the user
      // preferences, so the choice also becomes the default for new chats.
      setConfig((prev) => ({ ...prev, thinking: next }));
    },
    [setConfig, thinkingEffort]
  );

  const changePermissionMode = React.useCallback(
    (nextMode: PermissionMode) => {
      if (isSavingPermissionMode || nextMode === permissionMode) return;
      if (nextMode === 'auto' || nextMode === 'full_access') {
        setPendingPermissionMode(nextMode);
        return;
      }
      void applyPermissionMode(nextMode);
    },
    [applyPermissionMode, isSavingPermissionMode, permissionMode]
  );

  React.useEffect(() => {
    if (mentionQuery === null) {
      setMentionSuggestions([]);
      setIsMentionLoading(false);
      return;
    }

    setMentionSuggestions([]);
    setIsMentionLoading(true);
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        setIsMentionLoading(true);
        const params = new URLSearchParams({
          chat_id: currentChatId || 'draft',
          query: mentionQuery,
          limit: '30',
        });
        if (config.sandbox_volumes?.length) {
          params.set('volumes', JSON.stringify(config.sandbox_volumes));
        }
        const chatParams = new URLSearchParams({ limit: '30', search: mentionQuery });
        const [files, chats] = await Promise.allSettled([
          mentionQuery
            ? fetch(`${getApiBase()}/sandbox/mentions?${params}`, {
                signal: controller.signal,
              }).then(async (res) => (res.ok ? (await res.json()).items : []))
            : Promise.resolve([]),
          fetch(`${getApiBase()}/chats?${chatParams}`, {
            signal: controller.signal,
          }).then(async (res) => (res.ok ? (await res.json()).chats : [])),
        ]);
        if (controller.signal.aborted) return;
        const chatItems: FileMentionSuggestion[] =
          chats.status === 'fulfilled' && Array.isArray(chats.value)
            ? chats.value
                .filter((chat: { id: string }) => chat.id !== currentChatId)
                .map((chat: { id: string; title?: string }) => ({
                  name: chat.title || chat.id,
                  path: `chat://${encodeURIComponent(chat.id)}/${encodeURIComponent(chat.title || chat.id)}`,
                  type: 'chat',
                  root: '',
                  size: 0,
                  mime_type: '',
                }))
            : [];
        setMentionSuggestions([
          ...chatItems,
          ...(files.status === 'fulfilled' && Array.isArray(files.value) ? files.value : []),
        ]);
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          setMentionSuggestions([]);
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsMentionLoading(false);
        }
      }
    }, 150);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [mentionQuery, currentChatId, config.sandbox_volumes]);

  const insertMention = React.useCallback(
    (suggestion: FileMentionSuggestion) => {
      // The editor deletes the active `@query` and drops in an atomic chip;
      // the serialized string form is `@[<path>]` (no quotes, path visible).
      editorRef.current?.insertMention(suggestion.path, suggestion.name);
      setMentionQuery(null);
      setMentionSuggestions([]);
      if (suggestion.type !== 'chat')
        onFileMentionSelected?.({
          name: suggestion.name,
          path: suggestion.path,
          type: suggestion.type,
        });
    },
    [onFileMentionSelected]
  );

  const dismissMention = React.useCallback(() => {
    setMentionQuery(null);
    setMentionSuggestions([]);
    setIsMentionLoading(false);
  }, []);

  const handleMountFolder = React.useCallback(
    (paths: string[]) => {
      try {
        if (!paths || paths.length === 0) return;

        setConfig((prev) => {
          const currentVolumes = prev.sandbox_volumes || [];
          return { ...prev, sandbox_volumes: buildMountedVolumes(currentVolumes, paths) };
        });
      } catch (err) {
        console.error('Failed to mount folder', err);
      }
    },
    [setConfig]
  );

  const removeVolume = (index: number) => {
    setConfig((prev) => {
      const current = prev.sandbox_volumes || [];
      return {
        ...prev,
        sandbox_volumes: current.filter((_, i) => i !== index),
      };
    });
  };

  return (
    <div className="chat-composer min-w-0 flex flex-col gap-1">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-brutal-sm p-1.5 flex flex-col gap-1 relative group transition-colors duration-200 z-20 text-left"
      >
        {/* Unified file preview section. Capped height + scroll so a large
                batch of attachments never inflates the input box; images wrap into
                a compact grid, files stack as cards. */}
        {selectedFiles.length > 0 && (
          <div className="flex flex-col gap-2 p-2 mb-1 max-h-44 overflow-y-auto">
            {/* Images — compact wrapping grid */}
            {selectedFiles.some((f) => f.type.startsWith('image/')) && (
              <div className="flex flex-wrap gap-2">
                {selectedFiles.map(
                  (file, idx) =>
                    file.type.startsWith('image/') && (
                      <div key={idx} className="relative group/image shrink-0">
                        <ImagePreviewThumbnail file={file} onImageClick={onImageClick} />
                        <button
                          type="button"
                          onClick={() => removeFile(idx)}
                          className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-brutal-red border-2 border-brutal-black text-white text-xs flex items-center justify-center font-bold shadow-brutal-sm hover:shadow-none transition-all opacity-0 group-hover/image:opacity-100"
                          title={t('chatInput.removeFile')}
                        >
                          ×
                        </button>
                      </div>
                    )
                )}
              </div>
            )}

            {/* Non-image files — stacked cards */}
            {selectedFiles.map(
              (file, idx) =>
                !file.type.startsWith('image/') && (
                  <div
                    key={idx}
                    className="flex items-center gap-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black p-2"
                  >
                    <FileIcon mimeType={file.type} className="w-5 h-5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold text-brutal-black dark:text-white truncate">
                        {file.name}
                      </div>
                      <div className="text-xs text-neutral-500 dark:text-neutral-400">
                        {(file.size / 1024).toFixed(1)} KB
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeFile(idx)}
                      className="shrink-0 w-6 h-6 bg-brutal-red border-2 border-brutal-black text-white flex items-center justify-center hover:bg-red-600 transition-colors"
                      title={t('chatInput.removeFile')}
                    >
                      <XMarkIcon className="w-4 h-4" />
                    </button>
                  </div>
                )
            )}
          </div>
        )}

        {/* Upload progress bar */}
        {isUploading && (
          <div className="p-2">
            <div className="w-full bg-neutral-200 border-2 border-brutal-black h-6 overflow-hidden">
              <div
                className="h-full bg-brutal-blue transition-all duration-300 flex items-center justify-center"
                style={{ width: `${uploadProgress}%` }}
              >
                <span className="text-xs font-bold text-white">{uploadProgress.toFixed(0)}%</span>
              </div>
            </div>
          </div>
        )}

        {/* Error message */}
        {fileError && (
          <div className="p-2">
            <div className="bg-brutal-red border-2 border-brutal-black p-2 text-white text-sm font-bold">
              {fileError}
            </div>
          </div>
        )}

        {/* Slash command suggestions */}
        {suggestions.length > 0 && (
          <div className="absolute left-2 right-2 bottom-[calc(100%-0.5rem)] border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm overflow-hidden z-30">
            {suggestions.map((cmd, i) => {
              const showHeader = i === 0 || suggestions[i - 1].category !== cmd.category;
              return (
                <React.Fragment key={cmd.name}>
                  {showHeader && (
                    <div className="px-3 py-1 bg-neutral-200 dark:bg-zinc-900 border-y border-neutral-300 dark:border-zinc-700 text-xs font-bold text-neutral-500 uppercase tracking-wider first:border-t-0">
                      {cmd.category || 'Commands'}
                    </div>
                  )}
                  <div
                    className={`flex items-baseline gap-3 px-3 py-2 text-sm ${!input.includes(' ') || cmd.isOption ? 'cursor-pointer ' : ''}${i === selectedSuggestion && (!input.includes(' ') || cmd.isOption) ? 'bg-brutal-yellow dark:bg-yellow-600 text-brutal-black' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'}`}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      if (!input.includes(' ') || cmd.isOption) {
                        const textToInsert =
                          cmd.isOption && cmd.parentCmd
                            ? `${cmd.parentCmd} ${cmd.aliases[0]} `
                            : `${cmd.aliases?.[0] || cmd.usage} `;
                        setInput(textToInsert);
                      }
                    }}
                  >
                    <span className="font-bold font-mono shrink-0">{cmd.aliases[0]}</span>
                    <span className="text-neutral-500 dark:text-neutral-400 truncate">
                      {cmd.description}
                    </span>
                    <span className="ml-auto font-mono text-xs text-neutral-400 dark:text-neutral-500 shrink-0">
                      {cmd.usage}
                    </span>
                  </div>
                </React.Fragment>
              );
            })}
          </div>
        )}

        {mentionActive && (
          <div
            ref={mentionListRef}
            className="absolute -left-px -right-px bottom-[calc(100%+0.5rem)] border-2 border-brutal-black dark:border-zinc-500 bg-white dark:bg-zinc-800 overflow-hidden max-h-60 overflow-y-auto z-40 font-normal"
          >
            <div className="sticky top-0 z-10 flex gap-1 px-2 py-1.5 bg-white dark:bg-zinc-800 border-b-2 border-neutral-200 dark:border-zinc-600">
              {MENTION_CATEGORIES.map((category) => (
                <button
                  key={category}
                  type="button"
                  aria-pressed={mentionCategory === category}
                  className={`px-2 py-0.5 text-xs font-bold border focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue ${mentionCategory === category ? 'border-brutal-black bg-brutal-yellow text-brutal-black' : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-zinc-700'}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => setMentionCategory(category)}
                >
                  {t(`chatInput.mentionCategory_${category}`)}
                </button>
              ))}
            </div>
            {visibleMentions.length > 0 ? (
              visibleMentions.map((suggestion, i) => (
                <React.Fragment key={suggestion.path}>
                  {(i === 0 || visibleMentions[i - 1].type !== suggestion.type) && (
                    <div className="px-3 pt-2 pb-1 text-[11px] font-bold text-neutral-500 dark:text-neutral-400">
                      {t(`chatInput.mentionCategory_${suggestion.type || 'file'}`)}
                    </div>
                  )}
                  <div
                    data-selected={i === selectedMentionSuggestion}
                    onMouseEnter={() => setSelectedMentionSuggestion(i)}
                    className={`flex items-center gap-2 border-l-[3px] pl-[9px] pr-3 py-2 text-sm leading-5 cursor-pointer ${i === selectedMentionSuggestion ? 'border-brutal-black dark:border-brutal-yellow bg-brutal-yellow/15 dark:bg-brutal-yellow/10 text-neutral-900 dark:text-neutral-100' : 'border-transparent hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'}`}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      insertMention(suggestion);
                    }}
                  >
                    <div className="w-4 h-4 shrink-0 flex items-center justify-center text-neutral-600 dark:text-neutral-300">
                      {suggestion.type === 'chat' ? (
                        <ChatBubbleLeftRightIcon className="w-4 h-4 stroke-[1.5]" />
                      ) : suggestion.type === 'directory' ? (
                        <FolderIcon className="w-4 h-4 stroke-[1.5]" />
                      ) : (
                        <FileIcon
                          mimeType={suggestion.mime_type || 'application/octet-stream'}
                          className="w-4 h-4 stroke-[1.5]"
                        />
                      )}
                    </div>
                    <div
                      className="min-w-0 flex-1 flex items-baseline gap-3"
                      title={suggestion.name}
                    >
                      <div className="min-w-0 flex-1 font-medium truncate">{suggestion.name}</div>
                      {suggestion.type !== 'chat' && (
                        <div
                          className="max-w-[45%] truncate text-[11px] text-neutral-400 dark:text-neutral-500"
                          title={suggestion.path}
                        >
                          {suggestion.path}
                        </div>
                      )}
                    </div>
                  </div>
                </React.Fragment>
              ))
            ) : (
              <div className="px-3 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                {(mentionQuery?.length ?? 0) < 1
                  ? t('chatInput.fileMentionTypeToSearch')
                  : isMentionLoading
                    ? t('chatInput.fileMentionSearching')
                    : t('chatInput.fileMentionNoResults')}
              </div>
            )}
          </div>
        )}

        <div className="relative">
          {!input && !ghost && configReady && streamingForCurrentChat && (
            <div
              className={
                'pointer-events-none absolute inset-0 px-2 py-1.5 text-neutral-400 dark:text-neutral-500 ' +
                INPUT_TEXT_METRIC_CLASS
              }
            >
              {t('chatInput.placeholderRedirect', { queueKey })
                .split(/(Ctrl\+Enter|⌘\+Enter|Enter)/)
                .map((part, index) =>
                  part.endsWith('Enter') ? (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1 align-baseline whitespace-nowrap"
                    >
                      {part !== 'Enter' && (
                        <>
                          <kbd className="inline-flex h-6 items-center rounded-[2px] border border-neutral-300 dark:border-zinc-600 px-1.5 font-sans text-sm font-medium leading-none">
                            {part.slice(0, -6)}
                          </kbd>
                          <span className="text-sm">+</span>
                        </>
                      )}
                      <kbd
                        aria-label="Enter"
                        className="inline-flex h-6 min-w-6 items-center justify-center rounded-[2px] border border-neutral-300 dark:border-zinc-600 px-1 font-sans text-base font-medium leading-none"
                      >
                        <span aria-hidden="true">↵</span>
                      </kbd>
                    </span>
                  ) : (
                    <React.Fragment key={index}>{part}</React.Fragment>
                  )
                )}
            </div>
          )}
          {ghost && (
            <div
              ref={ghostOverlayRef}
              aria-hidden="true"
              className={`pointer-events-none absolute inset-0 overflow-hidden px-2 py-1.5 whitespace-pre-wrap break-words text-left ${INPUT_TEXT_METRIC_CLASS}`}
            >
              <span className="invisible">{input}</span>
              <span className="text-neutral-400 dark:text-neutral-500">{ghost}</span>
              <kbd className="ml-2 inline-flex h-6 items-center align-baseline rounded-[2px] border border-neutral-300 dark:border-zinc-600 px-1.5 font-sans text-sm font-medium leading-none text-neutral-400 dark:text-neutral-500">
                {t('chatInput.suggestionAcceptKey')}
              </kbd>
            </div>
          )}
          <MentionTextArea
            ref={editorRef}
            value={input}
            onChange={setInput}
            onQueryChange={setMentionQuery}
            onScroll={(e) => {
              if (ghostOverlayRef.current) {
                ghostOverlayRef.current.scrollTop = e.currentTarget.scrollTop;
              }
            }}
            disabled={!configReady}
            className={`mention-editor block w-full overflow-y-auto min-h-[40px] max-h-[120px] bg-transparent focus:outline-none caret-brutal-black dark:caret-white border-none px-2 py-1.5 whitespace-pre-wrap break-words selection:bg-brutal-blue/30 text-left text-brutal-black dark:text-white ${INPUT_TEXT_METRIC_CLASS}`}
            placeholder={
              ghost
                ? ''
                : !configReady
                  ? t('chatInput.placeholderLoading').toUpperCase()
                  : streamingForCurrentChat
                    ? ''
                    : t('chatInput.placeholderReady')
            }
            onCompositionStart={() => {
              isComposingRef.current = true;
            }}
            onCompositionEnd={() => {
              window.setTimeout(() => {
                isComposingRef.current = false;
              }, 0);
            }}
            onKeyDown={(e) => {
              // Every key the IME consumes — Enter to commit, arrows and Escape
              // in its candidate list — belongs to it, not to send or suggestions.
              if (isComposingRef.current || isImeComposing(e)) return;

              // Ahead of mention and slash-command handling, which treat any
              // Enter as accept-and-send and would redirect the running turn.
              if (e.key === 'Enter' && queue && (e.metaKey || e.ctrlKey) && !e.shiftKey) {
                e.preventDefault();
                if (configReady && input.trim()) queue();
                return;
              }

              if (mentionActive && visibleMentions.length > 0) {
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setSelectedMentionSuggestion((i) => Math.max(0, i - 1));
                  return;
                }
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setSelectedMentionSuggestion((i) => Math.min(visibleMentions.length - 1, i + 1));
                  return;
                }
                if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                  e.preventDefault();
                  insertMention(visibleMentions[selectedMentionSuggestion]);
                  return;
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  dismissMention();
                  return;
                }
              }
              if (mentionActive && visibleMentions.length === 0) {
                if (e.key === 'Escape') {
                  e.preventDefault();
                  dismissMention();
                  return;
                }
                if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey && input.trim() === '@')) {
                  e.preventDefault();
                  return;
                }
              }

              const hasSpace = input.includes(' ');
              const activeCmd = suggestions[selectedSuggestion];
              const isOptionMode = hasSpace && activeCmd?.isOption;

              if (suggestions.length > 0 && (!hasSpace || isOptionMode)) {
                // Intercept navigation and autocomplete ONLY if typing the command word OR navigating mapped options
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setSelectedSuggestion((i) => Math.max(0, i - 1));
                  return;
                }
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setSelectedSuggestion((i) => Math.min(suggestions.length - 1, i + 1));
                  return;
                }
                if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                  e.preventDefault();
                  if (activeCmd) {
                    const textToInsert =
                      activeCmd.isOption && activeCmd.parentCmd
                        ? `${activeCmd.parentCmd} ${activeCmd.aliases[0]} `
                        : `${activeCmd.aliases?.[0] || activeCmd.usage} `;

                    // If the user completely typed out the command (e.g. "/node list")
                    // pressing Enter should send it rather than just expanding the trailing space.
                    if (e.key === 'Enter' && input.trim() === textToInsert.trim()) {
                      if (configReady && input.trim()) {
                        send();
                      }
                    } else {
                      setInput(textToInsert);
                    }
                  }
                  return;
                }
                if (e.key === 'Escape') {
                  setInput('');
                  return;
                }
              } else if (suggestions.length > 0 && hasSpace && !isOptionMode) {
                // Passive hint mode: Escape clears, but Enter/Tab/Arrows act normally
                if (e.key === 'Escape') {
                  setInput('');
                  return;
                }
              }

              if (ghost) {
                const noModifiers = !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey;
                if (
                  noModifiers &&
                  (e.key === 'Tab' || (e.key === 'ArrowRight' && editorRef.current?.isCaretAtEnd()))
                ) {
                  e.preventDefault();
                  editorRef.current?.appendText(ghost);
                  return;
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  setDismissedSuggestion(inputSuggestion);
                  return;
                }
              }

              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (configReady && input.trim()) {
                  send();
                }
              }
            }}
            onPaste={(e) => {
              if (onPaste && e.clipboardData) {
                // Method 1: Get files directly (works for all file types pasted)
                const files = Array.from(e.clipboardData.files || []);

                // Method 2: Fallback to items for screenshot/image data
                if (files.length === 0) {
                  const items = Array.from(e.clipboardData.items);
                  items.forEach((item) => {
                    if (item.kind === 'file') {
                      const file = item.getAsFile();
                      if (file) {
                        files.push(file);
                      }
                    }
                  });
                }

                if (files.length > 0) {
                  e.preventDefault();
                  onPaste(files);
                }
              }
            }}
          />
        </div>

        {/* Button row */}
        <div className="chat-composer-toolbar flex flex-wrap items-center gap-2 px-1 pb-0.5">
          {/* Left: folder + attachment. The Focal Agent works through project
              sessions, which carry their own folders. */}
          {!isFocal && (
            <FolderContextPicker
              onMount={handleMountFolder}
              activeVolumes={config.sandbox_volumes || []}
              onRemoveVolume={removeVolume}
              disabled={!configReady || streamingForCurrentChat || isUploading}
              dropUp={modelSelectDropUp}
            />
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="*"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-9 h-9 flex items-center justify-center bg-transparent text-brutal-black dark:text-white hover:bg-neutral-200 dark:hover:bg-zinc-700 hover:text-brutal-blue transition-colors disabled:opacity-40 shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
            title={t('chatInput.attachFiles')}
            disabled={!configReady || streamingForCurrentChat || isUploading}
          >
            <PaperClipIcon className="w-5 h-5" />
          </button>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Right: model picker (shrinks) + action button (fixed) */}
          {configReady && (
            <div
              className="chat-composer-model relative min-w-0 shrink"
              title={isAcpRuntime && !canChooseRuntime ? t('chatWindow.acpAgentLocked') : undefined}
            >
              <BrutalSelect
                value={selectedEngine}
                onChange={onEngineChange}
                options={engineOptions}
                disabled={isAcpRuntime && !canChooseRuntime}
                placeholder={t('chatInput.modelPlaceholder').toUpperCase()}
                dropUp={modelSelectDropUp}
                className="h-9 text-sm max-w-[220px]"
                buttonClassName="!h-9 !gap-1.5 !font-bold [&>svg]:!w-3.5 [&>svg]:!h-3.5 [&>svg]:shrink-0 [&>svg]:stroke-2 [&>svg]:text-neutral-400 dark:[&>svg]:text-neutral-500 !border-0 !bg-transparent dark:!bg-transparent !px-2 !py-1.5 !shadow-none !translate-x-0 !translate-y-0 hover:!bg-neutral-200 dark:hover:!bg-zinc-600 focus-visible:!ring-2 focus-visible:!ring-brutal-blue"
                dropdownClassName="min-w-[240px] right-0"
              />
            </div>
          )}

          {/* Redirect button (shown when streaming and user has typed) */}
          {stopStreaming && streamingForCurrentChat && input.trim() ? (
            <button
              type="submit"
              className="w-9 h-9 inline-flex items-center justify-center border-2 border-brutal-black duration-100 p-0 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed uppercase shrink-0 bg-brutal-yellow hover:bg-yellow-300 text-brutal-black focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
              disabled={!configReady}
              title={t('chatInput.redirectAgent')}
              aria-label={t('chatInput.redirectAgent')}
            >
              <ArrowUturnRightIcon className="w-5 h-5 stroke-[2.5]" aria-hidden="true" />
            </button>
          ) : stopStreaming && streamingForCurrentChat ? (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                stopStreaming();
              }}
              className="w-9 h-9 inline-flex items-center justify-center border-2 border-brutal-black duration-100 p-0 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase shrink-0 bg-brutal-red hover:bg-red-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
              disabled={stopInFlight}
              title={stopInFlight ? t('chatInput.stopping') : t('chatInput.stopGenerating')}
              aria-label={stopInFlight ? t('chatInput.stopping') : t('chatInput.stopGenerating')}
              aria-busy={stopInFlight}
            >
              <StopIcon className="w-5 h-5 fill-current" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="submit"
              className="w-9 h-9 inline-flex items-center justify-center border-2 border-brutal-black duration-100 p-0 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase shrink-0 bg-brutal-blue hover:bg-blue-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brutal-blue"
              disabled={streamingForCurrentChat || !configReady}
              title={t('chatInput.sendMessage')}
              aria-label={t('chatInput.sendMessage')}
            >
              <ArrowUpIcon className="w-5 h-5 stroke-[2.5]" aria-hidden="true" />
            </button>
          )}
        </div>
      </form>

      <div
        className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-3 pt-0.5 ${isFocal ? 'justify-end' : 'justify-between'}`}
      >
        {!isFocal && (
          <div title={t(`chatWindow.permissionModeDescriptions.${permissionMode}`)}>
            <BrutalSelect
              value={permissionMode}
              onChange={(value) => changePermissionMode(value as PermissionMode)}
              options={PERMISSION_MODES.map((option) => ({
                value: option,
                label: t(`chatWindow.permissionModeInputLabels.${option}`),
              }))}
              dropUp={true}
              hideChevron={true}
              disabled={!configReady || streamingForCurrentChat || isSavingPermissionMode}
              className="inline-block w-auto"
              buttonClassName={FOOTER_SELECT_BUTTON_CLASS}
              dropdownClassName="min-w-[220px] font-mono text-[10px]"
            />
          </div>
        )}

        {/* Reasoning effort. Only the native runtime owns model settings — an
            ACP agent picks its own. Models that cannot think ignore the setting,
            so it stays selectable rather than guessing which model reasons. */}
        {!isAcpRuntime && (
          <ThinkingSlider
            value={thinkingEffort}
            onChange={changeThinkingEffort}
            disabled={!configReady || streamingForCurrentChat}
          />
        )}
      </div>

      <BrutalDialog
        open={pendingPermissionMode !== null}
        title={
          pendingPermissionMode === 'full_access'
            ? t('chatWindow.fullAccessModeDialogTitle')
            : t('chatWindow.autoModeDialogTitle')
        }
        message={
          pendingPermissionMode === 'full_access'
            ? t('chatWindow.fullAccessModeConfirmation')
            : t('chatWindow.autoModeConfirmation')
        }
        onClose={() => setPendingPermissionMode(null)}
        actions={[
          {
            label: t('chatWindow.autoModeCancel'),
            tone: 'default',
          },
          {
            label:
              pendingPermissionMode === 'full_access'
                ? t('chatWindow.fullAccessModeEnable')
                : t('chatWindow.autoModeEnable'),
            tone: 'primary',
            onClick: () => {
              if (pendingPermissionMode) {
                void applyPermissionMode(pendingPermissionMode);
              }
            },
          },
        ]}
      />
    </div>
  );
};
