import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { ghostRemainder, replyKey, suggestionContext } from './inputSuggestion';

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

describe('replyKey', () => {
  const turn = [
    { role: 'user', content: 'Write a haiku about rain' },
    { role: 'assistant', content: 'Soft rain on the roof' },
  ] as Message[];

  it('stays the same while the reply is still the last message', () => {
    const reloaded = turn.map((m) => ({ ...m })) as Message[];
    expect(replyKey(turn)).not.toBeNull();
    expect(replyKey(reloaded)).toBe(replyKey(turn));
  });

  it('changes once the conversation moves on', () => {
    const later = [...turn, { role: 'user', content: 'Now one about snow' }] as Message[];
    const newReply = [...later, { role: 'assistant', content: 'White hush' }] as Message[];
    expect(replyKey(later)).toBeNull();
    expect(replyKey(newReply)).not.toBe(replyKey(turn));
  });
});
