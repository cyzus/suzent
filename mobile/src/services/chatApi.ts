/**
 * Suzent chat API client.
 *
 * Handles REST calls and SSE streaming from the suzent server.
 */

import { ChatMessage, ChatSession, StreamEvent } from '../types';

let _baseUrl = '';

export function setBaseUrl(url: string) {
  _baseUrl = url.replace(/\/$/, '');
}

export function getBaseUrl(): string {
  return _baseUrl;
}

export async function ping(): Promise<boolean> {
  try {
    const res = await fetch(`${_baseUrl}/config`, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchChats(): Promise<ChatSession[]> {
  const res = await fetch(`${_baseUrl}/chats`);
  if (!res.ok) throw new Error('Failed to fetch chats');
  const data = await res.json();
  return data.chats ?? [];
}

export async function fetchChatMessages(chatId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${_baseUrl}/chats/${chatId}`);
  if (!res.ok) throw new Error('Failed to fetch messages');
  const data = await res.json();
  const rawMessages: Record<string, unknown>[] = data.messages ?? data.chat?.messages ?? [];
  return rawMessages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m, i) => {
      const content = typeof m.content === 'string'
        ? m.content
        : Array.isArray(m.content)
          ? (m.content as Array<{type: string; text?: string}>)
              .filter((p) => p.type === 'text')
              .map((p) => p.text ?? '')
              .join('')
          : String(m.content ?? '');
      return {
        id: `${chatId}-${i}`,
        role: m.role as 'user' | 'assistant',
        content,
        timestamp: (m.created_at as string) ?? new Date().toISOString(),
        files: m.files as ChatMessage['files'],
      };
    });
}

export async function deleteChat(chatId: string): Promise<void> {
  await fetch(`${_baseUrl}/chats/${chatId}`, { method: 'DELETE' });
}

/**
 * Send a message and stream the response via SSE.
 *
 * Calls onToken for each text delta, onDone when finished, onError on failure.
 */
export async function sendMessage(
  message: string,
  chatId: string | null,
  opts: {
    onToken: (delta: string) => void;
    onDone: (finalChatId: string) => void;
    onError: (err: string) => void;
  }
): Promise<void> {
  const body: Record<string, unknown> = { message, stream: true };
  if (chatId) body.chat_id = chatId;

  let response: Response;
  try {
    response = await fetch(`${_baseUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (err) {
    opts.onError(String(err));
    return;
  }

  if (!response.ok) {
    opts.onError(`Server error: ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    opts.onError('No response body');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let resolvedChatId = chatId ?? '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') continue;

        let event: StreamEvent;
        try {
          event = JSON.parse(raw);
        } catch {
          continue;
        }

        const ev = event as Record<string, unknown>;

        if (event.type === 'TEXT_MESSAGE_CONTENT' && event.delta) {
          opts.onToken(event.delta);
        }

        if (event.type === 'RUN_STARTED') {
          const tid = (ev.thread_id ?? ev.chat_id) as string | undefined;
          if (tid) resolvedChatId = tid;
        }

        if (event.type === 'AGENT_FINISHED' || event.type === 'RunFinishedEvent') {
          opts.onDone(resolvedChatId);
          return;
        }

        if (event.type === 'RUN_ERROR') {
          opts.onError((ev.message ?? ev.error ?? 'Agent error') as string);
          return;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  opts.onDone(resolvedChatId);
}

export async function stopStream(chatId: string): Promise<void> {
  await fetch(`${_baseUrl}/chat/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId }),
  });
}
