/**
 * Self-update for installed builds, through electron-updater: GitHub
 * releases by default, or a mirror feed (an electron-builder "generic"
 * directory: latest.yml plus the installers) when GitHub is unreachable or
 * the user names one. Updates download in the background and install when
 * the app quits, or right away when nobody is using it (the page decides).
 */

import fs from 'node:fs';
import path from 'node:path';

export interface UpdateInfoLike {
  version: string;
}

export interface UpdaterLike {
  autoDownload: boolean;
  autoInstallOnAppQuit: boolean;
  checkForUpdates(): Promise<{ updateInfo: UpdateInfoLike } | null>;
  downloadUpdate(): Promise<unknown>;
  quitAndInstall(isSilent?: boolean, isForceRunAfter?: boolean): void;
  setFeedURL(options: { provider: 'generic'; url: string }): void;
  on(event: 'update-downloaded', listener: (info: UpdateInfoLike) => void): unknown;
  on(event: 'error', listener: (error: Error) => void): unknown;
}

export interface UpdateStatus {
  current_version: string;
  latest_version?: string;
  update_available: boolean;
  error?: string;
}

const CHECK_EVERY_MS = 6 * 60 * 60 * 1000;
const FIRST_CHECK_AFTER_MS = 15_000;

export function autoUpdatePath(dataDir: string): string {
  return path.join(dataDir, 'desktop', 'auto-update');
}

export function mirrorPath(dataDir: string): string {
  return path.join(dataDir, 'desktop', 'update-mirror');
}

/** On unless the user turned it off, or SUZENT_AUTO_UPDATE=0. */
export function loadAutoUpdate(dataDir: string, env: NodeJS.ProcessEnv): boolean {
  const flag = env.SUZENT_AUTO_UPDATE?.trim().toLowerCase();
  if (flag === '0' || flag === 'false' || flag === 'off') return false;
  try {
    return fs.readFileSync(autoUpdatePath(dataDir), 'utf8').trim() !== 'off';
  } catch {
    return true;
  }
}

export function saveAutoUpdate(dataDir: string, enabled: boolean): void {
  const file = autoUpdatePath(dataDir);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, enabled ? 'on' : 'off');
}

/** SUZENT_UPDATE_MIRROR, else the URL in desktop/update-mirror, else none. */
export function loadMirror(dataDir: string, env: NodeJS.ProcessEnv): string | null {
  const candidates = [env.SUZENT_UPDATE_MIRROR];
  try {
    candidates.push(fs.readFileSync(mirrorPath(dataDir), 'utf8'));
  } catch {
    // No mirror configured.
  }
  for (const raw of candidates) {
    const value = raw?.trim();
    if (value && /^https:\/\//.test(value)) return value.replace(/\/+$/, '');
  }
  return null;
}

export function isNewer(candidate: string, current: string): boolean {
  const parse = (value: string): number[] =>
    value
      .replace(/^v/, '')
      .split(/[.-]/)
      .slice(0, 3)
      .map((part) => Number.parseInt(part, 10) || 0);
  const a = parse(candidate);
  const b = parse(current);
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
}

/**
 * Releases published before the installers existed have no latest*.yml, so
 * there is nothing this app can update to yet; that is not a failure.
 */
export function isMissingFeed(message: string): boolean {
  return /Cannot find latest[\w.-]*\.yml/.test(message);
}

export class DesktopUpdater {
  private staged: string | null = null;
  private enabled: boolean;
  private timer: NodeJS.Timeout | null = null;
  private usingMirror = false;

  constructor(
    private readonly updater: UpdaterLike,
    private readonly options: {
      currentVersion: string;
      dataDir: string;
      env: NodeJS.ProcessEnv;
      /** Runs before the app quits into the installer (stops the backend). */
      beforeInstall: () => Promise<void>;
      log?: (message: string) => void;
    }
  ) {
    this.enabled = loadAutoUpdate(options.dataDir, options.env);
    updater.autoDownload = this.enabled;
    updater.autoInstallOnAppQuit = this.enabled;
    updater.on('update-downloaded', (info) => {
      this.staged = `v${info.version}`;
      this.log(`Update ${info.version} downloaded; installs on quit`);
    });
    updater.on('error', (error) => this.log(`Updater: ${error.message}`));
  }

  start(): void {
    const first = setTimeout(() => void this.quietCheck(), FIRST_CHECK_AFTER_MS);
    first.unref?.();
    this.timer = setInterval(() => void this.quietCheck(), CHECK_EVERY_MS);
    this.timer.unref?.();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  get autoUpdate(): boolean {
    return this.enabled;
  }

  setAutoUpdate(enabled: boolean): void {
    saveAutoUpdate(this.options.dataDir, enabled);
    this.enabled = enabled;
    this.updater.autoDownload = enabled;
    this.updater.autoInstallOnAppQuit = enabled;
  }

  stagedTag(): string | null {
    return this.staged;
  }

  async check(): Promise<UpdateStatus> {
    const current = this.options.currentVersion;
    try {
      const result = await this.checkWithFallback();
      const latest = result?.updateInfo.version;
      return {
        current_version: current,
        latest_version: latest,
        update_available: Boolean(latest && isNewer(latest, current)),
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (isMissingFeed(message)) {
        this.log(`Latest release has no installer update feed yet: ${message.split('\n')[0]}`);
        return { current_version: current, update_available: false };
      }
      return {
        current_version: current,
        update_available: false,
        error: message,
      };
    }
  }

  /** Downloads if needed, then quits into the installer and reopens Suzent. */
  async installNow(): Promise<void> {
    if (!this.staged) {
      const status = await this.check();
      if (status.error) throw new Error(status.error);
      if (!status.update_available) throw new Error('Suzent is already up to date');
      await this.updater.downloadUpdate();
      if (!this.staged && status.latest_version) this.staged = `v${status.latest_version}`;
    }
    await this.applyStaged();
  }

  async applyStaged(): Promise<void> {
    if (!this.staged) throw new Error('No update is ready to install');
    await this.options.beforeInstall();
    this.updater.quitAndInstall(true, true);
  }

  private async quietCheck(): Promise<void> {
    if (!this.enabled || this.staged) return;
    await this.check();
  }

  private async checkWithFallback(): Promise<{ updateInfo: UpdateInfoLike } | null> {
    const mirror = loadMirror(this.options.dataDir, this.options.env);
    if (mirror && !this.usingMirror && this.options.env.SUZENT_UPDATE_MIRROR) {
      this.useMirror(mirror);
    }
    try {
      return await this.updater.checkForUpdates();
    } catch (error) {
      if (!mirror || this.usingMirror) throw error;
      this.log(`GitHub update check failed (${String(error)}); trying ${mirror}`);
      this.useMirror(mirror);
      return await this.updater.checkForUpdates();
    }
  }

  private useMirror(url: string): void {
    this.updater.setFeedURL({ provider: 'generic', url });
    this.usingMirror = true;
  }

  private log(message: string): void {
    this.options.log?.(message);
  }
}
