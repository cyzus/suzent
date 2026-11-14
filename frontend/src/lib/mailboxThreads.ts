import type { MailboxItem } from './api';

/** Thread identity belongs to the backend; old servers remain ungrouped. */
export function groupMailboxItems(items: MailboxItem[]): Map<string, MailboxItem[]> {
  const groups = new Map<string, MailboxItem[]>();
  const seen = new Set<number>();
  for (const item of [...items].sort((a, b) => b.id - a.id)) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    const key = item.presentation?.threadKey || `item:${item.id}`;
    const group = groups.get(key);
    if (group) group.push(item);
    else groups.set(key, [item]);
  }
  return groups;
}
