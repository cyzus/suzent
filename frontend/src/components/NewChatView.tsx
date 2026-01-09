import React from 'react';
import { BrutalSelect } from './BrutalSelect';
import { ChatInputPanel } from './ChatInputPanel';
import { ConfigOptions, ChatConfig } from '../types/api';

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
    return (
        <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center p-8 animate-brutal-drop">
            <div className="mb-12">
                <h2 className="text-4xl sm:text-5xl font-brutal font-bold text-brutal-black mb-2 tracking-tight">
                    {(() => {
                        const hour = new Date().getHours();
                        if (hour < 12) return 'Morning, Suzy';
                        if (hour < 18) return 'Afternoon, Suzy';
                        return 'Evening, Suzy';
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
