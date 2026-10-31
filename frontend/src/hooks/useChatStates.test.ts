import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatStates } from '../lib/chatStates';

const api = vi.hoisted(() => ({ fetchChatStates: vi.fn(), setChatResolved: vi.fn() }));

vi.mock('../lib/chatStates', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/chatStates')>()),
  ...api,
}));
vi.mock('./useEventBus', () => ({ subscribeToBusPayloads: () => () => {} }));

import { getChatStates, refreshChatStates, resolveChat } from './useChatStates';

const board: ChatStates = {
  chats: [
    {
      chatId: 'c',
      title: 'Chat',
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
    },
  ],
  counts: { waiting: 1, running: 0, idle: 0, resolved: 0 },
};

describe('resolveChat', () => {
  afterEach(() => {
    api.fetchChatStates.mockReset();
    api.setChatResolved.mockReset();
  });

  it('shows the chat resolved before the save returns', async () => {
    api.fetchChatStates.mockResolvedValue(board);
    await refreshChatStates();
    let finishSave = (): void => {};
    api.setChatResolved.mockReturnValue(new Promise<void>((done) => (finishSave = done)));

    const saving = resolveChat('c', true);
    const shown = getChatStates()!;
    expect(shown.chats[0]).toMatchObject({ state: 'resolved', waitingKind: null });
    expect(shown.counts).toEqual({ waiting: 0, running: 0, idle: 0, resolved: 1 });

    finishSave();
    await saving;
    expect(api.setChatResolved).toHaveBeenCalledWith('c', true);
  });

  it('ignores a refresh that was in flight before the change', async () => {
    api.fetchChatStates.mockResolvedValue(board);
    await refreshChatStates();
    let answerStale = (_: ChatStates): void => {};
    api.fetchChatStates.mockReturnValueOnce(
      new Promise<ChatStates>((done) => (answerStale = done))
    );
    const stale = refreshChatStates();
    api.setChatResolved.mockResolvedValue(undefined);
    api.fetchChatStates.mockReturnValue(new Promise<ChatStates>(() => {}));

    await resolveChat('c', true);
    answerStale(board);
    await stale;
    expect(getChatStates()!.chats[0].state).toBe('resolved');
  });

  it('puts the row back when the save fails', async () => {
    api.fetchChatStates.mockResolvedValue(board);
    await refreshChatStates();
    api.setChatResolved.mockRejectedValue(new Error('offline'));
    api.fetchChatStates.mockReturnValue(new Promise<ChatStates>(() => {}));

    await expect(resolveChat('c', true)).rejects.toThrow('offline');
    expect(getChatStates()!.chats[0].state).toBe('waiting');
  });
});
