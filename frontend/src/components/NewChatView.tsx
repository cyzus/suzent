import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChatInputPanel, type FileMentionSelection } from './ChatInputPanel';
import { ConfigOptions, ChatConfig, type DiscoveredExternalSession } from '../types/api';
import { GreetingCube } from './chat/GreetingCube';
import { useI18n } from '../i18n';
import { useProjects } from '../hooks/useProjects';
import { resolveProjectMenuPosition, type ProjectMenuGeometry } from '../lib/projectMenuPosition';
import { isImeComposing } from '../lib/ime';
import type { VoiceSession } from '../hooks/useVoiceSession';
import { AcpAgentIcon } from './AcpAgentIcon';
import { formatAcpAgentName } from './chat/AssistantMessage';
import { adoptAcpSession, discoverAcpSessions } from '../lib/api';

interface NewChatViewProps {
  input: string;
  setInput: React.Dispatch<React.SetStateAction<string>>;
  selectedFiles: File[];
  handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  removeFile: (index: number) => void;
  uploadProgress?: number;
  isUploading?: boolean;
  fileError?: string | null;
  send: () => void;
  config: ChatConfig;
  setConfig: React.Dispatch<React.SetStateAction<ChatConfig>>;
  backendConfig: ConfigOptions | null;
  fileInputRef: React.RefObject<HTMLInputElement>;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  configReady: boolean;
  streamingForCurrentChat: boolean;
  onPaste?: (files: File[]) => void;
  onImageClick?: (src: string) => void;
  currentChatId?: string | null;
  onFileMentionSelected?: (mention: FileMentionSelection) => void;
  onAdoptSession?: (chatId: string) => Promise<void> | void;
  voice: VoiceSession;
  /** Replaces the greeting and project picker, for chats that already have a home. */
  briefing?: React.ReactNode;
}

const GreetingPresence: React.FC<{ engaged: boolean; hideCube?: boolean }> = React.memo(
  ({ engaged, hideCube = false }) => {
    const { t } = useI18n();

    const getGreeting = () => {
      const hour = new Date().getHours();
      if (hour < 5) return t('newChat.greetings.nightOwl').toUpperCase();
      if (hour < 12) return t('newChat.greetings.goodMorning').toUpperCase();
      if (hour < 17) return t('newChat.greetings.keepBuilding').toUpperCase();
      if (hour < 21) return t('newChat.greetings.goodEvening').toUpperCase();
      return t('newChat.greetings.bedTime').toUpperCase();
    };

    return (
      <div className="new-chat-greeting mb-6 flex flex-col items-center gap-5">
        {!hideCube && <GreetingCube engaged={engaged} />}
        <h2 className="new-chat-title text-4xl sm:text-5xl font-brutal font-bold text-brutal-black dark:text-white mb-2 tracking-tight">
          {getGreeting()}
        </h2>
      </div>
    );
  }
);

GreetingPresence.displayName = 'GreetingPresence';

// Inline project picker shown above the chat input on the new-chat screen.
// Changes which project the next created chat will be assigned to.
const ProjectPicker: React.FC = () => {
  const { t } = useI18n();
  const { projects, currentProjectId, setCurrentProjectId, createProject } = useProjects();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [geometry, setGeometry] = useState<ProjectMenuGeometry | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const hasFocusedRef = useRef(false);

  const updatePosition = useCallback(() => {
    const button = buttonRef.current;
    if (!button) return;
    setGeometry(
      resolveProjectMenuPosition(button.getBoundingClientRect(), {
        width: window.innerWidth,
        height: window.innerHeight,
      })
    );
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();

    window.addEventListener('resize', updatePosition);
    // Capture, so scrolling any ancestor keeps the menu pinned to the button.
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [open, updatePosition]);

  // The portal is appended after #root, so Tab from the trigger would walk the
  // whole app before reaching the options. Move focus in explicitly once the
  // menu has been placed, starting on the current project.
  useEffect(() => {
    if (!open) {
      hasFocusedRef.current = false;
      return;
    }
    if (hasFocusedRef.current) return;
    const menu = menuRef.current;
    if (!menu) return;

    const target =
      menu.querySelector<HTMLElement>('[data-current]') ??
      menu.querySelector<HTMLElement>('button, input');
    target?.focus();
    hasFocusedRef.current = true;
  }, [open, geometry]);

  // The menu is portalled out of the button's subtree, so closing it needs
  // explicit outside-click and Escape handling.
  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (buttonRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
      setCreating(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (isImeComposing(event)) return;
      if (event.key !== 'Escape') return;
      setOpen(false);
      setCreating(false);
      buttonRef.current?.focus();
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const current = projects.find((p) => p.id === currentProjectId) || projects[0];
  if (!current) return null;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    const project = await createProject(name);
    if (project) setCurrentProjectId(project.id);
    setNewName('');
    setCreating(false);
    setOpen(false);
  };

  const menu =
    open &&
    geometry &&
    createPortal(
      <div
        ref={menuRef}
        role="dialog"
        aria-label={t('newChat.creatingIn')}
        className="fixed z-[9999] flex flex-col bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-brutal-overlay"
        style={{
          // A drop-up menu hangs from its bottom edge so a short list stays
          // tucked against the trigger instead of floating above it.
          ...(geometry.dropUp ? { bottom: geometry.bottom } : { top: geometry.top }),
          left: geometry.left,
          width: geometry.width,
          maxHeight: geometry.maxHeight,
        }}
      >
        <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                setCurrentProjectId(p.id);
                setOpen(false);
              }}
              data-current={p.id === currentProjectId || undefined}
              className={`w-full text-left px-3 py-2 text-xs font-bold hover:bg-neutral-100 dark:hover:bg-zinc-700 flex items-center justify-between gap-2 ${p.id === currentProjectId ? 'bg-brutal-yellow text-brutal-black' : 'dark:text-white'}`}
            >
              <span className="truncate">{p.name}</span>
              {p.id === currentProjectId && (
                <span className="text-[9px] uppercase opacity-70">●</span>
              )}
            </button>
          ))}
        </div>
        <div className="shrink-0 border-t-2 border-brutal-black">
          {creating ? (
            <form onSubmit={handleCreate} className="flex items-center gap-1 p-2">
              <input
                autoFocus
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (isImeComposing(e)) return;
                  if (e.key === 'Escape') setCreating(false);
                }}
                placeholder={t('chatList.newProjectPlaceholder')}
                className="flex-1 min-w-0 px-2 py-1 text-xs font-bold bg-white dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
              />
              <button
                type="submit"
                className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-brutal-yellow hover:brightness-95 text-brutal-black shrink-0"
              >
                ✓
              </button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="w-full text-left px-3 py-2 text-xs font-extrabold uppercase tracking-wider hover:bg-brutal-yellow hover:text-brutal-black dark:text-white"
            >
              + {t('chatList.newProject')}
            </button>
          )}
        </div>
      </div>,
      document.body
    );

  return (
    <div className="relative mb-3 flex justify-center">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="inline-flex max-w-full items-center gap-2 px-3 py-1.5 text-xs font-extrabold uppercase tracking-wider border-2 border-brutal-black bg-white dark:bg-zinc-800 dark:text-white hover:bg-brutal-yellow brutal-btn"
      >
        <svg
          className="w-3 h-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 7l9-4 9 4M3 7v10l9 4 9-4V7" />
        </svg>
        <span className="shrink-0 opacity-60">{t('newChat.creatingIn')}</span>
        <span className="min-w-0 truncate" title={current.name}>
          {current.name}
        </span>
        <svg
          className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          strokeWidth={3}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {menu}
    </div>
  );
};

// ... (other imports)

import { formatRelativeTime as formatLocalizedRelativeTime } from '../lib/chatUtils';

function formatRelativeTime(isoOrMtime: string | number | undefined, locale: string): string {
  if (!isoOrMtime) return '';
  const iso =
    typeof isoOrMtime === 'number' ? new Date(isoOrMtime * 1000).toISOString() : isoOrMtime;
  return formatLocalizedRelativeTime(iso, locale);
}

const ExternalSessionDiscoveryTray: React.FC<{
  agentId: string;
  cwd?: string;
  currentChatId?: string | null;
  onAdopted?: (chatId: string) => Promise<void> | void;
}> = ({ agentId, cwd, currentChatId, onAdopted }) => {
  const { t, locale } = useI18n();
  const { currentProjectId } = useProjects();
  const [sessions, setSessions] = useState<DiscoveredExternalSession[]>([]);
  const [adoptingId, setAdoptingId] = useState<string | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualId, setManualId] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    discoverAcpSessions({
      agentId,
      cwd,
      chatId: currentChatId,
      projectId: currentProjectId,
    })
      .then((res) => {
        if (!cancelled) setSessions(res.sessions.slice(0, 5));
      })
      .catch(() => {
        if (!cancelled) setSessions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, cwd, currentChatId, currentProjectId]);

  const handleAdopt = useCallback(
    async (sessionId: string, title?: string, updatedAt?: string, mtime?: number) => {
      const trimmed = sessionId.trim();
      if (!trimmed || adoptingId) return;
      setAdoptingId(trimmed);
      setError(null);
      try {
        const res = await adoptAcpSession({
          agentId,
          sessionId: trimmed,
          chatId: currentChatId,
          projectId: currentProjectId,
          cwd,
          title,
          updatedAt,
          mtime,
        });
        setManualOpen(false);
        setManualId('');
        await onAdopted?.(res.chat_id);
      } catch (err) {
        setError((err as Error).message || t('newChat.acp.resumeFailed'));
      } finally {
        setAdoptingId(null);
      }
    },
    [adoptingId, agentId, currentChatId, currentProjectId, cwd, onAdopted, t]
  );

  const agentName = formatAcpAgentName(agentId);

  return (
    <div className="mt-4 w-full text-left border-2 border-brutal-black dark:border-zinc-700 bg-white dark:bg-zinc-800/90 shadow-brutal-sm dark:shadow-none">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-neutral-200 dark:border-zinc-700 bg-neutral-50 dark:bg-zinc-900/60">
        <div className="flex items-center gap-2 min-w-0">
          <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center text-brutal-black dark:text-neutral-100">
            <AcpAgentIcon id={agentId} className="w-3.5 h-3.5 shrink-0" />
          </span>
          <span className="text-[11px] font-bold uppercase tracking-wider text-neutral-600 dark:text-neutral-300 truncate">
            {t('newChat.acp.discoveredTitle', { agent: agentName })}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setManualOpen((prev) => !prev)}
          className="shrink-0 text-[11px] font-mono font-bold text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white underline underline-offset-2"
        >
          {manualOpen ? t('newChat.acp.cancel') : t('newChat.acp.manualAction')}
        </button>
      </div>

      {manualOpen && (
        <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-200 dark:border-zinc-700 bg-neutral-50/50 dark:bg-zinc-900/30">
          <input
            type="text"
            value={manualId}
            onChange={(e) => setManualId(e.target.value)}
            onKeyDown={(e) => {
              if (isImeComposing(e)) return;
              if (e.key === 'Enter') {
                e.preventDefault();
                void handleAdopt(manualId);
              }
            }}
            placeholder={t('newChat.acp.manualPlaceholder')}
            className="flex-1 min-w-0 px-2 py-1 text-xs font-mono border border-brutal-black dark:border-zinc-600 bg-white dark:bg-zinc-800 text-brutal-black dark:text-white focus:outline-none"
          />
          <button
            type="button"
            disabled={!manualId.trim() || Boolean(adoptingId)}
            onClick={() => void handleAdopt(manualId)}
            className="px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-wider border border-brutal-black bg-brutal-yellow text-brutal-black disabled:opacity-50"
          >
            {adoptingId === manualId.trim()
              ? t('newChat.acp.adopting')
              : t('newChat.acp.manualSubmit')}
          </button>
        </div>
      )}

      {error && (
        <div className="px-3 py-1.5 text-xs font-mono text-red-600 dark:text-red-400 border-b border-neutral-200 dark:border-zinc-700">
          {error}
        </div>
      )}

      {sessions.length > 0 && (
        <div className="divide-y divide-neutral-100 dark:divide-zinc-700/60">
          {sessions.map((item) => {
            const busy = adoptingId === item.session_id;
            const rel = formatRelativeTime(item.updated_at || item.mtime, locale);
            return (
              <div
                key={item.session_id}
                className="flex items-center justify-between gap-3 px-3 py-2 hover:bg-neutral-50 dark:hover:bg-zinc-700/40 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-brutal-black dark:text-neutral-100 truncate">
                    {item.title}
                  </div>
                  <div className="flex items-center gap-2 text-[10px] font-mono text-neutral-400 dark:text-neutral-500">
                    <span>{item.session_id.slice(0, 8)}</span>
                    {rel && <span>· {rel}</span>}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={Boolean(adoptingId)}
                  onClick={() =>
                    void handleAdopt(item.session_id, item.title, item.updated_at, item.mtime)
                  }
                  className="shrink-0 px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-wider border border-brutal-black dark:border-zinc-500 bg-white dark:bg-zinc-800 text-brutal-black dark:text-neutral-100 hover:bg-brutal-yellow dark:hover:bg-zinc-700 disabled:opacity-50 transition-colors"
                >
                  {busy ? t('newChat.acp.adopting') : t('newChat.acp.adoptAction')}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export const NewChatView: React.FC<NewChatViewProps> = ({
  input,
  setInput,
  selectedFiles,
  handleFileSelect,
  removeFile,
  uploadProgress,
  isUploading,
  fileError,
  send,
  config,
  setConfig,
  backendConfig,
  fileInputRef,
  textareaRef,
  configReady,
  streamingForCurrentChat,
  onPaste,
  onImageClick,
  currentChatId,
  onFileMentionSelected,
  onAdoptSession,
  voice,
  briefing,
}) => {
  const [isInputHovered, setIsInputHovered] = useState(false);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const isInputEngaged = isInputHovered || isInputFocused;
  const activeAcpAgentId =
    config.runtime === 'acp' && config.acp_agent_id ? config.acp_agent_id : null;
  return (
    <div className="new-chat-view flex flex-col items-center justify-center min-h-full text-center animate-brutal-drop">
      {briefing ?? <GreetingPresence engaged={isInputEngaged} hideCube={voice.status !== 'idle'} />}

      <div className="w-full max-w-2xl">
        {!briefing && <ProjectPicker />}
        <div
          onPointerEnter={() => setIsInputHovered(true)}
          onPointerLeave={() => setIsInputHovered(false)}
          onFocusCapture={() => setIsInputFocused(true)}
          onBlurCapture={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setIsInputFocused(false);
            }
          }}
        >
          <ChatInputPanel
            input={input}
            setInput={setInput}
            selectedFiles={selectedFiles}
            handleFileSelect={handleFileSelect}
            removeFile={removeFile}
            uploadProgress={uploadProgress}
            isUploading={isUploading}
            fileError={fileError}
            send={send}
            config={config}
            setConfig={setConfig}
            backendConfig={backendConfig}
            fileInputRef={fileInputRef}
            textareaRef={textareaRef}
            configReady={configReady}
            streamingForCurrentChat={streamingForCurrentChat}
            modelSelectDropUp={false}
            onPaste={onPaste}
            onImageClick={onImageClick}
            currentChatId={currentChatId}
            onFileMentionSelected={onFileMentionSelected}
            voice={voice}
          />
        </div>
        {!briefing && activeAcpAgentId && (
          <ExternalSessionDiscoveryTray
            agentId={activeAcpAgentId}
            cwd={config.acp_cwd}
            currentChatId={currentChatId}
            onAdopted={onAdoptSession}
          />
        )}
      </div>
    </div>
  );
};
