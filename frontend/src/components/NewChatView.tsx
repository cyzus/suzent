import React, { useState } from 'react';
import { ChatInputPanel, type FileMentionSelection } from './ChatInputPanel';
import { ConfigOptions, ChatConfig } from '../types/api';
import { GreetingCube } from './chat/GreetingCube';
import { useI18n } from '../i18n';
import { useProjects } from '../hooks/useProjects';

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
}

const GreetingPresence: React.FC<{ engaged: boolean }> = React.memo(({ engaged }) => {
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
        <div className="mb-8 flex flex-col items-center gap-5">
            <GreetingCube engaged={engaged} />
            <h2 className="text-4xl sm:text-5xl font-brutal font-bold text-brutal-black dark:text-white mb-2 tracking-tight">
                {getGreeting()}
            </h2>
        </div>
    );
});

GreetingPresence.displayName = 'GreetingPresence';

// Inline project picker shown above the chat input on the new-chat screen.
// Changes which project the next created chat will be assigned to.
const ProjectPicker: React.FC = () => {
    const { t } = useI18n();
    const { projects, currentProjectId, setCurrentProjectId, createProject } = useProjects();
    const [open, setOpen] = useState(false);
    const [creating, setCreating] = useState(false);
    const [newName, setNewName] = useState('');

    const current = projects.find(p => p.id === currentProjectId) || projects[0];
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

    return (
        <div className="relative mb-3 flex justify-center">
            <button
                type="button"
                onClick={() => setOpen(!open)}
                className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-extrabold uppercase tracking-wider border-2 border-brutal-black bg-white dark:bg-zinc-800 dark:text-white shadow-[2px_2px_0_0_#000] hover:bg-brutal-yellow hover:translate-y-[1px] hover:translate-x-[1px] hover:shadow-[1px_1px_0_0_#000] transition-all"
            >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 7l9-4 9 4M3 7v10l9 4 9-4V7" />
                </svg>
                <span className="opacity-60">{t('newChat.creatingIn')}</span>
                <span>{current.name}</span>
                <svg className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {open && (
                <div className="absolute top-full mt-1 z-30 min-w-[220px] bg-white dark:bg-zinc-800 border-2 border-brutal-black shadow-[3px_3px_0_0_#000]">
                    <div className="max-h-60 overflow-y-auto">
                        {projects.map(p => (
                            <button
                                key={p.id}
                                type="button"
                                onClick={() => { setCurrentProjectId(p.id); setOpen(false); }}
                                className={`w-full text-left px-3 py-2 text-xs font-bold hover:bg-neutral-100 dark:hover:bg-zinc-700 flex items-center justify-between gap-2 ${p.id === currentProjectId ? 'bg-brutal-yellow text-brutal-black' : 'dark:text-white'}`}
                            >
                                <span className="truncate">{p.name}</span>
                                {p.id === currentProjectId && <span className="text-[9px] uppercase opacity-70">●</span>}
                            </button>
                        ))}
                    </div>
                    <div className="border-t-2 border-brutal-black">
                        {creating ? (
                            <form onSubmit={handleCreate} className="flex items-center gap-1 p-2">
                                <input
                                    autoFocus
                                    type="text"
                                    value={newName}
                                    onChange={(e) => setNewName(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Escape') setCreating(false); }}
                                    placeholder={t('chatList.newProjectPlaceholder')}
                                    className="flex-1 min-w-0 px-2 py-1 text-xs font-bold bg-white dark:bg-zinc-700 dark:text-white border-2 border-brutal-black focus:outline-none"
                                />
                                <button type="submit" className="px-2 py-1 text-[10px] font-extrabold uppercase border-2 border-brutal-black bg-brutal-yellow hover:bg-yellow-300 text-brutal-black shrink-0">
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
}) => {
    const [isInputHovered, setIsInputHovered] = useState(false);
    const [isInputFocused, setIsInputFocused] = useState(false);
    const isInputEngaged = isInputHovered || isInputFocused;

    return (
        <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-8 animate-brutal-drop">
            <GreetingPresence engaged={isInputEngaged} />

            <div className="w-full max-w-2xl">
                <ProjectPicker />
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
                    />
                </div>
            </div>
        </div>
    );
};

