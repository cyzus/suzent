import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const tauriDir = resolve(scriptDir, '..');
const repoDir = resolve(tauriDir, '..');
const manifestPath = join(repoDir, 'apps', 'suzent-installer', 'Cargo.toml');

const cargo = process.platform === 'win32' ? 'cargo.exe' : 'cargo';
const result = spawnSync(cargo, ['build', '--release', '--manifest-path', manifestPath], {
  cwd: repoDir,
  stdio: 'inherit',
});

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

const binaryName = process.platform === 'win32' ? 'suzent-installer.exe' : 'suzent-installer';
const source = join(repoDir, 'apps', 'suzent-installer', 'target', 'release', binaryName);
const destinationDir = join(tauriDir, 'resources', 'bin');
mkdirSync(destinationDir, { recursive: true });
copyFileSync(source, join(destinationDir, binaryName));
