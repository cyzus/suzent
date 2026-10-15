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
});
