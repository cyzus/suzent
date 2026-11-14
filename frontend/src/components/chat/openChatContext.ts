import { createContext, useContext } from 'react';

export type OpenChatHandler = (chatId: string) => Promise<boolean>;

/**
 * Switches to another chat, such as the session a Regent dispatch went to.
 * Provided by ChatWindow, like OpenFileContext; resolves false when the chat
 * could not be opened.
 */
export const OpenChatContext = createContext<OpenChatHandler | null>(null);

export function useOpenChat(): OpenChatHandler | null {
  return useContext(OpenChatContext);
}
