/**
 * Web pages shown inside the app window (the sidebar's web page view). Each
 * is a WebContentsView laid over the page's placeholder element, in its own
 * session so sites never share storage with the app itself.
 */

import { WebContentsView, shell, type BrowserWindow, type Rectangle } from 'electron';

export const EMBEDDED_PARTITION = 'persist:suzent-web-pages';

export function isWebUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

export function sanitizeBounds(bounds: Partial<Rectangle> | undefined): Rectangle {
  const int = (value: unknown, min: number): number =>
    typeof value === 'number' && Number.isFinite(value) ? Math.max(min, Math.round(value)) : min;
  return {
    x: int(bounds?.x, 0),
    y: int(bounds?.y, 0),
    width: int(bounds?.width, 1),
    height: int(bounds?.height, 1),
  };
}

export class EmbeddedPages {
  private readonly views = new Map<string, WebContentsView>();

  constructor(private readonly window: BrowserWindow) {
    window.on('closed', () => this.views.clear());
  }

  async open(id: string, url: string, bounds: Partial<Rectangle> | undefined): Promise<void> {
    if (!isWebUrl(url)) throw new Error(`Only http(s) pages can be embedded: ${url}`);
    this.close(id);
    const view = new WebContentsView({
      webPreferences: {
        partition: EMBEDDED_PARTITION,
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    view.setBackgroundColor('#ffffff');
    view.webContents.setWindowOpenHandler(({ url: target }) => {
      if (isWebUrl(target)) void shell.openExternal(target);
      return { action: 'deny' };
    });
    this.views.set(id, view);
    this.window.contentView.addChildView(view);
    view.setBounds(sanitizeBounds(bounds));
    await view.webContents.loadURL(url);
  }

  setBounds(id: string, bounds: Partial<Rectangle> | undefined): void {
    this.views.get(id)?.setBounds(sanitizeBounds(bounds));
  }

  close(id: string): void {
    const view = this.views.get(id);
    if (!view) return;
    this.views.delete(id);
    if (!this.window.isDestroyed()) this.window.contentView.removeChildView(view);
    view.webContents.close();
  }
}
