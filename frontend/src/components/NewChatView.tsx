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
            <div className="w-24 h-24">
                <RobotAvatar variant={greetingRobot} />
            </div>
            <h2 className="text-4xl sm:text-5xl font-brutal font-bold text-brutal-black mb-2 tracking-tight">
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

