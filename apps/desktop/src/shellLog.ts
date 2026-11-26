/**
 * Keeps what the main process prints in `<data dir>/runtime/desktop-shell.log`:
 * an installed app has no terminal, and a startup that stalls otherwise
 * leaves nothing to read.
 */

import fs from 'node:fs';
import path from 'node:path';
import { format } from 'node:util';

const MAX_BYTES = 1_000_000;

export function keepShellLog(dataDir: string): string {
  const file = path.join(dataDir, 'runtime', 'desktop-shell.log');
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    if ((fs.statSync(file, { throwIfNoEntry: false })?.size ?? 0) > MAX_BYTES) {
      fs.renameSync(file, `${file}.1`);
    }
  } catch {
    // A log we cannot rotate is still worth appending to.
  }
  for (const level of ['log', 'info', 'warn', 'error'] as const) {
    const original = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      original(...args);
      try {
        fs.appendFileSync(
          file,
          `${new Date().toISOString()} ${level.toUpperCase()} ${format(...args)}\n`
        );
      } catch {
        // Never let logging break the app.
      }
    };
  }
  return file;
}
