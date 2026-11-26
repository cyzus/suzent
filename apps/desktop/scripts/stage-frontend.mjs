// Copies the built web UI (frontend/dist) into this package, where the
// packaged app serves it from.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const source = path.resolve(here, '..', '..', '..', 'frontend', 'dist');
const target = path.resolve(here, '..', 'frontend');

if (!fs.existsSync(path.join(source, 'index.html'))) {
  console.error(`No built frontend at ${source}. Run \`npm run build\` in frontend/ first.`);
  process.exit(1);
}
fs.rmSync(target, { recursive: true, force: true });
fs.cpSync(source, target, { recursive: true });
console.log(`Staged the frontend into ${path.relative(process.cwd(), target) || '.'}`);
