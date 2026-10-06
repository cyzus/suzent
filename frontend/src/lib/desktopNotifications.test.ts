import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const plugin = vi.hoisted(() => ({
  isPermissionGranted: vi.fn(async () => true),
  requestPermission: vi.fn(async () => 'granted'),
  sendNotification: vi.fn(),
}));
vi.mock('@tauri-apps/plugin-notification', () => plugin);

import {
  notifyIfAway,
  takeAwaitedReply,
  truncateNotificationBody,
  watchForReply,
} from './desktopNotifications';

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
    expect(takeAwaitedReply('chat-1')).toBe(true);
    expect(takeAwaitedReply('chat-1')).toBe(false);
    expect(takeAwaitedReply('chat-2')).toBe(false);
  });

  it('flattens and shortens long bodies', () => {
    const body = truncateNotificationBody(`line one\n\n${'x'.repeat(300)}`);
    expect(body.startsWith('line one x')).toBe(true);
    expect(body).toHaveLength(200);
    expect(body.endsWith('…')).toBe(true);
  });
});
