import { describe, expect, it } from 'vitest';
import { groupMentionSuggestions } from './mentionGroups';

describe('mention categories', () => {
  const chats = Array.from({ length: 30 }, (_, id) => ({ type: 'chat' as const, id }));
  const files = [
    { type: 'file' as const, id: 40 },
    { type: 'directory' as const, id: 41 },
  ];

  it('caps chats in the overview and keeps file categories first', () => {
    const groups = groupMentionSuggestions([...chats, ...files], 'all');
    expect(groups.map((group) => group.category)).toEqual(['file', 'directory', 'chat']);
    expect(groups[2].items).toHaveLength(3);
    expect(groups.flatMap((group) => group.items)).toHaveLength(5);
  });

  it('shows all fetched chats only in their own category', () => {
    const groups = groupMentionSuggestions([...chats, ...files], 'chat');
    expect(groups).toHaveLength(1);
    expect(groups[0].items).toEqual(chats);
  });

  it('treats untyped file results as files and omits empty groups', () => {
    expect(groupMentionSuggestions([{ id: 1, type: undefined }], 'file')[0].items).toHaveLength(1);
    expect(groupMentionSuggestions(files, 'chat')).toEqual([]);
  });
});
