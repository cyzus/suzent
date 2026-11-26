// Builds Suzent-Setup-<version>-win-x64.exe: the drawn setup program
// (apps/desktop-setup) with the electron-builder installer appended, in the
// layout apps/desktop-setup/src/payload.rs reads. Run after `npm run dist`.
//
//   node scripts/build-setup.mjs [--setup <exe>] [--package <exe>] [--unpacked <dir>]
//
// Without --setup it builds the setup with cargo first.

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const desktop = path.resolve(here, '..');
const crate = path.resolve(desktop, '..', 'desktop-setup');
const release = path.join(desktop, 'release');
const MAGIC = Buffer.from('SZSETUP1');

function option(name) {
  const at = process.argv.indexOf(name);
  return at === -1 ? undefined : process.argv[at + 1];
}

function sizeOf(dir) {
  let total = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    total += entry.isDirectory() ? sizeOf(full) : fs.statSync(full).size;
  }
  return total;
}

function u64(value) {
  const buffer = Buffer.alloc(8);
  buffer.writeBigUInt64LE(BigInt(value));
  return buffer;
}

const { version } = JSON.parse(fs.readFileSync(path.join(desktop, 'package.json'), 'utf8'));
const pkg = option('--package') ?? path.join(release, `Suzent-${version}-win-x64.exe`);
const unpacked = option('--unpacked') ?? path.join(release, 'win-unpacked');
let setup = option('--setup');
if (!setup) {
  execFileSync('cargo', ['build', '--release', '--locked'], { cwd: crate, stdio: 'inherit' });
  setup = path.join(crate, 'target', 'release', process.platform === 'win32' ? 'suzent-setup.exe' : 'suzent-setup');
}
for (const file of [pkg, setup]) {
  if (!fs.existsSync(file)) throw new Error(`Missing ${file}`);
}

const out = path.join(release, `Suzent-Setup-${version}-win-x64.exe`);
const meta = Buffer.from(JSON.stringify({ version, unpacked_bytes: sizeOf(unpacked) }));
const packageSize = fs.statSync(pkg).size;
fs.mkdirSync(release, { recursive: true });
fs.copyFileSync(setup, out);
fs.appendFileSync(out, fs.readFileSync(pkg));
fs.appendFileSync(out, Buffer.concat([meta, u64(meta.length), u64(packageSize), MAGIC]));
console.log(`Wrote ${path.relative(process.cwd(), out)} (${(fs.statSync(out).size / 1e6).toFixed(1)} MB)`);
