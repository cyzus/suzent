import React from 'react';
import { BrutalSelect } from './BrutalSelect';
import { BrutalDialog } from './BrutalDialog';
import { ConfigOptions, ChatConfig, type PermissionMode } from '../types/api';
import { open } from '@tauri-apps/plugin-dialog';
import { FileIcon } from './FileIcon';
import { PaperClipIcon, XMarkIcon, FolderIcon } from '@heroicons/react/24/outline';
import { FolderContextPicker } from './chat/FolderContextPicker';
import { useI18n } from '../i18n';
import { useSlashCommands } from '../hooks/useSlashCommands';
import { getApiBase, setChatPermissionMode } from '../lib/api';
import { buildMountedVolumes } from '../lib/volumeMounts';

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
    hideConfigSelector?: boolean;
    onPaste?: (files: File[]) => void;
    onImageClick?: (src: string) => void;
    currentChatId?: string | null;
    onFileMentionSelected?: (mention: FileMentionSelection) => void;
}

export interface FileMentionSelection {
    name: string;
    path: string;
    type?: 'file' | 'directory';
}

interface FileMentionSuggestion extends FileMentionSelection {
    root: string;
    size: number;
    mime_type: string;
}

const FILE_MENTION_PATTERN = /(^|\s)(@(?:"[^"]+"|\[[^\]]+\]|\/[^\s@]+))/g;
const INPUT_TEXT_METRIC_CLASS =
    'text-lg leading-7 tracking-normal font-sans font-medium [tab-size:4]';
const PERMISSION_MODES: PermissionMode[] = [
    'default',
    'accept_edits',
    'plan',
    'auto',
    'strict_readonly',
];

function getFileExtensionLabel(filename: string): string {
    const ext = filename.split('.').pop()?.trim().toUpperCase();
    if (!ext || ext === filename.toUpperCase()) return 'FILE';
    return ext.slice(0, 4);
}

function getMentionBadgeLabel(suggestion: FileMentionSuggestion): string {
    if (suggestion.type === 'directory') return 'DIR';
    return getFileExtensionLabel(suggestion.name);
}

function renderInputWithFileMentionHighlights(value: string): React.ReactNode[] {
    const nodes: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    FILE_MENTION_PATTERN.lastIndex = 0;
    while ((match = FILE_MENTION_PATTERN.exec(value)) !== null) {
        const prefix = match[1];
        const mention = match[2];
        const mentionStart = match.index + prefix.length;

        if (mentionStart > lastIndex) {
            nodes.push(value.slice(lastIndex, mentionStart));
        }

        nodes.push(
            <span
                key={`${mention}-${mentionStart}`}
                className="bg-brutal-yellow/70 dark:bg-yellow-600/60 text-brutal-blue dark:text-yellow-100"
            >
                {mention}
            </span>
        );
        lastIndex = mentionStart + mention.length;
    }

    if (lastIndex < value.length) {
        nodes.push(value.slice(lastIndex));
    }

    return nodes.length > 0 ? nodes : [value];
}

function hasFileMentionHighlight(value: string): boolean {
    FILE_MENTION_PATTERN.lastIndex = 0;
    return FILE_MENTION_PATTERN.test(value);
}

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
            className="w-20 h-20 object-cover border-3 border-brutal-black cursor-pointer hover:opacity-80 transition-opacity"
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
    hideConfigSelector = false,
    onPaste,
    onImageClick,
    currentChatId,
    onFileMentionSelected,
}) => {
    // --- Volume Mounting Logic ---
    const { t } = useI18n();
    const [selectedSuggestion, setSelectedSuggestion] = React.useState(0);
    const [mentionSuggestions, setMentionSuggestions] = React.useState<FileMentionSuggestion[]>([]);
    const [selectedMentionSuggestion, setSelectedMentionSuggestion] = React.useState(0);
    const [mentionRange, setMentionRange] = React.useState<{ start: number; end: number; query: string } | null>(null);
    const [isMentionLoading, setIsMentionLoading] = React.useState(false);
    const [isSavingPermissionMode, setIsSavingPermissionMode] = React.useState(false);
    const [pendingPermissionMode, setPendingPermissionMode] = React.useState<PermissionMode | null>(null);
    const highlightRef = React.useRef<HTMLPreElement | null>(null);
    const isComposingRef = React.useRef(false);
    const shouldHighlightFileMentions = hasFileMentionHighlight(input);
    const suggestions = useSlashCommands(input);
    const permissionMode = config.permission_mode ?? 'default';
    React.useEffect(() => { setSelectedSuggestion(0); }, [suggestions.length]);
    React.useEffect(() => { setSelectedMentionSuggestion(0); }, [mentionSuggestions.length]);

    const applyPermissionMode = React.useCallback(async (nextMode: PermissionMode) => {
        if (isSavingPermissionMode || nextMode === permissionMode) return;

        const previous = permissionMode;
        setConfig(prev => ({ ...prev, permission_mode: nextMode }));
        if (!currentChatId) return;

        setIsSavingPermissionMode(true);
        try {
            const state = await setChatPermissionMode(currentChatId, nextMode);
            setConfig(prev => ({ ...prev, permission_mode: state.mode }));
        } catch {
            setConfig(prev => ({ ...prev, permission_mode: previous }));
        } finally {
            setIsSavingPermissionMode(false);
        }
    }, [
        currentChatId,
        isSavingPermissionMode,
        permissionMode,
        setConfig,
    ]);

    const changePermissionMode = React.useCallback((nextMode: PermissionMode) => {
        if (isSavingPermissionMode || nextMode === permissionMode) return;
        if (nextMode === 'auto') {
            setPendingPermissionMode(nextMode);
            return;
        }
        void applyPermissionMode(nextMode);
    }, [applyPermissionMode, isSavingPermissionMode, permissionMode]);

    const updateMentionRange = React.useCallback((value: string, caret: number | null | undefined) => {
        if (caret == null) {
            setMentionRange(null);
            return;
        }

        const beforeCaret = value.slice(0, caret);
        const match = beforeCaret.match(/(^|\s)@([^\s@]*)$/);
        if (!match) {
            setMentionRange(null);
            return;
        }

        const prefixLength = match[1].length;
        const start = beforeCaret.length - match[0].length + prefixLength;
        setMentionRange({ start, end: caret, query: match[2] });
    }, []);

    React.useEffect(() => {
        if (!mentionRange || mentionRange.query.length < 1) {
            setMentionSuggestions([]);
            setIsMentionLoading(false);
            return;
        }

        const controller = new AbortController();
        const timer = window.setTimeout(async () => {
            try {
                setIsMentionLoading(true);
                const params = new URLSearchParams({
                    chat_id: currentChatId || 'draft',
                    query: mentionRange.query,
                    limit: '30',
                });
                if (config.sandbox_volumes?.length) {
                    params.set('volumes', JSON.stringify(config.sandbox_volumes));
                }
                const res = await fetch(`${getApiBase()}/sandbox/mentions?${params.toString()}`, {
                    signal: controller.signal,
                });
                if (!res.ok) {
                    setMentionSuggestions([]);
                    return;
                }
                const data = await res.json();
                setMentionSuggestions(Array.isArray(data.items) ? data.items : []);
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
    }, [mentionRange?.query, currentChatId, config.sandbox_volumes]);

    const insertMention = React.useCallback((suggestion: FileMentionSuggestion) => {
        if (!mentionRange) return;
        const mentionText = `@"${suggestion.name.replace(/"/g, "'")}"`;
        const nextValue = `${input.slice(0, mentionRange.start)}${mentionText} ${input.slice(mentionRange.end)}`;
        const nextCaret = mentionRange.start + mentionText.length + 1;
        setInput(nextValue);
        setMentionRange(null);
        setMentionSuggestions([]);
        onFileMentionSelected?.({ name: suggestion.name, path: suggestion.path, type: suggestion.type });
        window.setTimeout(() => {
            textareaRef.current?.focus();
            textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
        }, 0);
    }, [input, mentionRange, onFileMentionSelected, setInput, textareaRef]);

    const handleMountFolder = React.useCallback((paths: string[]) => {
        try {
            if (!paths || paths.length === 0) return;

            setConfig((prev) => {
                const currentVolumes = prev.sandbox_volumes || [];
                return { ...prev, sandbox_volumes: buildMountedVolumes(currentVolumes, paths) };
            });

        } catch (err) {
            console.error('Failed to mount folder', err);
        }
    }, [setConfig]);

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
        <div className="flex flex-col gap-2">
          <form
              onSubmit={(e) => { e.preventDefault(); send(); }}
              className="bg-neutral-50 dark:bg-zinc-800 border-2 border-brutal-black shadow-brutal-sm p-2 flex flex-col gap-2 relative group focus-within:shadow-brutal focus-within:-translate-y-[1px] transition-all duration-200 z-20 text-left"
          >
            {/* Unified file preview section */}
            {selectedFiles.length > 0 && (
                <div className="flex flex-col gap-2 p-2 mb-1">
                    {selectedFiles.map((file, idx) => {
                        const isImage = file.type.startsWith('image/');

                        return (
                            <div key={idx}>
                                {isImage ? (
                                    // Image preview (larger, visual)
                                    // Image preview with proper URL cleanup
                                    <div className="relative group/image inline-block">
                                        <ImagePreviewThumbnail
                                            file={file}
                                            onImageClick={onImageClick}
                                        />
                                        <button
                                            type="button"
                                            onClick={() => removeFile(idx)}
                                            className="absolute -top-2 -right-2 w-6 h-6 bg-brutal-red border-2 border-brutal-black text-white text-sm flex items-center justify-center font-bold shadow-brutal-sm hover:shadow-none transition-all"
                                            title={t('chatInput.removeFile')}
                                        >
                                            ×
                                        </button>
                                    </div>
                                ) : (
                                    // File card (icon + name + size)
                                    <div className="flex items-center gap-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black p-2">
                                        <FileIcon mimeType={file.type} className="w-5 h-5 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-bold text-brutal-black dark:text-white truncate">{file.name}</div>
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
                                )}
                            </div>
                        );
                    })}
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
                                    className={`flex items-baseline gap-3 px-3 py-2 text-sm ${(!input.includes(' ') || cmd.isOption) ? 'cursor-pointer ' : ''}${i === selectedSuggestion && (!input.includes(' ') || cmd.isOption) ? 'bg-brutal-yellow dark:bg-yellow-600 text-brutal-black' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'}`}
                                    onMouseDown={(e) => { 
                                        e.preventDefault(); 
                                        if (!input.includes(' ') || cmd.isOption) {
                                            const textToInsert = cmd.isOption && cmd.parentCmd 
                                                ? `${cmd.parentCmd} ${cmd.aliases[0]} ` 
                                                : `${cmd.aliases?.[0] || cmd.usage} `;
                                            setInput(textToInsert); 
                                        }
                                    }}
                                >
                                    <span className="font-bold font-mono shrink-0">{cmd.aliases[0]}</span>
                                    <span className="text-neutral-500 dark:text-neutral-400 truncate">{cmd.description}</span>
                                    <span className="ml-auto font-mono text-xs text-neutral-400 dark:text-neutral-500 shrink-0">{cmd.usage}</span>
                                </div>
                            </React.Fragment>
                        );
                    })}
                </div>
            )}

            {mentionRange && (
                <div className="absolute left-2 right-2 bottom-[calc(100%-0.5rem)] border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm overflow-hidden max-h-56 overflow-y-auto z-40">
                    <div className="px-3 py-1 bg-neutral-200 dark:bg-zinc-900 border-b border-neutral-300 dark:border-zinc-700 text-xs font-bold text-neutral-500 uppercase tracking-wider">
                        {t('chatInput.fileMentions')}
                    </div>
                    {mentionSuggestions.length > 0 ? (
                        mentionSuggestions.map((suggestion, i) => (
                            <div
                                key={suggestion.path}
                                className={`flex items-center gap-3 px-3 py-2 text-sm cursor-pointer ${i === selectedMentionSuggestion ? 'bg-brutal-yellow dark:bg-yellow-600 text-brutal-black' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'}`}
                                onMouseDown={(e) => {
                                    e.preventDefault();
                                    insertMention(suggestion);
                                }}
                            >
                                <div className="w-10 h-8 shrink-0 border-2 border-brutal-black bg-brutal-yellow shadow-[2px_2px_0_0_#000] flex items-center justify-center">
                                    <span className="text-[9px] leading-none font-black text-brutal-blue">
                                        {getMentionBadgeLabel(suggestion)}
                                    </span>
                                </div>
                                <div className="min-w-0 flex-1">
                                    <div className="font-bold truncate">{suggestion.name}</div>
                                    <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate font-mono">{suggestion.path}</div>
                                </div>
                            </div>
                        ))
                    ) : (
                        <div className="px-3 py-3 text-sm text-neutral-500 dark:text-neutral-400">
                            {mentionRange.query.length < 1
                                ? t('chatInput.fileMentionTypeToSearch')
                                : isMentionLoading
                                    ? t('chatInput.fileMentionSearching')
                                    : t('chatInput.fileMentionNoResults')}
                        </div>
                    )}
                </div>
            )}

            <div className="relative">
                {shouldHighlightFileMentions && (
                    <pre
                        ref={highlightRef}
                        aria-hidden="true"
                        className={`absolute inset-0 w-full min-h-[44px] max-h-[200px] overflow-hidden whitespace-pre-wrap break-words pointer-events-none text-brutal-black dark:text-white border-none p-2 ${INPUT_TEXT_METRIC_CLASS}`}
                    >
                        {renderInputWithFileMentionHighlights(input)}
                        {' '}
                    </pre>
                )}
                <textarea
                    autoFocus
                    ref={textareaRef}
                    className={`relative w-full resize-none overflow-y-auto min-h-[44px] max-h-[200px] bg-transparent focus:outline-none caret-brutal-black dark:caret-white placeholder-neutral-400 dark:placeholder-neutral-500 placeholder:font-bold border-none p-2 selection:bg-brutal-blue/30 text-left ${shouldHighlightFileMentions ? 'text-transparent' : 'text-brutal-black dark:text-white'} ${INPUT_TEXT_METRIC_CLASS}`}
                    value={input}
                    onScroll={(e) => {
                        if (shouldHighlightFileMentions && highlightRef.current) {
                            highlightRef.current.scrollTop = e.currentTarget.scrollTop;
                        }
                    }}
                    onChange={(e) => {
                        setInput(e.target.value);
                        updateMentionRange(e.target.value, e.target.selectionStart);
                    }}
                    onCompositionStart={() => {
                        isComposingRef.current = true;
                    }}
                    onCompositionEnd={() => {
                        window.setTimeout(() => {
                            isComposingRef.current = false;
                        }, 0);
                    }}
                    onClick={(e) => updateMentionRange(input, e.currentTarget.selectionStart)}
                    onKeyUp={(e) => {
                        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
                            updateMentionRange(input, e.currentTarget.selectionStart);
                        }
                    }}
                    onKeyDown={(e) => {
                    // Always ignore Enter if IME composition is active to allow selecting characters
                    // Including e.keyCode === 229 for broad cross-browser compatibility
                    if (e.key === 'Enter' && (isComposingRef.current || e.nativeEvent.isComposing || e.keyCode === 229)) {
                        return;
                    }

                    if (mentionRange && mentionSuggestions.length > 0) {
                        if (e.key === 'ArrowUp') {
                            e.preventDefault();
                            setSelectedMentionSuggestion(i => Math.max(0, i - 1));
                            return;
                        }
                        if (e.key === 'ArrowDown') {
                            e.preventDefault();
                            setSelectedMentionSuggestion(i => Math.min(mentionSuggestions.length - 1, i + 1));
                            return;
                        }
                        if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                            e.preventDefault();
                            insertMention(mentionSuggestions[selectedMentionSuggestion]);
                            return;
                        }
                        if (e.key === 'Escape') {
                            setMentionRange(null);
                            setMentionSuggestions([]);
                            setIsMentionLoading(false);
                            return;
                        }
                    }
                    if (mentionRange && mentionSuggestions.length === 0) {
                        if (e.key === 'Escape') {
                            setMentionRange(null);
                            setMentionSuggestions([]);
                            setIsMentionLoading(false);
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
                        if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedSuggestion(i => Math.max(0, i - 1)); return; }
                        if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedSuggestion(i => Math.min(suggestions.length - 1, i + 1)); return; }
                        if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                            e.preventDefault();
                            if (activeCmd) {
                                const textToInsert = activeCmd.isOption && activeCmd.parentCmd 
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
                        if (e.key === 'Escape') { setInput(''); return; }
                    } else if (suggestions.length > 0 && hasSpace && !isOptionMode) {
                        // Passive hint mode: Escape clears, but Enter/Tab/Arrows act normally
                        if (e.key === 'Escape') { setInput(''); return; }
                    }
                    
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (configReady && input.trim()) {
                            send();
                        }
                    }
                    }}
                    placeholder={
                        !configReady
                            ? t('chatInput.placeholderLoading').toUpperCase()
                            : streamingForCurrentChat
                                ? t('chatInput.placeholderRedirect')
                                : t('chatInput.placeholderReady')
                    }
                    disabled={!configReady}
                    onPaste={(e) => {
                    if (onPaste && e.clipboardData) {
                        // Method 1: Get files directly (works for all file types pasted)
                        const files = Array.from(e.clipboardData.files || []);

                        // Method 2: Fallback to items for screenshot/image data
                        if (files.length === 0) {
                            const items = Array.from(e.clipboardData.items);
                            items.forEach(item => {
                                if (item.kind === 'file') {
                                    const file = item.getAsFile();
                                    if (file) {
                                        files.push(file);
                                    }
                                }
                            });
                        }

                        if (files.length > 0) {
                            onPaste(files);
                        }
                    }
                    }}
                />
            </div>

            {/* Button row */}
            <div className="flex flex-nowrap items-center gap-2 pt-1 pl-2 pr-1">
                {/* Left: folder + attachment */}
                <FolderContextPicker
                    onMount={handleMountFolder}
                    activeVolumes={config.sandbox_volumes || []}
                    onRemoveVolume={removeVolume}
                    disabled={!configReady || streamingForCurrentChat || isUploading}
                    dropUp={modelSelectDropUp}
                />
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
                    className="text-brutal-black hover:text-brutal-blue transition-colors disabled:opacity-40 shrink-0"
                    title={t('chatInput.attachFiles')}
                    disabled={!configReady || streamingForCurrentChat || isUploading}
                >
                    <PaperClipIcon className="w-6 h-6" />
                </button>

                {/* Spacer */}
                <div className="flex-1" />

                {/* Right: model picker (shrinks) + action button (fixed) */}
                {configReady && !hideConfigSelector && (
                    <div className="relative min-w-0 shrink">
                        <BrutalSelect
                            value={config.model}
                            onChange={(val) => setConfig(prev => ({ ...prev, model: val }))}
                            options={backendConfig!.models}
                            placeholder={t('chatInput.modelPlaceholder').toUpperCase()}
                            dropUp={modelSelectDropUp}
                            className="h-10 text-sm"
                            dropdownClassName="min-w-[200px] right-0"
                        />
                    </div>
                )}

                {/* Redirect button (shown when streaming and user has typed) */}
                {stopStreaming && streamingForCurrentChat && input.trim() ? (
                    <button
                        type="submit"
                        className="h-9 border-2 border-brutal-black shadow-[2px_2px_0_0_#000] brutal-btn duration-100 px-4 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed uppercase shrink-0 bg-brutal-yellow text-brutal-black"
                        disabled={!configReady}
                        title={t('chatInput.redirectAgent')}
                    >
                        {t('chatInput.redirect').toUpperCase()}
                    </button>
                ) : stopStreaming && streamingForCurrentChat ? (
                    <button
                        type="button"
                        onClick={(e) => {
                            e.preventDefault();
                            stopStreaming();
                        }}
                        className="h-9 border-2 border-brutal-black shadow-[2px_2px_0_0_#000] brutal-btn duration-100 px-4 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase shrink-0 bg-brutal-red"
                        disabled={stopInFlight}
                        title={t('chatInput.stopGenerating')}
                    >
                        {t('chatInput.stop').toUpperCase()}
                    </button>
                ) : (
                    <button
                        type="submit"
                        className="h-9 border-2 border-brutal-black shadow-[2px_2px_0_0_#000] brutal-btn duration-100 px-4 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase shrink-0 bg-brutal-blue"
                        disabled={streamingForCurrentChat || !configReady}
                        title={t('chatInput.sendMessage')}
                    >
                        {t('chatInput.send').toUpperCase()}
                    </button>
                )}
            </div>
          </form>

          {!hideConfigSelector && (
            <div
              className="flex items-center px-2"
              title={t(`chatWindow.permissionModeDescriptions.${permissionMode}`)}
            >
              <BrutalSelect
                value={permissionMode}
                onChange={value => changePermissionMode(value as PermissionMode)}
                options={PERMISSION_MODES.map(option => ({
                  value: option,
                  label: t(`chatWindow.permissionModeInputLabels.${option}`),
                }))}
                dropUp={true}
                hideChevron={true}
                disabled={!configReady || streamingForCurrentChat || isSavingPermissionMode}
                className="inline-block w-auto"
                buttonClassName="!h-7 !w-auto !gap-1.5 !border-0 !bg-transparent dark:!bg-transparent !px-0 !py-0 !font-sans !text-[13px] !font-medium !normal-case !tracking-normal !text-neutral-600 dark:!text-neutral-400 !shadow-none !translate-x-0 !translate-y-0 hover:!bg-transparent hover:!text-brutal-black dark:hover:!bg-transparent dark:hover:!text-white"
                dropdownClassName="min-w-[220px] font-mono text-[10px]"
              />
            </div>
          )}

          <BrutalDialog
            open={pendingPermissionMode === 'auto'}
            title={t('chatWindow.autoModeDialogTitle')}
            message={t('chatWindow.autoModeConfirmation')}
            onClose={() => setPendingPermissionMode(null)}
            actions={[
              {
                label: t('chatWindow.autoModeCancel'),
                tone: 'default',
              },
              {
                label: t('chatWindow.autoModeEnable'),
                tone: 'primary',
                onClick: () => applyPermissionMode('auto'),
              },
            ]}
          />
        </div>
    );
};
