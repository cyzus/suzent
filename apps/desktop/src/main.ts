/**
 * Suzent desktop: one window over the local Python backend.
 *
 * The frontend is served from the `suzent://app` scheme (or the Vite dev
 * server), finds the backend port through the bridge, and talks to it over
 * loopback HTTP. Closing the window hides to the tray on Windows and macOS
 * per the user's close preference; quitting stops a backend this app owns.
 */

import {
  BrowserWindow,
  Notification,
  app,
  dialog,
  globalShortcut,
  ipcMain,
  net,
  protocol,
  shell,
  type IpcMainInvokeEvent,
  type OpenDialogOptions,
} from 'electron';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { Backend, StartupFailure, type StartupError } from './backend';
import {
  decideClose,
  loadCloseAction,
  parseCloseAction,
  saveCloseAction,
  supportsTray,
  trayHostFor,
} from './closeAction';
import { EmbeddedPages, isWebUrl } from './embeddedPages';
import { fetchHealth, isSuzentOk, SERVICE_PORT } from './health';
import { installShim } from './cliShim';
import { resolveLayout, type Layout } from './layout';
import { extractJsonPayload, runServiceCli } from './service';
import { SuzentTray } from './tray';
import { DesktopUpdater } from './updater';

const APP_ID = 'com.suzent.app';
const SCHEME = 'suzent';
const APP_ORIGIN = `${SCHEME}://app`;
const CLOSE_PROMPT_ACK_MS = 1500;
const CSP = [
  "default-src 'self'",
  "connect-src 'self' http://localhost:* ws://localhost:* http://127.0.0.1:* ws://127.0.0.1:*",
  "img-src 'self' data: blob: http://localhost:* http://127.0.0.1:*",
  "frame-src 'self' http://localhost:* http://127.0.0.1:*",
  "media-src 'self' blob: http://localhost:* http://127.0.0.1:*",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
].join('; ');

protocol.registerSchemesAsPrivileged([
  {
    scheme: SCHEME,
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
  },
]);

const layout: Layout = resolveLayout({
  resourcesPath: process.resourcesPath,
  appPath: app.getAppPath(),
  isPackaged: app.isPackaged,
  platform: process.platform,
  env: process.env,
  home: os.homedir(),
});
const host = trayHostFor(process.platform);
const appVersion = app.getVersion();

let mainWindow: BrowserWindow | null = null;
let embedded: EmbeddedPages | null = null;
let tray: SuzentTray | null = null;
let backend: Backend | null = null;
let startup: Promise<void> | null = null;
let startupError: StartupError | null = null;
let exiting = false;
let backendStopped = false;
let promptSeq = 0;
let promptAcked = 0;
const notifications = new Set<Notification>();
const shortcuts = new Set<string>();

function iconPath(name: string): string {
  return path.join(app.getAppPath(), 'icons', name);
}

/** `suzent` in a terminal on macOS and Linux; the Windows installer does its own. */
function installCliCommand(): void {
  if (layout.mode !== 'bundled' || process.platform === 'win32') return;
  try {
    const result = installShim(
      path.join(app.getPath('home'), '.local', 'bin'),
      app.getPath('exe'),
      process.resourcesPath,
      process.env
    );
    if (result === 'skipped-foreign') {
      console.warn('~/.local/bin/suzent belongs to another install; leaving it as it is.');
    }
  } catch (error) {
    console.warn('Could not install the suzent command:', error);
  }
}

function frontendDir(): string {
  const packaged = path.join(app.getAppPath(), 'frontend');
  if (fs.existsSync(path.join(packaged, 'index.html'))) return packaged;
  return path.join(layout.sourceRoot ?? process.cwd(), 'frontend', 'dist');
}

function emit(name: string, payload?: unknown): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('suzent:event', name, payload);
  }
}

function reveal(): void {
  const window = mainWindow;
  if (!window) return;
  window.show();
  if (window.isMinimized()) window.restore();
  if (process.platform === 'darwin') app.focus({ steal: true });
  window.focus();
}

function quit(): void {
  exiting = true;
  app.quit();
}

async function publishPort(port: number): Promise<void> {
  const window = mainWindow;
  if (!window || window.isDestroyed()) return;
  await window.webContents.executeJavaScript(
    `window.__SUZENT_BACKEND_PORT__ = ${port};
try { sessionStorage.setItem('SUZENT_PORT', '${port}'); } catch (e) {}
try { localStorage.setItem('SUZENT_PORT', '${port}'); } catch (e) {}`
  );
  emit('backend-ready', port);
}

let startupAbort: AbortController | null = null;

function startBackend(): Promise<void> {
  if (startup) return startup;
  startup = (async () => {
    if (backend && (await backend.isRunning())) return;
    backend = null;
    startupError = null;
    try {
      startupAbort = new AbortController();
      const next = await Backend.connect({ layout, appVersion, signal: startupAbort.signal });
      backend = next;
      console.log(`Backend ${next.owned ? 'started' : 'attached'} on port ${next.port}`);
      await publishPort(next.port);
    } catch (error) {
      const failure =
        error instanceof StartupFailure
          ? error.toJSON()
          : { message: error instanceof Error ? error.message : String(error), recoverable: true };
      startupError = failure;
      console.error(`Failed to start backend: ${failure.message}`);
      emit('backend-error', failure);
    }
  })().finally(() => {
    startup = null;
    startupAbort = null;
  });
  return startup;
}

async function stopBackend(): Promise<void> {
  const current = backend;
  backend = null;
  await current?.stop();
}

function showNotification(title: string, body: string): void {
  if (!Notification.isSupported()) return;
  const notification = new Notification({ title, body, icon: iconPath('128x128.png') });
  // Windows drops click events of notifications that were garbage collected.
  notifications.add(notification);
  const forget = (): void => {
    notifications.delete(notification);
  };
  notification.on('click', () => {
    reveal();
    forget();
  });
  notification.on('close', forget);
  notification.on('failed', forget);
  notification.show();
}

async function serviceStatus(): Promise<string> {
  return extractJsonPayload(await runServiceCli(layout, 'uv', ['status', '--json']));
}

async function setServiceEnabled(enabled: boolean): Promise<string> {
  if (enabled) {
    await runServiceCli(layout, 'uv', ['install']);
    return serviceStatus();
  }
  const wasAttached = backend !== null && !backend.owned;
  await runServiceCli(layout, 'uv', ['uninstall']);
  if (wasAttached) {
    // The window was using the service that was just removed: wait for its
    // port to close, then start an owned backend so the window keeps working.
    for (let attempt = 0; attempt < 30; attempt += 1) {
      if (!isSuzentOk(await fetchHealth(SERVICE_PORT))) break;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    backend = null;
    await startBackend();
  }
  return serviceStatus();
}

function desktopAbout(): Record<string, unknown> {
  const bundled = layout.mode === 'bundled';
  const distribution = process.windowsStore
    ? 'microsoft_store'
    : app.isPackaged
      ? 'github'
      : 'development';
  return {
    packaged: bundled,
    distribution,
    runtime: bundled ? 'bundled' : 'source',
    install_path: bundled ? path.dirname(app.getPath('exe')) : (layout.sourceRoot ?? ''),
    data_dir: layout.dataDir,
    app_version: appVersion,
  };
}

let updater: DesktopUpdater | null = null;

/** Installed builds update themselves; a development run is updated through git. */
function createUpdater(): DesktopUpdater | null {
  if (!app.isPackaged || layout.mode !== 'bundled') return null;
  // Loaded only here: electron-updater reads app-update.yml on import.
  const { autoUpdater } = require('electron-updater') as typeof import('electron-updater');
  return new DesktopUpdater(autoUpdater, {
    currentVersion: appVersion,
    dataDir: layout.dataDir,
    env: process.env,
    beforeInstall: async () => {
      exiting = true;
      // The service runs from this install's runtime, which the installer
      // replaces: stop it now and start it again from the new version.
      if (backend && !backend.owned) {
        try {
          await runServiceCli(layout, 'uv', ['stop']);
          fs.mkdirSync(path.dirname(restartServiceMarker()), { recursive: true });
          fs.writeFileSync(restartServiceMarker(), appVersion);
        } catch (error) {
          console.warn('Could not stop the background service before updating:', error);
        }
      }
      await stopBackend();
      backendStopped = true;
    },
    log: (message) => console.log(message),
  });
}

function restartServiceMarker(): string {
  return path.join(layout.dataDir, 'desktop', 'restart-service-after-update');
}

/** Starts the service an update stopped, before the window looks for a backend. */
async function restartServiceAfterUpdate(): Promise<void> {
  const marker = restartServiceMarker();
  if (!fs.existsSync(marker)) return;
  fs.rmSync(marker, { force: true });
  try {
    await runServiceCli(layout, 'uv', ['start']);
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline && !(await fetchHealth(SERVICE_PORT, 1000))) {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  } catch (error) {
    console.warn('Could not restart the background service after updating:', error);
  }
}

async function updateStatus(): Promise<string> {
  if (!updater) return JSON.stringify({ current_version: appVersion, update_available: false });
  return JSON.stringify(await updater.check());
}

function stringArg(args: Record<string, unknown>, key: string): string {
  const value = args[key];
  if (typeof value !== 'string') throw new Error(`Missing ${key}`);
  return value;
}

async function openDialogFor(options: Record<string, unknown>): Promise<string | string[] | null> {
  const properties: OpenDialogOptions['properties'] = [
    options.directory ? 'openDirectory' : 'openFile',
  ];
  if (options.multiple) properties.push('multiSelections');
  const dialogOptions: OpenDialogOptions = {
    properties,
    title: typeof options.title === 'string' ? options.title : undefined,
    defaultPath: typeof options.defaultPath === 'string' ? options.defaultPath : undefined,
  };
  const result = mainWindow
    ? await dialog.showOpenDialog(mainWindow, dialogOptions)
    : await dialog.showOpenDialog(dialogOptions);
  if (result.canceled || result.filePaths.length === 0) return null;
  return options.multiple ? result.filePaths : result.filePaths[0];
}

function safeExternal(url: string): boolean {
  try {
    return ['http:', 'https:', 'mailto:', 'file:'].includes(new URL(url).protocol);
  } catch {
    return false;
  }
}

type Handler = (args: Record<string, unknown>, event: IpcMainInvokeEvent) => unknown;

const commands: Record<string, Handler> = {
  // 0 until the backend passed its health check; the page keeps polling.
  get_backend_port: () => backend?.port ?? 0,
  get_backend_startup_error: () => startupError,
  retry_backend_start: () => {
    startupError = null;
    void startBackend();
  },
  is_backend_starting: () => startup !== null,
  frontend_ready: () => reveal(),
  bootstrap_status: () => ({
    required: false,
    workspace_dir: layout.sourceRoot ?? layout.dataDir,
    installer_available: false,
    installer_path: null,
  }),
  restart_app: async () => {
    exiting = true;
    await stopBackend();
    backendStopped = true;
    app.relaunch();
    app.exit(0);
  },
  check_for_update: () => updateStatus(),
  get_staged_update: () => updater?.stagedTag() ?? null,
  get_auto_update_enabled: () => updater?.autoUpdate ?? false,
  set_auto_update_enabled: (args) => {
    if (!updater) throw new Error('This build is updated through git, not automatically.');
    updater.setAutoUpdate(Boolean(args.enabled));
  },
  start_update_and_restart: async () => {
    if (!updater) throw new Error('This build is updated through git: run `git pull`.');
    await updater.installNow();
  },
  apply_staged_update_now: async () => {
    if (!updater) throw new Error('No update is ready to install');
    await updater.applyStaged();
  },
  get_service_status: () => serviceStatus(),
  set_service_enabled: (args) => setServiceEnabled(Boolean(args.enabled)),
  restart_background_service: async () => {
    await runServiceCli(layout, 'uv', ['restart']);
    return serviceStatus();
  },
  get_service_log_path: () => path.join(layout.dataDir, 'runtime', 'server.log'),
  get_desktop_about: () => desktopAbout(),
  show_notification: (args) => showNotification(stringArg(args, 'title'), stringArg(args, 'body')),
  set_tray_language: (args) => tray?.setLanguage(stringArg(args, 'language')),
  ack_close_prompt: (args) => {
    const seq = Number(args.seq);
    if (Number.isFinite(seq)) promptAcked = Math.max(promptAcked, seq);
  },
  get_close_action: () => (supportsTray(host) ? loadCloseAction(layout.dataDir, host) : null),
  set_close_action: (args) => {
    const action = parseCloseAction(stringArg(args, 'action'));
    if (!action) throw new Error(`Unknown close action: ${String(args.action)}`);
    saveCloseAction(layout.dataDir, action);
  },
  resolve_close: (args) => {
    const choice = parseCloseAction(stringArg(args, 'choice'));
    if (choice !== 'tray' && choice !== 'quit') {
      throw new Error(`Unknown close choice: ${String(args.choice)}`);
    }
    if (args.remember) saveCloseAction(layout.dataDir, choice);
    if (choice === 'quit') quit();
    else mainWindow?.hide();
  },
  window_minimize: () => mainWindow?.minimize(),
  window_toggle_maximize: () => {
    if (!mainWindow) return false;
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
    return mainWindow.isMaximized();
  },
  window_close: () => mainWindow?.close(),
  window_show: () => reveal(),
  open_external: async (args) => {
    const url = stringArg(args, 'url');
    if (!safeExternal(url)) throw new Error(`Refusing to open ${url}`);
    if (url.startsWith('file:')) {
      const error = await shell.openPath(fileURLToPath(url));
      if (error) throw new Error(error);
      return;
    }
    await shell.openExternal(url);
  },
  open_dialog: (args) => openDialogFor((args.options as Record<string, unknown>) ?? {}),
  register_shortcut: (args) => {
    const accelerator = stringArg(args, 'accelerator');
    if (shortcuts.has(accelerator)) return true;
    let ok = false;
    try {
      ok = globalShortcut.register(accelerator, () => emit('shortcut-pressed', accelerator));
    } catch {
      ok = false;
    }
    if (ok) shortcuts.add(accelerator);
    return ok;
  },
  unregister_shortcut: (args) => {
    const accelerator = stringArg(args, 'accelerator');
    if (shortcuts.delete(accelerator)) globalShortcut.unregister(accelerator);
  },
  embedded_page_open: (args) =>
    embedded?.open(
      stringArg(args, 'id'),
      stringArg(args, 'url'),
      args.bounds as Record<string, number> | undefined
    ),
  embedded_page_bounds: (args) =>
    embedded?.setBounds(stringArg(args, 'id'), args.bounds as Record<string, number> | undefined),
  embedded_page_close: (args) => embedded?.close(stringArg(args, 'id')),
};

function isAppFrame(event: IpcMainInvokeEvent): boolean {
  const url = event.senderFrame?.url ?? '';
  const devUrl = process.env.SUZENT_DEV_URL;
  return url.startsWith(`${APP_ORIGIN}/`) || (!!devUrl && url.startsWith(devUrl));
}

ipcMain.handle('suzent:invoke', async (event, command: string, args: Record<string, unknown>) => {
  if (!isAppFrame(event)) throw new Error('Desktop commands are only available to the app');
  const handler = commands[command];
  if (!handler) throw new Error(`Unknown desktop command: ${command}`);
  return handler(args ?? {}, event);
});

function contentType(file: string): string | undefined {
  return {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json',
    '.svg': 'image/svg+xml',
    '.wasm': 'application/wasm',
  }[path.extname(file).toLowerCase()];
}

function serveFrontend(): void {
  const root = frontendDir();
  protocol.handle(SCHEME, async (request) => {
    const url = new URL(request.url);
    if (url.host !== 'app') return new Response('Not found', { status: 404 });
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '');
    let file = path.resolve(root, relative || 'index.html');
    if (file !== root && !file.startsWith(root + path.sep)) {
      return new Response('Forbidden', { status: 403 });
    }
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      // Client-side routes all render the single page.
      file = path.join(root, 'index.html');
    }
    const response = await net.fetch(pathToFileURL(file).toString());
    const headers = new Headers(response.headers);
    const type = contentType(file);
    if (type) headers.set('Content-Type', type);
    if (file.endsWith('.html')) headers.set('Content-Security-Policy', CSP);
    return new Response(response.body, { status: response.status, headers });
  });
}

function onClose(event: Electron.Event): void {
  const decision = decideClose(
    host,
    tray?.ready ?? false,
    exiting,
    loadCloseAction(layout.dataDir, host)
  );
  if (decision === 'allow') return;
  event.preventDefault();
  if (decision === 'quit') {
    quit();
    return;
  }
  if (decision === 'hide') {
    mainWindow?.hide();
    return;
  }
  // Ask the page; if it does not acknowledge in time (still loading, hung),
  // hide so the close button never silently does nothing.
  const seq = ++promptSeq;
  emit('close-prompt', seq);
  setTimeout(() => {
    if (promptAcked < seq) mainWindow?.hide();
  }, CLOSE_PROMPT_ACK_MS);
}

function createWindow(): BrowserWindow {
  const mac = process.platform === 'darwin';
  const window = new BrowserWindow({
    title: 'SUZENT - Your Personal Agent',
    width: 1040,
    height: 760,
    minWidth: 760,
    minHeight: 560,
    show: false,
    backgroundColor: '#fafafa',
    icon: process.platform === 'linux' ? iconPath('icon.png') : undefined,
    // Windows and Linux draw their own title bar in the page. macOS keeps its
    // native traffic lights floating over the page header.
    frame: mac,
    titleBarStyle: mac ? 'hidden' : undefined,
    trafficLightPosition: mac ? { x: 16, y: 17 } : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });
  window.setMenuBarVisibility(false);
  window.on('close', onClose);
  window.on('closed', () => {
    mainWindow = null;
    embedded = null;
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (safeExternal(url)) void shell.openExternal(url);
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', (event, url) => {
    const devUrl = process.env.SUZENT_DEV_URL;
    if (url.startsWith(`${APP_ORIGIN}/`) || (devUrl && url.startsWith(devUrl))) return;
    event.preventDefault();
    if (isWebUrl(url)) void shell.openExternal(url);
  });
  const devUrl = process.env.SUZENT_DEV_URL;
  void window.loadURL(devUrl || `${APP_ORIGIN}/index.html`);
  return window;
}

function systemLanguage(): string {
  return process.env.LC_ALL || process.env.LANG || app.getLocale();
}

if (!app.requestSingleInstanceLock()) {
  app.exit(0);
} else {
  app.on('second-instance', () => {
    reveal();
    void startBackend();
  });

  app.setAppUserModelId(APP_ID);

  app.whenReady().then(() => {
    serveFrontend();
    mainWindow = createWindow();
    embedded = new EmbeddedPages(mainWindow);
    tray = new SuzentTray(
      host,
      { windows: iconPath('32x32.png'), macosTemplate: iconPath('tray-template.png') },
      {
        show: reveal,
        quit,
        openChat: (chatId) => {
          reveal();
          emit('tray-open-chat', chatId);
        },
        backendPort: () => backend?.port ?? null,
      },
      systemLanguage()
    );
    try {
      tray.install();
    } catch (error) {
      console.error('System tray unavailable; closing the window will quit Suzent:', error);
    }
    void restartServiceAfterUpdate().finally(() => void startBackend());
    installCliCommand();
    updater = createUpdater();
    updater?.start();
  });

  app.on('activate', () => reveal());

  // Dock Quit, Cmd+Q, the tray's Quit and a system shutdown all come here
  // first, so the window close they cause is let through instead of hiding.
  app.on('before-quit', (event) => {
    exiting = true;
    if (backendStopped || (!startup && !backend?.owned)) return;
    event.preventDefault();
    // A backend still starting is killed rather than left running alone.
    startupAbort?.abort();
    void (startup ?? Promise.resolve()).then(stopBackend).finally(() => {
      backendStopped = true;
      app.quit();
    });
  });

  app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    tray?.destroy();
  });

  app.on('window-all-closed', () => {
    app.quit();
  });
}
