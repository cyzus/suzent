import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '../types/api';
import {
  ghostRemainder,
  loadCachedSuggestion,
  saveCachedSuggestion,
  suggestionContext,
} from './inputSuggestion';

describe('ghostRemainder', () => {
  it('offers the whole suggestion for an empty input', () => {
    expect(ghostRemainder('', 'Make it shorter')).toBe('Make it shorter');
  });

  it('offers the untyped rest while the input follows the suggestion', () => {
    expect(ghostRemainder('make it', 'Make it shorter')).toBe(' shorter');
  });

  it('treats a typed non-breaking space as a space', () => {
    expect(ghostRemainder('Make ', 'Make it shorter')).toBe('it shorter');
  });

  it('hides once the input drifts away or is complete', () => {
    expect(ghostRemainder('Make it longer', 'Make it shorter')).toBeNull();
    expect(ghostRemainder('Make it shorter', 'Make it shorter')).toBeNull();
    expect(ghostRemainder('', null)).toBeNull();
  });

  it('hides for mentions and multi-line drafts', () => {
    expect(ghostRemainder('@[/a.txt] ', '@[/a.txt] summarise it')).toBeNull();
    expect(ghostRemainder('Make\n', 'Make it shorter')).toBeNull();
  });
});

describe('suggestionContext', () => {
  it('keeps the recent finished user and assistant turns', () => {
    const messages = [
      { role: 'user', content: 'old' },
      ...Array.from({ length: 6 }, (_, i) => ({
        role: i % 2 === 0 ? 'user' : 'assistant',
        content: `m${i}`,
      })),
      { role: 'assistant', content: '   ' },
      { role: 'assistant', content: 'draft', _streaming_draft: true },
    ] as Message[];

    const context = suggestionContext(messages);

    expect(context).toHaveLength(6);
    expect(context[0]).toEqual({ role: 'user', content: 'm0' });
    expect(context[5]).toEqual({ role: 'assistant', content: 'm5' });
  });
});

describe('suggestion cache', () => {
  const turn = [
    { role: 'user', content: 'Write a haiku about rain' },
    { role: 'assistant', content: 'Soft rain on the roof' },
  ] as Message[];

  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => store.set(k, v),
    });
  });

  it('restores the suggestion while its reply is still the last message', () => {
    saveCachedSuggestion('chat-1', turn, 'Now one about snow');

    expect(loadCachedSuggestion('chat-1', turn)).toBe('Now one about snow');
    expect(loadCachedSuggestion('chat-2', turn)).toBeNull();
  });

  it('drops the suggestion once the conversation moves on', () => {
    saveCachedSuggestion('chat-1', turn, 'Now one about snow');

    const later = [...turn, { role: 'user', content: 'Now one about snow' }] as Message[];
    const newReply = [...later, { role: 'assistant', content: 'White hush' }] as Message[];
    expect(loadCachedSuggestion('chat-1', later)).toBeNull();
    expect(loadCachedSuggestion('chat-1', newReply)).toBeNull();
  });

  it('forgets a chat when the model had no prediction', () => {
    saveCachedSuggestion('chat-1', turn, 'Now one about snow');
    saveCachedSuggestion('chat-1', turn, null);

    expect(loadCachedSuggestion('chat-1', turn)).toBeNull();
  });

  it('keeps only the most recent chats', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1);
    for (let i = 0; i < 60; i++) saveCachedSuggestion(`chat-${i}`, turn, `guess ${i}`);
    vi.restoreAllMocks();

    expect(loadCachedSuggestion('chat-59', turn)).toBe('guess 59');
    expect(loadCachedSuggestion('chat-0', turn)).toBeNull();
  });
});
