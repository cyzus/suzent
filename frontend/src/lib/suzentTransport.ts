/**
 * Custom chat transport for Suzent backend.
 *
 * Uses Vercel AI SDK's `DefaultChatTransport` with:
 * - `prepareSendMessagesRequest` to transform the SDK's message format into
 *   the Suzent backend's expected payload ({ message, config, chat_id })
 * - Custom `fetch` wrapper to handle FormData for image file uploads
 *   (since DefaultChatTransport always calls JSON.stringify on the body)
 *
 * The DefaultChatTransport handles all SSE Data Stream Protocol parsing,
 * UIMessageChunk validation, and abort signal management.
 */

import { DefaultChatTransport } from 'ai';
import type { UIMessage } from 'ai';
import type { ChatConfig, FileAttachment } from '../types/api';
import { getApiBase } from './api';

/**
 * Extra payload that ChatWindow passes via `sendMessage(msg, { body: ... })`.
 */
export interface SuzentRequestBody {
  config: ChatConfig;
  chatId: string | null;
  reset?: boolean;
  filesMetadata?: FileAttachment[];
}

/**
 * Extract the last user message text from the SDK's UIMessage array.
 * The SDK appends the user message to `messages` before calling the transport.
 */
function extractLastUserText(messages: UIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role === 'user') {
      // Extract text from parts
      for (const part of msg.parts) {
        if (part.type === 'text') {
          return part.text;
        }
      }
      break;
    }
  }
  return '';
}

/**
 * Return value from createSuzentTransport.
 */
export interface SuzentTransportHandle {
  /** The DefaultChatTransport instance to pass to useChat. */
  transport: DefaultChatTransport<UIMessage>;
  /**
   * Set image files to be uploaded with the next sendMessage call.
   * Called before sendMessage; cleared automatically after the fetch.
   */
  setPendingImageFiles: (files: File[] | null) => void;
}

/**
 * Creates a SuzentTransport instance.
 *
 * Uses a closure to hold pending image files for FormData uploads,
 * since DefaultChatTransport always JSON.stringify's the body.
 */
export function createSuzentTransport(): SuzentTransportHandle {
  // Mutable state: image files to include in the next request.
  // Set via setPendingImageFiles() before calling sendMessage(),
  // consumed and cleared by the custom fetch wrapper.
  let pendingImageFiles: File[] | null = null;

  const transport = new DefaultChatTransport({
    api: `${getApiBase()}/chat`,

    // Custom fetch wrapper to handle FormData when image files are pending.
    // DefaultChatTransport calls JSON.stringify(body) before passing to fetch,
    // so we parse it back and re-encode as FormData when needed.
    fetch: async (input, init) => {
      if (pendingImageFiles && pendingImageFiles.length > 0) {
        const files = pendingImageFiles;
        pendingImageFiles = null; // Clear immediately

        // Parse the JSON body that DefaultChatTransport serialized
        let bodyObj: Record<string, any> = {};
        try {
          bodyObj = JSON.parse(init?.body as string);
        } catch {
          // Fallback: body might already be an object in some edge cases
        }

        const formData = new FormData();
        formData.append('message', bodyObj.message || '');
        formData.append('config', JSON.stringify(bodyObj.config || {}));
        formData.append('reset', String(bodyObj.reset || false));
        if (bodyObj.chat_id) {
          formData.append('chat_id', bodyObj.chat_id);
        }
        if (bodyObj.files && Array.isArray(bodyObj.files)) {
          formData.append('files_metadata', JSON.stringify(bodyObj.files));
        }
        for (const file of files) {
          formData.append('files', file);
        }

        // Reconstruct fetch init without the JSON body and Content-Type
        const newHeaders: Record<string, string> = {};
        if (init?.headers) {
          // Copy headers except Content-Type (let browser set it for multipart)
          const h = init.headers as Record<string, string>;
          for (const [k, v] of Object.entries(h)) {
            if (k.toLowerCase() !== 'content-type') {
              newHeaders[k] = v;
            }
          }
        }

        return globalThis.fetch(input, {
          method: init?.method ?? 'POST',
          body: formData,
          headers: newHeaders,
          credentials: init?.credentials,
          signal: init?.signal,
        });
      }

      // Standard path: pass through to global fetch unchanged
      return globalThis.fetch(input, init);
    },

    prepareSendMessagesRequest({ messages, body }) {
      const extra = (body ?? {}) as Partial<SuzentRequestBody>;
      const messageText = extractLastUserText(messages);
      const config = extra.config ?? {};
      const chatId = extra.chatId ?? null;
      const reset = extra.reset ?? false;
      const filesMetadata = extra.filesMetadata;

      // Build our backend's expected JSON payload
      const payload: Record<string, unknown> = {
        message: messageText,
        config,
        reset,
      };
      if (chatId) {
        payload.chat_id = chatId;
      }
      if (filesMetadata && filesMetadata.length > 0) {
        payload.files = filesMetadata;
      }

      return {
        body: payload,
        headers: {
          'Content-Type': 'application/json',
        },
      };
    },
  });

  return {
    transport,
    setPendingImageFiles(files: File[] | null) {
      pendingImageFiles = files;
    },
  };
}
