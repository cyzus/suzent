import { describe, expect, it } from 'vitest';
import { groupMailboxItems } from './mailboxThreads';
import type { MailboxItem } from './api';
import fixtures from '../../../packages/mobile-contract/mailbox-thread-fixtures.json';

describe('server-owned mailbox threads', () => {
  it('groups only by the backend key regardless of webhook format', () => {
    const items = fixtures.map(
      (fixture, index) => ({ id: index + 1, presentation: fixture.presentation }) as MailboxItem
    );
    const groups = groupMailboxItems([...items, items[0]]);
    expect(groups.get(fixtures[0].presentation.threadKey)?.map((item) => item.id)).toEqual([2, 1]);
    expect(groups.get(fixtures[7].presentation.threadKey)?.map((item) => item.id)).toEqual([9, 8]);
    expect([...groups.values()].flat()).toHaveLength(items.length);
  });
  it('does not guess identities for old servers', () => {
    const items = [1, 2].map(
      (id) => ({ id, signature: 'same', source_name: 'github' }) as MailboxItem
    );
    expect(groupMailboxItems(items).size).toBe(2);
  });
});
