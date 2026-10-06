import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const plugin = vi.hoisted(() => ({
  isPermissionGranted: vi.fn(async () => true),
  requestPermission: vi.fn(async () => 'granted'),
  sendNotification: vi.fn(),
}));
vi.mock('@tauri-apps/plugin-notification', () => plugin);

import {
  forgetReply,
  notifyIfAway,
  recordReplyChunk,
  takeReplyOutcome,
  truncateNotificationBody,
  watchForReply,
} from './desktopNotifications';

const frame = (data: object): string => `data: ${JSON.stringify(data)}\n\n`;

function setFocus(focused: boolean): void {
  vi.stubGlobal('document', { visibilityState: 'visible', hasFocus: () => focused });
}

describe('desktop notifications', () => {
  beforeEach(() => {
    plugin.sendNotification.mockClear();
    vi.stubGlobal('window', { __TAURI__: {} });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('notifies when the window has lost focus', async () => {
    setFocus(false);
    await notifyIfAway('Daily report', 'All systems operational');
    expect(plugin.sendNotification).toHaveBeenCalledWith({
      title: 'Daily report',
      body: 'All systems operational',
    });
  });

  it('stays quiet while the user is looking at Suzent', async () => {
    setFocus(true);
    await notifyIfAway('Daily report', 'done');
    expect(plugin.sendNotification).not.toHaveBeenCalled();
  });

  it('never calls the Tauri plugin in web mode', async () => {
    vi.stubGlobal('window', {});
    setFocus(false);
    await notifyIfAway('Daily report', 'done');
    expect(plugin.sendNotification).not.toHaveBeenCalled();
  });

  it('announces each watched reply once', () => {
    watchForReply('chat-1');
    expect(takeReplyOutcome('chat-1')).toBe('ready');
    expect(takeReplyOutcome('chat-1')).toBeNull();
    expect(takeReplyOutcome('chat-2')).toBeNull();
  });

  it('ignores chunks from chats nobody is waiting on', () => {
    recordReplyChunk('chat-1', frame({ type: 'RUN_ERROR', message: 'boom' }));
    expect(takeReplyOutcome('chat-1')).toBeNull();
  });

  it('tells a failed turn from a finished one', () => {
    watchForReply('chat-1');
    recordReplyChunk('chat-1', frame({ type: 'RUN_ERROR', message: 'boom' }));
    expect(takeReplyOutcome('chat-1')).toBe('failed');
  });

  it('stays quiet about a turn the user stopped', () => {
    watchForReply('chat-1');
    recordReplyChunk('chat-1', frame({ type: 'RUN_ERROR', code: 'stream_stopped' }));
    expect(takeReplyOutcome('chat-1')).toBe('stopped');
  });

  it('reports a turn paused on an unanswered approval', () => {
    const request = (id: string) =>
      frame({ type: 'CUSTOM', name: 'tool_approval_request', value: { toolCallId: id } });
    watchForReply('chat-1');
    recordReplyChunk('chat-1', request('t1') + request('t2'));
    recordReplyChunk(
      'chat-1',
      frame({ type: 'CUSTOM', name: 'tool_approval_result', value: { toolCallId: 't1' } })
    );
    expect(takeReplyOutcome('chat-1')).toBe('approval');
  });

  it('drops a watch whose turn never started', () => {
    watchForReply('chat-1');
    forgetReply('chat-1');
    expect(takeReplyOutcome('chat-1')).toBeNull();
  });

  it('flattens and shortens long bodies', () => {
    const body = truncateNotificationBody(`line one\n\n${'x'.repeat(300)}`);
    expect(body.startsWith('line one x')).toBe(true);
    expect(body).toHaveLength(200);
    expect(body.endsWith('…')).toBe(true);
  });
});
