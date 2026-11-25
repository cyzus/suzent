/**
 * The `suzent` command for macOS and Linux installs: a small wrapper in
 * ~/.local/bin that runs the bundled runtime's CLI. Windows gets the same
 * command from the installer, which puts resources\bin on the user's PATH.
 */

import fs from 'node:fs';
import path from 'node:path';

export const SHIM_MARKER = '# managed-by: suzent-desktop';

export type ShimResult = 'written' | 'unchanged' | 'skipped-foreign' | 'skipped-unstable';

function quote(value: string): string {
  return `'${value.replaceAll("'", `'"'"'`)}'`;
}

export function shimScript(appExe: string, resourcesDir: string): string {
  const resources = quote(resourcesDir);
  return [
    '#!/bin/sh',
    SHIM_MARKER,
    `SUZENT_RESOURCES=${resources}`,
    `if [ ! -x "$SUZENT_RESOURCES/bin/suzent" ]; then`,
    `  echo "Suzent is no longer at $SUZENT_RESOURCES. Open the Suzent app once to fix this command." >&2`,
    '  exit 1',
    'fi',
    `SUZENT_APP=${quote(appExe)} SUZENT_RESOURCES="$SUZENT_RESOURCES" exec "$SUZENT_RESOURCES/bin/suzent" "$@"`,
    '',
  ].join('\n');
}

/** An AppImage runs from a fresh mount point each launch; nothing can point there. */
export function isStableInstall(resourcesDir: string, env: NodeJS.ProcessEnv): boolean {
  return !env.APPIMAGE && !resourcesDir.includes(`${path.sep}.mount_`);
}

/**
 * Writes the wrapper unless a `suzent` that is not ours is already there,
 * such as a source install's own command.
 */
export function installShim(
  binDir: string,
  appExe: string,
  resourcesDir: string,
  env: NodeJS.ProcessEnv
): ShimResult {
  if (!isStableInstall(resourcesDir, env)) return 'skipped-unstable';
  const target = path.join(binDir, 'suzent');
  const script = shimScript(appExe, resourcesDir);
  let current: string | null = null;
  try {
    current = fs.readFileSync(target, 'utf8');
  } catch {
    // Absent, or a dangling link: treat as free only when nothing is there.
    if (fs.existsSync(target) || isLink(target)) return 'skipped-foreign';
  }
  if (current !== null && !current.includes(SHIM_MARKER)) return 'skipped-foreign';
  if (current === script) return 'unchanged';
  fs.mkdirSync(binDir, { recursive: true });
  const temp = `${target}.${process.pid}.tmp`;
  fs.writeFileSync(temp, script, { mode: 0o755 });
  fs.renameSync(temp, target);
  return 'written';
}

function isLink(file: string): boolean {
  try {
    return fs.lstatSync(file).isSymbolicLink();
  } catch {
    return false;
  }
}
