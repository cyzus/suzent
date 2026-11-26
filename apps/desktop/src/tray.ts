/**
 * Windows notification area and macOS menu bar. Linux has no tray: closing
 * the window quits there, as it did in the Tauri app.
 */

import {
  Menu,
  Tray,
  nativeImage,
  type MenuItemConstructorOptions,
  type NativeImage,
} from 'electron';

import {
  badged,
  faded,
  fetchSnapshot,
  isChinese,
  menuEntries,
  needsAttention,
  sameSnapshot,
  tooltip,
  type Snapshot,
} from './trayStatus';
import type { TrayHost } from './closeAction';

const POLL_EVERY_MS = 4000;

export interface TrayActions {
  show(): void;
  quit(): void;
  openChat(chatId: string): void;
  backendPort(): number | null;
}

export class SuzentTray {
  private tray: Tray | null = null;
  private language: string;
  private last: Snapshot | null = null;
  private timer: NodeJS.Timeout | null = null;
  private base: NativeImage | null = null;

  constructor(
    private readonly host: TrayHost,
    private readonly icons: { windows: string; macosTemplate: string },
    private readonly actions: TrayActions,
    language: string
  ) {
    this.language = language;
  }

  get ready(): boolean {
    return this.tray !== null;
  }

  install(): void {
    if (this.host === 'unsupported') return;
    if (this.host === 'macos') {
      const image = nativeImage.createFromPath(this.icons.macosTemplate);
      // The 44px glyph is the @2x rendition of a 22pt menu-bar icon.
      const template = nativeImage.createEmpty();
      template.addRepresentation({ scaleFactor: 2, buffer: image.toPNG() });
      template.setTemplateImage(true);
      this.tray = new Tray(template);
    } else {
      this.base = nativeImage.createFromPath(this.icons.windows);
      this.tray = new Tray(this.base);
      // Windows: left click restores, right click opens the menu.
      this.tray.on('click', () => this.actions.show());
    }
    this.apply({ kind: 'starting' });
    this.timer = setInterval(() => void this.refresh(), POLL_EVERY_MS);
  }

  setLanguage(language: string): void {
    this.language = language;
    if (this.last) this.apply(this.last);
  }

  destroy(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.tray?.destroy();
    this.tray = null;
  }

  private async refresh(): Promise<void> {
    const snapshot = await fetchSnapshot(this.actions.backendPort());
    if (!sameSnapshot(this.last, snapshot)) this.apply(snapshot);
  }

  private apply(snapshot: Snapshot): void {
    const tray = this.tray;
    if (!tray) return;
    this.last = snapshot;
    const zh = isChinese(this.language);
    tray.setToolTip(tooltip(snapshot, zh));
    if (this.host === 'windows' && this.base) tray.setImage(this.iconFor(snapshot, this.base));
    tray.setContextMenu(Menu.buildFromTemplate(this.template(snapshot, zh)));
  }

  private iconFor(snapshot: Snapshot, base: NativeImage): NativeImage {
    const { width, height } = base.getSize();
    const bitmap = base.toBitmap();
    if (needsAttention(snapshot)) {
      return nativeImage.createFromBitmap(badged(bitmap, width, height), { width, height });
    }
    if (snapshot.kind === 'unreachable') {
      return nativeImage.createFromBitmap(faded(bitmap), { width, height });
    }
    return base;
  }

  private template(snapshot: Snapshot, zh: boolean): MenuItemConstructorOptions[] {
    return menuEntries(snapshot, zh).map((entry): MenuItemConstructorOptions => {
      switch (entry.type) {
        case 'separator':
          return { type: 'separator' };
        case 'label':
          return { label: entry.label, enabled: false };
        case 'chat':
          return { label: entry.label, click: () => this.actions.openChat(entry.chatId) };
        case 'show':
          return { label: entry.label, click: () => this.actions.show() };
        case 'quit':
          return { label: entry.label, click: () => this.actions.quit() };
      }
    });
  }
}
