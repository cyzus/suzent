import React from 'react';
import { BrutalSelect } from './BrutalSelect';
import { ConfigOptions, ChatConfig } from '../types/api';
import { open } from '@tauri-apps/plugin-dialog';
import { FileIcon } from './FileIcon';
import { PaperClipIcon, XMarkIcon, FolderIcon } from '@heroicons/react/24/outline';
import { FolderContextPicker } from './chat/FolderContextPicker';
import { useI18n } from '../i18n';
import { useSlashCommands } from '../hooks/useSlashCommands';
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
    isStreaming: boolean;
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
    isStreaming,
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
}) => {
    // --- Volume Mounting Logic ---
    const { t } = useI18n();
    const [selectedSuggestion, setSelectedSuggestion] = React.useState(0);
    const suggestions = useSlashCommands(input);
    React.useEffect(() => { setSelectedSuggestion(0); }, [suggestions.length]);
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
        <form
            onSubmit={(e) => { e.preventDefault(); send(); }}
            className="bg-neutral-50 dark:bg-zinc-800 border-2 border-brutal-black shadow-brutal-sm p-2 flex flex-col gap-2 relative group focus-within:shadow-brutal focus-within:-translate-y-[1px] transition-all duration-200 z-20"
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
                <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm mb-1 overflow-hidden">
                    {suggestions.map((cmd, i) => (
                        <div
                            key={cmd.name}
                            className={`flex items-baseline gap-3 px-3 py-2 cursor-pointer text-sm ${i === selectedSuggestion ? 'bg-brutal-yellow dark:bg-yellow-600 text-brutal-black' : 'hover:bg-neutral-100 dark:hover:bg-zinc-700 text-brutal-black dark:text-white'}`}
                            onMouseDown={(e) => { e.preventDefault(); setInput(cmd.usage + ' '); }}
                        >
                            <span className="font-bold font-mono shrink-0">{cmd.aliases[0]}</span>
                            <span className="text-neutral-500 dark:text-neutral-400 truncate">{cmd.description}</span>
                            <span className="ml-auto font-mono text-xs text-neutral-400 dark:text-neutral-500 shrink-0">{cmd.usage}</span>
                        </div>
                    ))}
                </div>
            )}

            < textarea
                autoFocus
                ref={textareaRef}
                className="w-full resize-none overflow-y-auto min-h-[44px] max-h-[200px] bg-transparent focus:outline-none text-lg text-brutal-black dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 font-medium placeholder:font-bold border-none p-2"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                    if (suggestions.length > 0) {
                        if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedSuggestion(i => Math.max(0, i - 1)); return; }
                        if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedSuggestion(i => Math.min(suggestions.length - 1, i + 1)); return; }
                        if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
                            e.preventDefault();
                            setInput(suggestions[selectedSuggestion].usage + ' ');
                            return;
                        }
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

            {/* Button row */}
            <div className="flex flex-nowrap gap-2 items-center justify-between pt-1">
                <div className="flex gap-2 items-center pl-2 shrink-0">
                    {/* Folder Context Button */}
                    <FolderContextPicker
                        onMount={handleMountFolder}
                        activeVolumes={config.sandbox_volumes || []}
                        onRemoveVolume={removeVolume}
                        disabled={!configReady || isStreaming || isUploading}
                        dropUp={modelSelectDropUp}
                    />

                    {/* Unified file input (all types) */}
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
                        disabled={!configReady || isStreaming || isUploading}
                    >
                        <PaperClipIcon className="w-6 h-6" />
                    </button>
                </div>

                <div className="flex flex-nowrap gap-2 items-center justify-end flex-1 min-w-0">
                    {configReady && !hideConfigSelector && (
                        <div className="relative shrink-0">
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
                            className="h-9 border-2 border-brutal-black shadow-[2px_2px_0_0_#000] brutal-btn duration-100 px-4 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase ml-1 shrink-0 bg-brutal-yellow text-brutal-black"
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
                            className="h-9 border-2 border-brutal-black shadow-[2px_2px_0_0_#000] brutal-btn duration-100 px-4 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase ml-1 shrink-0 bg-brutal-red"
                            disabled={stopInFlight}
                            title={t('chatInput.stopGenerating')}
                        >
                            {t('chatInput.stop').toUpperCase()}
                        </button>
                    ) : (
                        <button
                            type="submit"
                            className="h-9 border-2 border-brutal-black shadow-[2px_2px_0_0_#000] brutal-btn duration-100 px-4 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase ml-1 shrink-0 bg-brutal-blue"
                            disabled={isStreaming || !configReady}
                            title={t('chatInput.sendMessage')}
                        >
                            {t('chatInput.send').toUpperCase()}
                        </button>
                    )}
                </div>
            </div>
        </form>
    );
};
