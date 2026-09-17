/**
 * Finds the backend to develop against, so `npm run dev` needs no arguments.
 *
 * The desktop window is told its port by the Tauri shell. A browser tab on the
 * Vite origin has no such channel, and the backend worth developing against is
 * almost always one that is already running -- the installed service, or the
 * one the desktop app started -- rather than a second one launched just for
 * this. So we look for it the same way the CLI does, then confirm by asking.
 *
 * Node-only: imported by vite.config.ts, never by the bundle.
 */

import { homedir } from 'node:os';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Matches suzent.config.paths.DEFAULT_PORT. */
const DEFAULT_BACKEND_PORT = 25314;
const PROBE_TIMEOUT_MS = 400;

export interface DevBackend {
  url: string;
  /** Human-readable reason, printed at startup so a wrong guess is visible. */
  source: string;
}

/** Mirrors suzent.config.paths.get_data_dir(). */
function dataDir(): string {
  const override = process.env.SUZENT_DATA_DIR;
  if (override) return override;
  return join(homedir(), '.suzent');
}

/** The port in the running service's state file, if it wrote one. */
function servicePort(): number | null {
  try {
    const raw = readFileSync(join(dataDir(), 'runtime', 'service.json'), 'utf8');
    const port = (JSON.parse(raw) as { port?: unknown }).port;
    return typeof port === 'number' && Number.isFinite(port) ? port : null;
  } catch {
    return null;
  }
}

async function answers(port: number): Promise<boolean> {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/system/version`, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Resolve the dev backend, preferring one that actually answers.
 *
 * Resolved once, when the dev server starts: a backend started later will not
 * be picked up, which is why the choice is printed rather than assumed.
 */
export async function resolveDevBackend(): Promise<DevBackend> {
  const override = process.env.VITE_SUZENT_BACKEND;
  if (override) return { url: override, source: 'VITE_SUZENT_BACKEND' };

  const fromState = servicePort();
  const candidates: { port: number; source: string }[] = [];
  const seen = new Set<number>();
  for (const candidate of [
    { port: fromState, source: 'runtime/service.json' },
    { port: Number(process.env.SUZENT_PORT) || null, source: 'SUZENT_PORT' },
    { port: DEFAULT_BACKEND_PORT, source: 'default port' },
    { port: 8000, source: 'legacy default port' },
  ]) {
    if (candidate.port === null || seen.has(candidate.port)) continue;
    seen.add(candidate.port);
    candidates.push({ port: candidate.port, source: candidate.source });
  }

  for (const { port, source } of candidates) {
    if (await answers(port)) {
      return { url: `http://127.0.0.1:${port}`, source: `${source}, answering` };
    }
  }

  const port = fromState ?? DEFAULT_BACKEND_PORT;
  return {
    url: `http://127.0.0.1:${port}`,
    source: 'guessed -- nothing answered, start a backend and restart Vite',
  };
}
