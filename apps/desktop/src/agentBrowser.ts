/**
 * The agent's browser: real Chromium pages inside the app window, driven by
 * the backend's browser tool through the DevTools protocol of each page's
 * `webContents.debugger`. Nothing listens on a debugging port.
 *
 * The pages run in their own session, apart from the app and from the
 * sidebar's web pages, with no preload and no permissions. While the browser
 * panel is closed they keep working out of sight; the panel shows the
 * selected page with its tabs and address bar, where the user can watch and
 * use it. The agent always acts on the tab the panel shows.
 */

import { WebContentsView, session, type BrowserWindow, type Rectangle } from 'electron';

import {
  CDP_METHODS,
  addressUrl,
  agentUrl,
  isAgentUrl,
  type BrowserHost,
} from './agentBrowserLink';
import { sanitizeBounds } from './embeddedPages';

/** Sign-ins kept across restarts. */
export const AGENT_PARTITION = 'persist:suzent-agent-browser';
/** Sign-ins forgotten when the app quits. */
export const TEMPORARY_PARTITION = 'suzent-agent-browser';

const OUT_OF_VIEW: Rectangle = { x: 0, y: 0, width: 1, height: 1 };
const DESKTOP_METRICS = { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false };
const MAX_TABS = 20;
const LOAD_TIMEOUT_MS = 15_000;
const FRAME_INTERVAL_MS = 100;
const STATE_DELAY_MS = 50;

type Emit = (method: string, params: unknown) => void;

interface Tab {
  id: number;
  view: WebContentsView;
  shown: boolean | null;
}

export interface TabState {
  id: string;
  title: string;
  url: string;
  loading: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
}

export interface BrowserState {
  tabs: TabState[];
  selected: string | null;
}

const lockedDown = new Set<string>();

function lockDown(partition: string): void {
  if (lockedDown.has(partition)) return;
  lockedDown.add(partition);
  const agentSession = session.fromPartition(partition);
  agentSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  agentSession.setPermissionCheckHandler(() => false);
  agentSession.on('will-download', (event) => event.preventDefault());
}

const tabId = (tab: Tab): string => `tab-${tab.id}`;

export class AgentBrowser implements BrowserHost {
  private readonly tabs = new Map<number, Tab>();
  private nextId = 0;
  private selected: number | undefined;
  private shown: Rectangle | null = null;
  private pendingFrame: unknown = null;
  private frameTimer: ReturnType<typeof setTimeout> | null = null;
  private stateTimer: ReturnType<typeof setTimeout> | null = null;
  private partition = AGENT_PARTITION;
  /** DevTools events for the backend. */
  emit: Emit = () => undefined;
  /** Tab and address bar state for the browser panel. */
  onState: (state: BrowserState) => void = () => undefined;

  constructor(
    private readonly window: BrowserWindow,
    private readonly focus: () => void
  ) {
    lockDown(this.partition);
    window.on('closed', () => this.tabs.clear());
  }

  /** Lays the selected page over the browser panel. */
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
    this.pendingFrame = null;
    this.layout();
  }

  state(): BrowserState {
    return {
      tabs: [...this.tabs.values()].map((tab) => {
        const contents = tab.view.webContents;
        return {
          id: tabId(tab),
          title: contents.getTitle().slice(0, 200),
          url: contents.getURL(),
          loading: contents.isLoading(),
          canGoBack: contents.navigationHistory.canGoBack(),
          canGoForward: contents.navigationHistory.canGoForward(),
        };
      }),
      selected: this.selected === undefined ? null : `tab-${this.selected}`,
    };
  }

  /**
   * Keeps sign-ins across restarts or not. Switching closes every tab, since
   * an open page keeps the session it was made in.
   */
  configure(persistent: boolean): void {
    const partition = persistent ? AGENT_PARTITION : TEMPORARY_PARTITION;
    if (partition === this.partition) return;
    this.closeAll();
    this.partition = partition;
    lockDown(partition);
  }

  /** Signs out of every site and forgets the browser's data. */
  async clearData(): Promise<void> {
    this.closeAll();
    await Promise.all(
      [AGENT_PARTITION, TEMPORARY_PARTITION].map(async (partition) => {
        const data = session.fromPartition(partition);
        await data.clearStorageData();
        await data.clearCache();
      })
    );
  }

  /** What the user does in the panel's tab bar and address bar. */
  async command(action: string, params: Record<string, unknown>): Promise<void> {
    const tab = typeof params.id === 'string' ? this.find(params.id) : this.current();
    switch (action) {
      case 'new': {
        const created = this.create();
        await this.load(
          created,
          typeof params.url === 'string' ? addressUrl(params.url) : 'about:blank'
        );
        await this.choose(created);
        return;
      }
      case 'select':
        if (tab) await this.choose(tab);
        return;
      case 'close':
        if (tab) await this.close(tab);
        return;
      case 'navigate': {
        const url = addressUrl(String(params.url ?? ''));
        const target = tab ?? this.create();
        await this.load(target, url);
        if (!tab) await this.choose(target);
        return;
      }
      case 'back':
        tab?.view.webContents.navigationHistory.goBack();
        return;
      case 'forward':
        tab?.view.webContents.navigationHistory.goForward();
        return;
      case 'reload':
        tab?.view.webContents.reload();
        return;
      case 'stop':
        tab?.view.webContents.stop();
        return;
      default:
        throw new Error('Unsupported browser command.');
    }
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
      case 'configure':
        this.configure(params.persistent !== false);
        return {};
      case 'tabs':
        return [...this.tabs.values()].map((tab) => ({
          id: tabId(tab),
          title: tab.view.webContents.getTitle().slice(0, 200),
          url: tab.view.webContents.getURL(),
          selected: tab.id === this.selected,
          active: tab.id === this.selected,
          focused: tab.id === this.selected && this.shown !== null,
        }));
      case 'select': {
        const tab = typeof params.id === 'string' ? this.find(params.id) : undefined;
        if (!tab) throw new Error('List tabs and select a valid tab.');
        await this.select(tab);
        return { id: tabId(tab), url: tab.view.webContents.getURL() };
      }
      case 'open': {
        const url = agentUrl(params.url);
        const tab = this.current() ?? this.create();
        await this.load(tab, url);
        await this.select(tab);
        return { id: tabId(tab), url };
      }
      case 'new': {
        const url = params.url === undefined ? 'about:blank' : agentUrl(params.url);
        const tab = this.create();
        await this.load(tab, url);
        await this.select(tab);
        return { id: tabId(tab), url };
      }
      case 'close': {
        const tab = typeof params.id === 'string' ? this.find(params.id) : undefined;
        if (!tab) throw new Error('List tabs and close a valid tab.');
        const next = this.neighbor(tab);
        this.closeTab(tab);
        if (next && this.selected === undefined) await this.select(next);
        return { selected: this.selected === undefined ? null : `tab-${this.selected}` };
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
    this.closeAll();
  }

  private current(): Tab | undefined {
    return this.selected === undefined ? undefined : this.tabs.get(this.selected);
  }

  private find(id: string): Tab | undefined {
    const match = /^tab-(\d+)$/.exec(id);
    return match ? this.tabs.get(Number(match[1])) : undefined;
  }

  /** The tab to show once *tab* closes: the one after it, else before it. */
  private neighbor(tab: Tab): Tab | undefined {
    const order = [...this.tabs.values()];
    const index = order.indexOf(tab);
    return order[index + 1] ?? order[index - 1];
  }

  private create(): Tab {
    if (this.tabs.size >= MAX_TABS) throw new Error('Too many browser tabs are open.');
    const view = new WebContentsView({
      webPreferences: {
        partition: this.partition,
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
    for (const event of [
      'did-start-loading',
      'did-stop-loading',
      'did-navigate',
      'did-navigate-in-page',
      'page-title-updated',
    ] as const) {
      contents.on(event as 'did-start-loading', () => this.changed());
    }
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
    this.changed();
    return tab;
  }

  private async select(tab: Tab): Promise<void> {
    if (this.selected !== tab.id) {
      this.selected = tab.id;
      this.pendingFrame = null;
      this.layout();
      this.changed();
    }
    // DevTools commands to a page that never loaded wait for its first load.
    if (!tab.view.webContents.getURL()) await this.load(tab, 'about:blank');
    await tab.view.webContents.debugger.sendCommand('Page.enable');
  }

  /** Selects a tab for the user and moves the agent there too. */
  private async choose(tab: Tab): Promise<void> {
    const moved = this.selected !== tab.id;
    await this.select(tab);
    if (moved) this.emit('selected', { id: tabId(tab) });
  }

  private async close(tab: Tab): Promise<void> {
    const wasSelected = this.selected === tab.id;
    const next = this.neighbor(tab);
    this.closeTab(tab);
    if (wasSelected && next) await this.choose(next);
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

  private changed(): void {
    if (this.stateTimer) return;
    this.stateTimer = setTimeout(() => {
      this.stateTimer = null;
      if (!this.window.isDestroyed()) this.onState(this.state());
    }, STATE_DELAY_MS);
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

  private closeAll(): void {
    for (const tab of [...this.tabs.values()]) this.closeTab(tab);
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
    this.changed();
  }
}
