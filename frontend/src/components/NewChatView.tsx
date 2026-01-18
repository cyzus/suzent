import React, { useMemo } from 'react';
import { ChatInputPanel } from './ChatInputPanel';
import { ConfigOptions, ChatConfig } from '../types/api';
import { RobotAvatar, RobotVariant } from './chat/RobotAvatar';

interface NewChatViewProps {
    input: string;
    setInput: React.Dispatch<React.SetStateAction<string>>;
    selectedImages: File[];
    handleImageSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
    removeImage: (index: number) => void;
    send: () => void;
    isStreaming: boolean;
    config: ChatConfig;
    setConfig: React.Dispatch<React.SetStateAction<ChatConfig>>;
    backendConfig: ConfigOptions | null;
    fileInputRef: React.RefObject<HTMLInputElement>;
    textareaRef: React.RefObject<HTMLTextAreaElement>;
    configReady: boolean;
    streamingForCurrentChat: boolean;
}

export const NewChatView: React.FC<NewChatViewProps> = ({
    input,
    setInput,
    selectedImages,
    handleImageSelect,
    removeImage,
    send,
    isStreaming,
    config,
    setConfig,
    backendConfig,
    fileInputRef,
    textareaRef,
    configReady,
    streamingForCurrentChat,
}) => {
    // Select a random friendly robot
    const greetingRobot = useMemo(() => {
        const variants: RobotVariant[] = ['peeker', 'jumper', 'dj', 'party', 'snoozer'];
        // Snoozer is rare (10% chance)
        if (Math.random() > 0.9) return 'snoozer';

        const friendly = ['peeker', 'jumper', 'dj', 'party'];
        return friendly[Math.floor(Math.random() * friendly.length)] as RobotVariant;
    }, []);

    return (
        <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-8 animate-brutal-drop">
            <div className="mb-8 flex flex-col items-center gap-6">
                <div className="w-24 h-24">
                    <RobotAvatar variant={greetingRobot} />
                </div>
                <h2 className="text-4xl sm:text-5xl font-brutal font-bold text-brutal-black mb-2 tracking-tight">
                    {(() => {
                        const hour = new Date().getHours();
                        if (hour < 5) return 'NIGHT OWL?';
                        if (hour < 12) return 'GOOD MORNING.';
                        if (hour < 17) return 'KEEP BUILDING.';
                        if (hour < 21) return 'GOOD EVENING.';
                        return 'BED TIME? OR MAYBE LATE NIGHT CODING?';
                    })()}
                </h2>
            </div>

            <div className="w-full max-w-2xl">
                <ChatInputPanel
                    input={input}
                    setInput={setInput}
                    selectedImages={selectedImages}
                    handleImageSelect={handleImageSelect}
                    removeImage={removeImage}
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
                />
            </div>
        </div>
    );
};
