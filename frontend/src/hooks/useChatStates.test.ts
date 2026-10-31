import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatStateRow, ChatStates } from '../lib/chatStates';

const api = vi.hoisted(() => ({ fetchChatStates: vi.fn(), setChatResolved: vi.fn() }));

vi.mock('../lib/chatStates', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/chatStates')>()),
  ...api,
}));
vi.mock('./useEventBus', () => ({ subscribeToBusPayloads: () => () => {} }));

import { getChatStates, refreshChatStates, resolveChat } from './useChatStates';

const waiting = (chatId: string): ChatStateRow => ({
  chatId,
  title: chatId,
  projectId: 'p',
  projectName: 'Project',
  state: 'waiting',
  waitingKind: 'reply',
  waitingReason: 'Pick an option',
  summary: null,
  lastActiveAt: null,
  resolvedAt: null,
  openTasks: 0,
  doneTasks: 0,
});
const board: ChatStates = {
  chats: [waiting('a'), waiting('b')],
  counts: { waiting: 2, running: 0, idle: 0, resolved: 0 },
};
const stateOf = (chatId: string): string | undefined =>
  getChatStates()?.chats.find((row) => row.chatId === chatId)?.state;

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (v: T) => void;
  reject: (e: Error) => void;
} {
  let resolve = (_: T): void => {};
  let reject = (_: Error): void => {};
  const promise = new Promise<T>((ok, fail) => {
    resolve = ok;
    reject = fail;
  });
  return { promise, resolve, reject };
}

describe('resolveChat', () => {
  afterEach(() => {
    api.fetchChatStates.mockReset();
    api.setChatResolved.mockReset();
  });

  it('shows the chat resolved before the save returns', async () => {
    api.fetchChatStates.mockResolvedValue(board);
    await refreshChatStates();
    const save = deferred<void>();
    api.setChatResolved.mockReturnValue(save.promise);

    const saving = resolveChat('a', true);
    expect(stateOf('a')).toBe('resolved');
    expect(getChatStates()!.counts).toEqual({ waiting: 1, running: 0, idle: 0, resolved: 1 });

    save.resolve();
    await saving;
    expect(api.setChatResolved).toHaveBeenCalledWith('a', true);
  });

  it('keeps showing the click when a refresh lands during the save', async () => {
    api.fetchChatStates.mockResolvedValue(board);
    await refreshChatStates();
    const save = deferred<void>();
    api.setChatResolved.mockReturnValue(save.promise);

    const saving = resolveChat('a', true);
    // A poll that read the server before the save finished.
    await refreshChatStates();
    expect(stateOf('a')).toBe('resolved');

    const resolvedBoard: ChatStates = {
      chats: [{ ...waiting('a'), state: 'resolved', waitingKind: null }, waiting('b')],
      counts: { waiting: 1, running: 0, idle: 0, resolved: 1 },
    };
    api.fetchChatStates.mockResolvedValue(resolvedBoard);
    save.resolve();
    await saving;
    // Settled: the next refresh shows the server's row as it is.
    api.fetchChatStates.mockResolvedValue(board);
    await refreshChatStates();
    expect(stateOf('a')).toBe('waiting');
  });

  it("puts back only the failed chat's row", async () => {
    api.fetchChatStates.mockResolvedValue(board);
    await refreshChatStates();
    const saveA = deferred<void>();
    const saveB = deferred<void>();
    api.setChatResolved.mockImplementation((chatId: string) =>
      chatId === 'a' ? saveA.promise : saveB.promise
    );
    api.fetchChatStates.mockReturnValue(new Promise<ChatStates>(() => {}));

    const resolvingA = resolveChat('a', true);
    const resolvingB = resolveChat('b', true);
    saveA.reject(new Error('offline'));
    await expect(resolvingA).rejects.toThrow('offline');

    expect(stateOf('a')).toBe('waiting');
    expect(stateOf('b')).toBe('resolved');
    expect(getChatStates()!.counts).toEqual({ waiting: 1, running: 0, idle: 0, resolved: 1 });
    void resolvingB;
  });
});
