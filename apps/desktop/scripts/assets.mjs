// Copies the shared app icons into this package, where the main process and
// electron-builder look for them.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const source = path.resolve(here, '..', '..', '..', 'src-tauri', 'icons');
const target = path.resolve(here, '..', 'icons');
const files = [
  '32x32.png',
  '128x128.png',
  '128x128@2x.png',
  'icon.png',
  'icon.ico',
  'icon.icns',
  'tray-template.png',
];

fs.mkdirSync(target, { recursive: true });
for (const file of files) fs.copyFileSync(path.join(source, file), path.join(target, file));
console.log(`Copied ${files.length} icons to ${path.relative(process.cwd(), target) || '.'}`);
