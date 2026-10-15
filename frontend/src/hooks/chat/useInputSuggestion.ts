import { useEffect, useRef, useState } from 'react';
import type { Message } from '../../types/api';
import {
  fetchInputSuggestion,
  isInputSuggestionEnabled,
  loadCachedSuggestion,
  onInputSuggestionEnabledChange,
  saveCachedSuggestion,
  suggestionContext,
} from '../../lib/inputSuggestion';

// The finished turn's messages keep settling for a moment after its stream
// ends (final reload, reconciled tool rows); wait for them to go quiet.
const SETTLE_MS = 600;

interface UseInputSuggestionOptions {
  chatId: string | null;
  messages: Message[];
  streaming: boolean;
}

/**
 * Predicts the user's next message once the agent finishes a turn.
 *
 * Only a turn ending in this view asks for one: opening an old chat does not
 * spend a model call on a conversation the user may only be reading. Each
 * prediction is saved on this device, so reopening the chat or restarting the
 * app shows it again while its reply is still the last message.
 */
export function useInputSuggestion({
  chatId,
  messages,
  streaming,
}: UseInputSuggestionOptions): string | null {
  const [enabled, setEnabled] = useState(isInputSuggestionEnabled);
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const wasStreamingRef = useRef(streaming);

  useEffect(() => onInputSuggestionEnabledChange(setEnabled), []);

  useEffect(() => {
    setSuggestion(null);
    setPending(false);
    wasStreamingRef.current = false;
  }, [chatId]);

  useEffect(() => {
    if (streaming) {
      setSuggestion(null);
      setPending(false);
    } else if (wasStreamingRef.current) {
      setPending(true);
    }
    wasStreamingRef.current = streaming;
  }, [streaming]);

  useEffect(() => {
    if (!enabled) setSuggestion(null);
  }, [enabled]);

  useEffect(() => {
    if (!chatId || !enabled || streaming || pending || suggestion) return;
    const cached = loadCachedSuggestion(chatId, messages);
    if (cached) setSuggestion(cached);
  }, [chatId, enabled, streaming, pending, suggestion, messages]);

  useEffect(() => {
    if (!pending || !enabled || streaming) return;
    const context = suggestionContext(messages);
    if (context.length === 0 || context[context.length - 1].role !== 'assistant') return;

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const next = await fetchInputSuggestion(context, controller.signal);
        if (!controller.signal.aborted) {
          if (chatId) saveCachedSuggestion(chatId, messages, next);
          setSuggestion(next);
          setPending(false);
        }
      } catch {
        if (!controller.signal.aborted) setPending(false);
      }
    }, SETTLE_MS);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [chatId, pending, enabled, streaming, messages]);

  return enabled ? suggestion : null;
}
