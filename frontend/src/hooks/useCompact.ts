import { useState, useCallback } from 'react';
import { getApiBase } from '../lib/api';

export type CompactionStage = 'idle' | 'loading' | 'analyzing' | 'summarizing' | 'saving' | 'complete' | 'error';

export type CompactionProgress = {
  stage: CompactionStage;
  message?: string;
};

export type CompactionResult = {
  skipped: boolean;
  reason?: string;
  tokensBefore?: number;
  tokensAfter?: number;
  messagesBefore?: number;
  messagesAfter?: number;
  error?: string;
};

export function useCompact() {
  const [progress, setProgress] = useState<CompactionProgress>({ stage: 'idle' });

  const compact = useCallback(async (chatId: string, focus?: string): Promise<CompactionResult> => {
    setProgress({ stage: 'loading' });

    try {
      const res = await fetch(`${getApiBase()}/chat/compact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, focus: focus || undefined }),
      });

      if (!res.ok || !res.body) {
        const msg = `Request failed: ${res.status}`;
        setProgress({ stage: 'error', message: msg });
        return { skipped: false, error: msg };
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let result: CompactionResult = { skipped: false, error: 'No response received' };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'compaction_progress') {
              setProgress({ stage: data.stage, message: data.message });
            } else if (data.type === 'compaction_complete') {
              result = {
                skipped: !!data.skipped,
                reason: data.reason,
                tokensBefore: data.tokens_before,
                tokensAfter: data.tokens_after,
                messagesBefore: data.messages_before,
                messagesAfter: data.messages_after,
              };
              setProgress({ stage: 'complete' });
            } else if (data.type === 'compaction_error') {
              result = { skipped: false, error: data.message };
              setProgress({ stage: 'error', message: data.message });
            }
          } catch {
            // ignore parse errors
          }
        }
      }

      return result;
    } catch (err: any) {
      const msg = err?.message ?? 'Unknown error';
      setProgress({ stage: 'error', message: msg });
      return { skipped: false, error: msg };
    }
  }, []);

  const reset = useCallback(() => setProgress({ stage: 'idle' }), []);

  return { compact, progress, reset };
}
