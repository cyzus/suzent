import { createContext, useContext } from 'react';

export type OpenFileHandler = (filePath: string, fileName: string, shiftKey?: boolean) => void;

/**
 * Opens a file in the chat's right-side preview. Provided by ChatWindow so a
 * tool block can link its file without threading a callback through every
 * message and rail component in between; null where no preview exists.
 */
export const OpenFileContext = createContext<OpenFileHandler | null>(null);

export function useOpenFile(): OpenFileHandler | null {
  return useContext(OpenFileContext);
}
