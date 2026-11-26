/**
 * The connection from the app to the backend's browser tool. The app dials
 * `/ws/browser-desktop` on loopback and proves it runs as the same user by
 * sending the token the backend wrote to its runtime folder, then answers the
 * backend's browser requests one at a time.
 */

import fs from 'node:fs';
import path from 'node:path';

/** DevTools methods the backend may send; everything else is refused. */
export const CDP_METHODS = new Set([
  'Page.enable',
  'Page.getFrameTree',
  'Page.createIsolatedWorld',
  'Page.startScreencast',
  'Page.stopScreencast',
  'Page.screencastFrameAck',
  'Page.reload',
  'Page.getNavigationHistory',
  'Page.navigateToHistoryEntry',
  'Runtime.evaluate',
  'Input.dispatchMouseEvent',
  'Input.dispatchKeyEvent',
  'Input.insertText',
]);

/** The pages the agent may open: the web and a blank page, nothing local. */
export function agentUrl(value: unknown): string {
  if (value === 'about:blank') return value;
  if (typeof value !== 'string') throw new Error('Only web pages can be opened.');
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('Only web pages can be opened.');
  }
  return url.href;
}

export function isAgentUrl(value: string): boolean {
  try {
    agentUrl(value);
    return true;
  } catch {
    return false;
  }
}

export function tokenFile(dataDir: string, port: number): string {
  return path.join(dataDir, 'runtime', `desktop-browser-${port}.token`);
}

export interface BrowserHost {
  dispatch(action: string, params: Record<string, unknown>): Promise<unknown>;
  /** Called when the backend goes away: stop work the backend asked for. */
  reset(): void;
}

interface SocketLike {
  readyState: number;
  send(data: string): void;
  close(code?: number): void;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
}

export interface LinkOptions {
  dataDir: string;
  port: () => number | null;
  host: BrowserHost;
  connect?: (url: string) => SocketLike;
  retryMs?: number;
  log?: (message: string) => void;
}

const OPEN = 1;
const MAX_ERROR = 500;

export class AgentBrowserLink {
  private socket: SocketLike | null = null;
  private ready = false;
  private queue: Promise<void> = Promise.resolve();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private stopped = false;

  constructor(private readonly options: LinkOptions) {}

  get connected(): boolean {
    return this.ready;
  }

  start(): void {
    this.stopped = false;
    this.attempt();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.socket?.close(1000);
    this.dropped();
  }

  /** Dial again now, e.g. after the backend restarted on a new port. */
  reconnect(): void {
    this.socket?.close(1000);
    this.dropped();
    this.attempt();
  }

  /** Forwards a DevTools event of the controlled page to the backend. */
  emit(method: string, params: unknown): void {
    if (this.ready && this.socket?.readyState === OPEN) {
      this.socket.send(JSON.stringify({ type: 'event', method, params }));
    }
  }

  private schedule(): void {
    if (this.stopped || this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.attempt();
    }, this.options.retryMs ?? 2000);
  }

  private attempt(): void {
    if (this.stopped || this.socket) return;
    const port = this.options.port();
    if (!port) return this.schedule();
    let token: string;
    try {
      token = fs.readFileSync(tokenFile(this.options.dataDir, port), 'utf8').trim();
    } catch {
      // An older backend without the built-in browser, or not started yet.
      return this.schedule();
    }
    const connect = this.options.connect ?? ((url: string) => new WebSocket(url) as SocketLike);
    const socket = connect(`ws://127.0.0.1:${port}/ws/browser-desktop`);
    this.socket = socket;
    socket.onopen = () => socket.send(JSON.stringify({ token }));
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.dropped();
      this.schedule();
    };
    socket.onmessage = ({ data }) => {
      if (this.socket !== socket) return;
      let message: { type?: string; id?: unknown; action?: unknown; params?: unknown };
      try {
        message = JSON.parse(String(data));
      } catch {
        return;
      }
      if (!this.ready) {
        if (message.type === 'ready') {
          this.ready = true;
          this.options.log?.('Built-in browser connected to the backend');
          this.heartbeat = setInterval(() => {
            if (socket.readyState === OPEN) socket.send(JSON.stringify({ type: 'ping' }));
          }, 20_000);
        }
        return;
      }
      const id = message.id;
      if (!Number.isInteger(id) || typeof message.action !== 'string') return;
      const action = message.action;
      const params =
        message.params && typeof message.params === 'object'
          ? (message.params as Record<string, unknown>)
          : {};
      this.queue = this.queue.then(async () => {
        if (this.socket !== socket || socket.readyState !== OPEN) return;
        let reply: Record<string, unknown>;
        try {
          reply = {
            type: 'result',
            id,
            result: (await this.options.host.dispatch(action, params)) ?? {},
          };
        } catch (error) {
          const text = error instanceof Error ? error.message : String(error);
          reply = {
            type: 'result',
            id,
            error: text.slice(0, MAX_ERROR) || 'Browser action failed.',
          };
        }
        if (this.socket === socket && socket.readyState === OPEN)
          socket.send(JSON.stringify(reply));
      });
    };
  }

  private dropped(): void {
    const wasReady = this.ready;
    this.socket = null;
    this.ready = false;
    this.queue = Promise.resolve();
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = null;
    if (wasReady) this.options.host.reset();
  }
}
