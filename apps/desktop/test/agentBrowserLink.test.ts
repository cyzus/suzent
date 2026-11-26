import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { AgentBrowserLink, agentUrl, tokenFile, type BrowserHost } from '../src/agentBrowserLink';

class FakeSocket {
  readyState = 1;
  sent: unknown[] = [];
  closed: number | undefined;
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;

  constructor(readonly url: string) {}

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(code?: number): void {
    this.closed = code;
    this.readyState = 3;
    this.onclose?.({});
  }

  receive(value: unknown): void {
    this.onmessage?.({ data: JSON.stringify(value) });
  }
}

const settle = (): Promise<void> => new Promise((resolve) => setImmediate(resolve));

function setup(host: BrowserHost): { link: AgentBrowserLink; sockets: FakeSocket[] } {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-link-'));
  fs.mkdirSync(path.join(dataDir, 'runtime'));
  fs.writeFileSync(tokenFile(dataDir, 4321), 'secret-token\n');
  const sockets: FakeSocket[] = [];
  const link = new AgentBrowserLink({
    dataDir,
    port: () => 4321,
    host,
    retryMs: 60_000,
    connect: (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    },
  });
  return { link, sockets };
}

test('agent pages are limited to the web and a blank page', () => {
  assert.equal(agentUrl('https://example.com/a'), 'https://example.com/a');
  assert.equal(agentUrl('about:blank'), 'about:blank');
  for (const bad of [
    'file:///etc/passwd',
    'suzent://app/index.html',
    'chrome://settings',
    'https://u:p@x.com',
    'javascript:alert(1)',
  ]) {
    assert.throws(() => agentUrl(bad), bad);
  }
});

test('the link authenticates with the token and answers requests in order', async () => {
  const calls: string[] = [];
  let resets = 0;
  const host: BrowserHost = {
    dispatch: async (action) => {
      calls.push(action);
      if (action === 'cdp') throw new Error('x'.repeat(2000));
      return action === 'tabs' ? [] : undefined;
    },
    reset: () => {
      resets += 1;
    },
  };
  const { link, sockets } = setup(host);
  link.start();
  const socket = sockets[0];
  assert.equal(socket.url, 'ws://127.0.0.1:4321/ws/browser-desktop');
  socket.onopen?.({});
  assert.deepEqual(socket.sent, [{ token: 'secret-token' }]);

  socket.receive({ id: 1, action: 'tabs', params: {} });
  await settle();
  assert.deepEqual(calls, [], 'requests before ready are ignored');

  socket.receive({ type: 'ready' });
  assert.equal(link.connected, true);
  socket.receive({ id: 2, action: 'tabs', params: {} });
  socket.receive({ id: 3, action: 'cdp', params: { method: 'Runtime.evaluate' } });
  socket.receive({ id: 4, action: 'status' });
  await settle();
  await settle();
  assert.deepEqual(calls, ['tabs', 'cdp', 'status']);
  const results = socket.sent.slice(1) as Array<Record<string, unknown>>;
  assert.deepEqual(results[0], { type: 'result', id: 2, result: [] });
  assert.equal(results[1].id, 3);
  assert.equal((results[1].error as string).length, 500);
  assert.deepEqual(results[2], { type: 'result', id: 4, result: {} });

  link.emit('Page.frameNavigated', { frame: {} });
  assert.deepEqual(socket.sent.at(-1), {
    type: 'event',
    method: 'Page.frameNavigated',
    params: { frame: {} },
  });

  socket.close();
  assert.equal(link.connected, false);
  assert.equal(resets, 1);
  link.stop();
});

test('the link waits for a token file before dialing', () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agent-link-'));
  let dialed = 0;
  const link = new AgentBrowserLink({
    dataDir,
    port: () => 4321,
    host: { dispatch: async () => ({}), reset: () => undefined },
    retryMs: 60_000,
    connect: () => {
      dialed += 1;
      return new FakeSocket('');
    },
  });
  link.start();
  assert.equal(dialed, 0);
  link.stop();
});
