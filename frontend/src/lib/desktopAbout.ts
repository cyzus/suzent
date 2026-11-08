import { invoke } from '@tauri-apps/api/core';
import { isWeb } from './runtime';

export type DesktopDistribution = 'microsoft_store' | 'github' | 'development' | 'web';
export type DesktopRuntime = 'bundled' | 'source' | 'unknown';

export interface DesktopAbout {
  packaged: boolean;
  distribution: DesktopDistribution;
  runtime: DesktopRuntime;
  installPath: string;
  dataDir: string;
  appVersion: string;
}

const GITHUB_REPO = 'https://github.com/cyzus/suzent';

export function releaseNotesUrl(version?: string | null): string {
  if (version && version !== 'unknown') {
    const tag = version.startsWith('v') ? version : `v${version}`;
    return `${GITHUB_REPO}/releases/tag/${tag}`;
  }
  return `${GITHUB_REPO}/releases/latest`;
}

export function commitUrl(commit: string): string {
  return `${GITHUB_REPO}/commit/${commit}`;
}

/** First 16 hex chars — short enough for About, stable enough for support. */
export function shortInstallationId(id: string | null | undefined): string | null {
  if (!id) return null;
  return id.slice(0, 16);
}

export async function fetchDesktopAbout(): Promise<DesktopAbout | null> {
  if (isWeb()) {
    return {
      packaged: false,
      distribution: 'web',
      runtime: 'unknown',
      installPath: '',
      dataDir: '',
      appVersion: __FRONTEND_VERSION__,
    };
  }
  try {
    const raw = await invoke<{
      packaged: boolean;
      distribution: string;
      runtime: string;
      install_path: string;
      data_dir: string;
      app_version: string;
    }>('get_desktop_about');
    const distribution =
      raw.distribution === 'microsoft_store' ||
      raw.distribution === 'github' ||
      raw.distribution === 'development'
        ? raw.distribution
        : 'github';
    const runtime = raw.runtime === 'bundled' || raw.runtime === 'source' ? raw.runtime : 'unknown';
    return {
      packaged: raw.packaged,
      distribution,
      runtime,
      installPath: raw.install_path,
      dataDir: raw.data_dir,
      appVersion: raw.app_version,
    };
  } catch {
    return null;
  }
}
