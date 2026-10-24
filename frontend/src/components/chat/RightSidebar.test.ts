import { describe, expect, it } from 'vitest';
import { evaluateSidebarAutoOpen, type AutoOpenFlags } from './RightSidebar';

const baseFlags = (overrides: Partial<AutoOpenFlags> = {}): AutoOpenFlags => ({
  chatId: 'chat-a',
  file: false,
  fileToPreview: null,
  canvas: false,
  canvasResolved: true,
  subAgent: false,
  viewingSubAgentTaskId: null,
  webContext: false,
  forcedWebContextId: null,
  goal: false,
  goalResolved: true,
  ...overrides,
});

describe('evaluateSidebarAutoOpen', () => {
  it('closes the Canvas pane when its surface moves back into chat, only once', () => {
    const before = baseFlags({
      activeTab: 'canvas',
      canvasSurfaceId: 'a',
      canvasLocation: 'canvas',
    });
    const after = { ...before, canvasLocation: 'inline' as const };
    expect(evaluateSidebarAutoOpen(before, after).shouldClose).toBe(true);
    expect(evaluateSidebarAutoOpen(after, after).shouldClose).toBeUndefined();
    expect(evaluateSidebarAutoOpen(after, before).shouldClose).toBeUndefined();
  });

  it('does not close other tabs or mistake surface/chat switches for a move', () => {
    const before = baseFlags({
      activeTab: 'canvas',
      canvasSurfaceId: 'a',
      canvasLocation: 'canvas',
    });
    const after = { ...before, canvasLocation: 'inline' as const };
    for (const flags of [
      { ...after, activeTab: 'files' as const },
      { ...after, canvasSurfaceId: 'b' },
      { ...after, chatId: 'chat-b' },
      { ...after, canvasResolved: false },
      { ...after, file: true, fileToPreview: { path: '/a', name: 'a' } },
    ]) {
      expect(evaluateSidebarAutoOpen(before, flags).shouldClose).toBeUndefined();
    }
  });

  it('does not switch tabs or open when switching from New Chat (null) to a chat with tasks', () => {
    // 1. User is on New Chat (chatId: null); goalChatId is null so goalResolved is true, goal is false
    const onNewChat = baseFlags({
      chatId: null,
      goal: false,
      goalResolved: true,
    });

    // 2. Render 1 after clicking Chat B: chatId is 'chat-b', but fetch hasn't landed yet
    // (goalChatId is still null, so goalResolved is false)
    const switchRender1 = baseFlags({
      chatId: 'chat-b',
      goal: false,
      goalResolved: false,
    });
    expect(evaluateSidebarAutoOpen(onNewChat, switchRender1)).toEqual({
      nextTab: null,
      shouldOpen: false,
    });

    // 3. Render 2 when fetch for Chat B lands with existing tasks:
    // goalResolved transitions false -> true and goal is true.
    // Must NOT treat this initial load as a same-chat rise!
    const switchRender2 = baseFlags({
      chatId: 'chat-b',
      goal: true,
      goalResolved: true,
    });
    expect(evaluateSidebarAutoOpen(switchRender1, switchRender2)).toEqual({
      nextTab: null,
      shouldOpen: false,
    });
  });

  it('does not switch tabs when switching between two existing chats where target has tasks or canvas', () => {
    const onChatA = baseFlags({
      chatId: 'chat-a',
      canvas: false,
      canvasResolved: true,
      goal: false,
      goalResolved: true,
    });

    // Render 1 on switch to Chat B: async state not yet resolved for Chat B
    const chatBUnresolved = baseFlags({
      chatId: 'chat-b',
      canvas: false,
      canvasResolved: false,
      goal: false,
      goalResolved: false,
    });
    expect(evaluateSidebarAutoOpen(onChatA, chatBUnresolved)).toEqual({
      nextTab: null,
      shouldOpen: false,
    });

    // Render 2 on Chat B: canvas and goal resolve with existing content
    const chatBResolved = baseFlags({
      chatId: 'chat-b',
      canvas: true,
      canvasResolved: true,
      goal: true,
      goalResolved: true,
    });
    expect(evaluateSidebarAutoOpen(chatBUnresolved, chatBResolved)).toEqual({
      nextTab: null,
      shouldOpen: false,
    });
  });

  it('auto-switches to plan when tasks genuinely rise within an already-resolved chat', () => {
    const beforeTask = baseFlags({
      chatId: 'chat-b',
      goal: false,
      goalResolved: true,
    });
    const afterTaskCreated = baseFlags({
      chatId: 'chat-b',
      goal: true,
      goalResolved: true,
    });
    expect(evaluateSidebarAutoOpen(beforeTask, afterTaskCreated)).toEqual({
      nextTab: 'plan',
      shouldOpen: true,
    });
  });

  it('auto-switches to canvas when a surface genuinely rises within an already-resolved chat', () => {
    const beforeCanvas = baseFlags({
      chatId: 'chat-b',
      canvas: false,
      canvasResolved: true,
    });
    const afterCanvasCreated = baseFlags({
      chatId: 'chat-b',
      canvas: true,
      canvasResolved: true,
    });
    expect(evaluateSidebarAutoOpen(beforeCanvas, afterCanvasCreated)).toEqual({
      nextTab: 'canvas',
      shouldOpen: true,
    });
  });

  it('auto-switches to files, agents, or browser when explicitly clicked within the same chat', () => {
    const prev = baseFlags({ chatId: 'chat-b' });
    const fileClicked = baseFlags({
      chatId: 'chat-b',
      file: true,
      fileToPreview: { path: '/workspace/a.txt', name: 'a.txt', nonce: 1 },
    });
    expect(evaluateSidebarAutoOpen(prev, fileClicked)).toEqual({
      nextTab: 'files',
      shouldOpen: true,
    });

    const agentClicked = baseFlags({
      chatId: 'chat-b',
      subAgent: true,
      viewingSubAgentTaskId: 'task-123',
    });
    expect(evaluateSidebarAutoOpen(prev, agentClicked)).toEqual({
      nextTab: 'agents',
      shouldOpen: true,
    });

    const webClicked = baseFlags({
      chatId: 'chat-b',
      webContext: true,
      forcedWebContextId: 'web-ctx-1',
    });
    expect(evaluateSidebarAutoOpen(prev, webClicked)).toEqual({
      nextTab: 'browser',
      shouldOpen: true,
    });
  });

  it('switches to the canvas each time a chat surface is popped out', () => {
    const prev = baseFlags({ canvas: true, canvasRequestNonce: 1 });
    expect(evaluateSidebarAutoOpen(prev, { ...prev, canvasRequestNonce: 2 })).toEqual({
      nextTab: 'canvas',
      shouldOpen: true,
    });
    expect(evaluateSidebarAutoOpen(prev, prev)).toEqual({ nextTab: null, shouldOpen: false });
  });
});

describe('Focal Agent session board', () => {
  it('opens the board when arriving on the Focal chat with room for it', () => {
    expect(
      evaluateSidebarAutoOpen(
        baseFlags({ chatId: 'chat-a' }),
        baseFlags({ chatId: 'focal-suzent', focalBoard: 'open' })
      )
    ).toEqual({ nextTab: 'plan', shouldOpen: true });
  });

  it('closes the board on arrival when the user closed it there last time', () => {
    expect(
      evaluateSidebarAutoOpen(
        baseFlags({ chatId: 'chat-a' }),
        baseFlags({ chatId: 'focal-suzent', focalBoard: 'closed' })
      )
    ).toEqual({ nextTab: null, shouldOpen: false, shouldClose: true });
  });

  it('leaves the sidebar alone on narrow screens and once already on the Focal chat', () => {
    expect(
      evaluateSidebarAutoOpen(
        baseFlags({ chatId: 'chat-a' }),
        baseFlags({ chatId: 'focal-suzent' })
      )
    ).toEqual({ nextTab: null, shouldOpen: false });
    expect(
      evaluateSidebarAutoOpen(
        baseFlags({ chatId: 'focal-suzent', focalBoard: 'open' }),
        baseFlags({ chatId: 'focal-suzent', focalBoard: 'open' })
      )
    ).toEqual({ nextTab: null, shouldOpen: false });
  });
});
