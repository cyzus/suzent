/**
 * The agent's browser: real Chromium pages inside the app window, driven by
 * the backend's browser tool through the DevTools protocol of each page's
 * `webContents.debugger`. Nothing listens on a debugging port.
 *
 * The pages run in their own session, apart from the app and from the
 * sidebar's web pages, with no preload and no permissions. While the browser
 * panel is closed they keep working out of sight; the panel shows the
 * controlled page, where the user can watch and use it.
 */

import { WebContentsView, session, type BrowserWindow, type Rectangle } from 'electron';

import { CDP_METHODS, agentUrl, isAgentUrl, type BrowserHost } from './agentBrowserLink';
import { sanitizeBounds } from './embeddedPages';

export const AGENT_PARTITION = 'persist:suzent-agent-browser';

const OUT_OF_VIEW: Rectangle = { x: 0, y: 0, width: 1, height: 1 };
const DESKTOP_METRICS = { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false };
const MAX_TABS = 20;
const LOAD_TIMEOUT_MS = 15_000;
const FRAME_INTERVAL_MS = 100;

type Emit = (method: string, params: unknown) => void;

interface Tab {
  id: number;
  view: WebContentsView;
  shown: boolean | null;
}

function lockDown(): void {
  const agentSession = session.fromPartition(AGENT_PARTITION);
  agentSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  agentSession.setPermissionCheckHandler(() => false);
  agentSession.on('will-download', (event) => event.preventDefault());
}

export class AgentBrowser implements BrowserHost {
  private readonly tabs = new Map<number, Tab>();
  private nextId = 0;
  private selected: number | undefined;
  private shown: Rectangle | null = null;
  private pendingFrame: unknown = null;
  private frameTimer: ReturnType<typeof setTimeout> | null = null;
  emit: Emit = () => undefined;

  constructor(
    private readonly window: BrowserWindow,
    private readonly focus: () => void
  ) {
    lockDown();
    window.on('closed', () => this.tabs.clear());
  }

  /** Lays the controlled page over the browser panel. */
  show(bounds: Partial<Rectangle> | undefined): boolean {
    this.shown = sanitizeBounds(bounds);
    this.layout();
    return this.selected !== undefined;
  }

  hide(): void {
    this.shown = null;
    this.layout();
  }

  reset(): void {
    this.selected = undefined;
    this.pendingFrame = null;
    this.layout();
  }

  async dispatch(action: string, params: Record<string, unknown>): Promise<unknown> {
    switch (action) {
      case 'status': {
        const tab = this.current();
        return {
          title: tab ? tab.view.webContents.getTitle().slice(0, 200) : null,
          selected: tab !== undefined,
          browser: 'Suzent',
        };
      }
      case 'focus':
        if (!this.current()) throw new Error('Open a page first.');
        this.focus();
        return {};
      case 'tabs':
        return [...this.tabs.values()].map(({ id, view }) => ({
          id: `tab-${id}`,
          title: view.webContents.getTitle().slice(0, 200),
          url: view.webContents.getURL(),
          selected: id === this.selected,
          active: id === this.selected,
          focused: id === this.selected && this.shown !== null,
        }));
      case 'select': {
        const id = typeof params.id === 'string' ? /^tab-(\d+)$/.exec(params.id) : null;
        const tab = id ? this.tabs.get(Number(id[1])) : undefined;
        if (!tab) throw new Error('List tabs and select a valid tab.');
        await this.select(tab);
        return { id: `tab-${tab.id}`, url: tab.view.webContents.getURL() };
      }
      case 'open': {
        const url = agentUrl(params.url);
        const tab = this.current() ?? this.create();
        // DevTools commands to a page that never loaded wait for its first load.
        await this.load(tab, url);
        await this.select(tab);
        return { id: `tab-${tab.id}`, url };
      }
      case 'cdp': {
        const tab = this.current();
        if (!tab) throw new Error('Select a tab or open a page first.');
        const method = String(params.method);
        if (!CDP_METHODS.has(method)) throw new Error('Unsupported browser command.');
        const commandParams =
          params.params && typeof params.params === 'object'
            ? (params.params as Record<string, unknown>)
            : {};
        const result = await tab.view.webContents.debugger.sendCommand(method, commandParams);
        if (method === 'Page.reload' || method === 'Page.navigateToHistoryEntry') {
          await this.settle(tab);
        }
        return result;
      }
      case 'detach':
        this.reset();
        return {};
      default:
        throw new Error('Unsupported browser command.');
    }
  }

  destroy(): void {
    for (const tab of [...this.tabs.values()]) this.closeTab(tab);
  }

  private current(): Tab | undefined {
    return this.selected === undefined ? undefined : this.tabs.get(this.selected);
  }

  private create(url?: string): Tab {
    if (this.tabs.size >= MAX_TABS) throw new Error('Too many browser tabs are open.');
    const view = new WebContentsView({
      webPreferences: {
        partition: AGENT_PARTITION,
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
        backgroundThrottling: false,
        spellcheck: false,
      },
    });
    const tab: Tab = { id: ++this.nextId, view, shown: null };
    const contents = view.webContents;
    view.setBackgroundColor('#ffffff');
    const guard = (event: Electron.Event, target: string): void => {
      if (!isAgentUrl(target)) event.preventDefault();
    };
    contents.on('will-navigate', guard);
    contents.on('will-redirect', guard);
    // Links that open a new window become another tab the agent can list.
    contents.setWindowOpenHandler(({ url: target }) => {
      if (isAgentUrl(target) && this.tabs.size < MAX_TABS) {
        void this.load(this.create(), target).catch(() => undefined);
      }
      return { action: 'deny' };
    });
    contents.on('destroyed', () => this.forget(tab));
    contents.debugger.attach('1.3');
    contents.debugger.on('message', (_event, method, params) =>
      this.onDevTools(tab, method, params)
    );
    contents.debugger.on('detach', () => {
      if (this.selected === tab.id) {
        this.selected = undefined;
        this.emit('detached', {});
      }
    });
    this.tabs.set(tab.id, tab);
    this.window.contentView.addChildView(view);
    this.layout();
    if (url) void contents.loadURL(url).catch(() => undefined);
    return tab;
  }

  private async select(tab: Tab): Promise<void> {
    if (this.selected !== tab.id) {
      this.selected = tab.id;
      this.pendingFrame = null;
      this.layout();
    }
    await tab.view.webContents.debugger.sendCommand('Page.enable');
  }

  private async load(tab: Tab, url: string): Promise<void> {
    // A redirect or a newer navigation aborts this one; that page still loads.
    const loading = tab.view.webContents.loadURL(url).catch((error: { code?: string }) => {
      if (error?.code !== 'ERR_ABORTED') {
        throw new Error(`Could not open the page (${error?.code ?? 'load failed'}).`);
      }
    });
    await Promise.race([loading, new Promise((resolve) => setTimeout(resolve, LOAD_TIMEOUT_MS))]);
  }

  private async settle(tab: Tab): Promise<void> {
    const deadline = Date.now() + LOAD_TIMEOUT_MS;
    while (!tab.view.webContents.isDestroyed() && tab.view.webContents.isLoading()) {
      if (Date.now() > deadline) throw new Error('Page is still loading.');
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }

  private onDevTools(tab: Tab, method: string, params: unknown): void {
    if (tab.id !== this.selected) return;
    if (method === 'Page.screencastFrame') {
      // Acknowledged here so a slow preview never holds up agent commands.
      const sessionId = (params as { sessionId?: number }).sessionId;
      void tab.view.webContents.debugger
        .sendCommand('Page.screencastFrameAck', { sessionId })
        .catch(() => undefined);
      this.pendingFrame = params;
      if (!this.frameTimer) {
        this.frameTimer = setTimeout(() => {
          this.frameTimer = null;
          if (this.pendingFrame) this.emit('Page.screencastFrame', this.pendingFrame);
          this.pendingFrame = null;
        }, FRAME_INTERVAL_MS);
      }
      return;
    }
    if (method === 'Page.frameNavigated') this.emit(method, params);
  }

  /**
   * Chromium drops input to hidden pages and stops painting them, and the
   * agent must keep working while the panel is closed. So a page out of view
   * stays shown in one pixel of the window, laid out at a desktop size.
   */
  private layout(): void {
    for (const tab of this.tabs.values()) {
      const shown = this.shown !== null && tab.id === this.selected;
      tab.view.setBounds(shown && this.shown ? this.shown : OUT_OF_VIEW);
      if (tab.shown === shown) continue;
      tab.shown = shown;
      const devtools = tab.view.webContents.debugger;
      void (
        shown
          ? devtools.sendCommand('Emulation.clearDeviceMetricsOverride')
          : devtools.sendCommand('Emulation.setDeviceMetricsOverride', DESKTOP_METRICS)
      ).catch(() => undefined);
    }
  }

  private closeTab(tab: Tab): void {
    this.forget(tab);
    if (!this.window.isDestroyed()) this.window.contentView.removeChildView(tab.view);
    if (!tab.view.webContents.isDestroyed()) tab.view.webContents.close();
  }

  private forget(tab: Tab): void {
    if (!this.tabs.delete(tab.id)) return;
    if (this.selected === tab.id) {
      this.selected = undefined;
      this.emit('detached', {});
    }
  }
}
