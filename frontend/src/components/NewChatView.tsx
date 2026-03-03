import React, { useMemo } from 'react';
import { ChatInputPanel } from './ChatInputPanel';
import { ConfigOptions, ChatConfig } from '../types/api';
import { RobotAvatar, RobotVariant } from './chat/RobotAvatar';
import { useI18n } from '../i18n';

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
    isStreaming: boolean;
    config: ChatConfig;
    setConfig: React.Dispatch<React.SetStateAction<ChatConfig>>;
    backendConfig: ConfigOptions | null;
    fileInputRef: React.RefObject<HTMLInputElement>;
    textareaRef: React.RefObject<HTMLTextAreaElement>;
    configReady: boolean;
    streamingForCurrentChat: boolean;
    onPaste?: (files: File[]) => void;
    onImageClick?: (src: string) => void;
}

// Memoized greeting robot component to prevent animation restarts on input changes
const GreetingRobot: React.FC = React.memo(() => {
    const { t } = useI18n();
    // Select a random friendly robot (only runs once per mount)
    const greetingRobot = useMemo(() => {
        const variants: RobotVariant[] = ['peeker', 'jumper', 'dj', 'party', 'snoozer'];
        // Snoozer is rare (10% chance)
        if (Math.random() > 0.9) return 'snoozer';

        const friendly = ['peeker', 'jumper', 'dj', 'party'];
        return friendly[Math.floor(Math.random() * friendly.length)] as RobotVariant;
    }, []);

    const getGreeting = () => {
        const hour = new Date().getHours();
        if (hour < 5) return t('newChat.greetings.nightOwl').toUpperCase();
        if (hour < 12) return t('newChat.greetings.goodMorning').toUpperCase();
        if (hour < 17) return t('newChat.greetings.keepBuilding').toUpperCase();
        if (hour < 21) return t('newChat.greetings.goodEvening').toUpperCase();
        return t('newChat.greetings.bedTime').toUpperCase();
    };

    return (
        <div className="mb-8 flex flex-col items-center gap-6">
            {/* Thin-stroke orbit decoration */}
            <div className="relative w-40 h-40 flex items-center justify-center">
                {/* Outer square — slow clockwise */}
                <div
                    className="absolute inset-0 border border-neutral-400/40 dark:border-[#FF6600]/40 animate-spin"
                    style={{ animationDuration: '20s', animationTimingFunction: 'linear' }}
                />
                {/* Inner square — counter-clockwise, offset size */}
                <div
                    className="absolute border border-neutral-300/60 dark:border-white/20 animate-spin"
                    style={{ width: '72%', height: '72%', animationDuration: '13s', animationDirection: 'reverse', animationTimingFunction: 'linear' }}
                />
                {/* Corner brackets — static */}
                <div className="absolute top-0 left-0 w-4 h-4 border-l border-t border-neutral-500/60 dark:border-[#FF6600]/60 pointer-events-none" />
                <div className="absolute top-0 right-0 w-4 h-4 border-r border-t border-neutral-500/60 dark:border-[#FF6600]/60 pointer-events-none" />
                <div className="absolute bottom-0 left-0 w-4 h-4 border-l border-b border-neutral-500/60 dark:border-[#FF6600]/60 pointer-events-none" />
                <div className="absolute bottom-0 right-0 w-4 h-4 border-r border-b border-neutral-500/60 dark:border-[#FF6600]/60 pointer-events-none" />
                <div className="w-20 h-20 relative z-10">
                    <RobotAvatar variant={greetingRobot} />
                </div>
            </div>
            <h2 className="text-4xl sm:text-5xl font-brutal font-bold text-brutal-black dark:text-white mb-2 tracking-tight">
                {getGreeting()}
            </h2>
        </div>
    );
});

GreetingRobot.displayName = 'GreetingRobot';

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
    isStreaming,
    config,
    setConfig,
    backendConfig,
    fileInputRef,
    textareaRef,
    configReady,
    streamingForCurrentChat,
    onPaste,
    onImageClick,
}) => {

    return (
        <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-8 animate-brutal-drop">
            <GreetingRobot />

            <div className="w-full max-w-2xl">
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
                    isStreaming={isStreaming}
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
                />
            </div>
        </div>
    );
};

