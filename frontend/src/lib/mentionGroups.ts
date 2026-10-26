export const MENTION_CATEGORIES = ['all', 'file', 'directory', 'chat'] as const;
export type MentionCategory = (typeof MENTION_CATEGORIES)[number];

/** Keep the overview small, with filesystem matches ahead of recent chats. */
export function groupMentionSuggestions<T extends { type?: 'file' | 'directory' | 'chat' }>(
  items: T[],
  category: MentionCategory
): { category: Exclude<MentionCategory, 'all'>; items: T[] }[] {
  return (['file', 'directory', 'chat'] as const)
    .filter((kind) => category === 'all' || category === kind)
    .map((kind) => ({
      category: kind,
      items: items
        .filter((item) => (item.type || 'file') === kind)
        .slice(0, category === 'all' ? 3 : 30),
    }))
    .filter((group) => group.items.length > 0);
}
