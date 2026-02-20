import React from 'react';
import { BrutalSelect } from './BrutalSelect';
import { ConfigOptions, ChatConfig } from '../types/api';
import { open } from '@tauri-apps/plugin-dialog';
import { FileIcon } from './FileIcon';
import { PaperClipIcon, XMarkIcon, FolderIcon } from '@heroicons/react/24/outline';
import { FolderContextPicker } from './chat/FolderContextPicker';
import { useI18n } from '../i18n';

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
    onPaste,
    onImageClick,
}) => {
    const { t } = useI18n();
    // --- Volume Mounting Logic ---
    const handleMountFolder = React.useCallback((paths: string[]) => {
        try {
            if (!paths || paths.length === 0) return;

            setConfig((prev) => {
                const currentVolumes = prev.sandbox_volumes || [];
                const newVolumes = [...currentVolumes];

                paths.forEach((hostPath) => {
                    // Normalize path separators
                    const normalizedHost = hostPath.replace(/\\/g, '/');
                    // Extract safe folder name
                    const folderName = normalizedHost.split('/').pop() || 'data';

                    // Simple collision handling
                    let containerPath = `/mnt/${folderName}`;
                    let counter = 1;

                    // Check if this container path is already taken by a DIFFERENT host path
                    // Or if we just want uniqueness in the container list
                    while (newVolumes.some(v => {
                        const lastSemi = v.lastIndexOf(':');
                        const existContainer = v.substring(lastSemi + 1);
                        return existContainer === containerPath;
                    })) {
                        containerPath = `/mnt/${folderName}-${counter}`;
                        counter++;
                    }

                    // Avoid re-mounting same host path (update its container mapping if changed, or skip)
                    // For simplicity, if host path exists, we assume user might want to re-add? 
                    // Let's filter out existing host path first to be safe or just skip
                    const existsIndex = newVolumes.findIndex(v => v.substring(0, v.lastIndexOf(':')) === hostPath);
                    if (existsIndex === -1) {
                        newVolumes.push(`${hostPath}:${containerPath}`);
                    }
                });

                return { ...prev, sandbox_volumes: newVolumes };
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
            className="bg-neutral-50 border-2 border-brutal-black shadow-brutal-sm p-2 flex flex-col gap-2 relative group focus-within:shadow-brutal focus-within:-translate-y-[1px] transition-all duration-200 z-20"
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
                                    <div className="flex items-center gap-2 bg-white border-2 border-brutal-black p-2">
                                        <FileIcon mimeType={file.type} className="w-5 h-5 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <div className="text-sm font-bold text-brutal-black truncate">{file.name}</div>
                                            <div className="text-xs text-neutral-500">
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

            < textarea
                autoFocus
                ref={textareaRef}
                className="w-full resize-none overflow-y-auto min-h-[44px] max-h-[200px] bg-transparent focus:outline-none text-lg text-brutal-black placeholder-neutral-400 font-medium placeholder:font-bold border-none p-2"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (!isStreaming && configReady && input.trim()) {
                            send();
                        }
                    }
                }}
                placeholder={configReady ? t('chatInput.placeholderReady') : t('chatInput.placeholderLoading')}
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
                    {configReady && (
                        <div className="relative shrink-0">
                            <BrutalSelect
                                value={config.model}
                                onChange={(val) => setConfig(prev => ({ ...prev, model: val }))}
                                options={backendConfig!.models}
                                placeholder={t('chatInput.modelPlaceholder')}
                                dropUp={modelSelectDropUp}
                                className="h-10 text-sm"
                                dropdownClassName="min-w-[200px] right-0"
                            />
                        </div>
                    )}

                    <button
                        type={stopStreaming && streamingForCurrentChat ? "button" : "submit"}
                        onClick={(e) => {
                            if (stopStreaming && streamingForCurrentChat) {
                                e.preventDefault();
                                stopStreaming();
                            }
                        }}
                        className={`h-9 border-2 border-brutal-black shadow-[2px_2px_0_0_#000] brutal-btn duration-100 px-4 text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed text-white uppercase ml-1 shrink-0 ${stopStreaming && streamingForCurrentChat ? 'bg-brutal-red' : 'bg-brutal-blue'}`}
                        disabled={
                            stopStreaming && streamingForCurrentChat
                                ? stopInFlight
                                : (isStreaming || !configReady)
                        }
                        title={stopStreaming && streamingForCurrentChat ? t('chatInput.stopGenerating') : t('chatInput.sendMessage')}
                    >
                        {stopStreaming && streamingForCurrentChat ? t('chatInput.stop') : t('chatInput.send')}
                    </button>
                </div>
            </div>
        </form>
    );
};
