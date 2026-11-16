import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cpSync, mkdirSync, rmSync } from 'node:fs';

const root = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(root, '../../frontend');
const tsc = resolve(frontend, 'node_modules/.bin/tsc');
const esbuild = resolve(frontend, 'node_modules/.bin/esbuild');
const emit = resolve(root, '.es5');
const outfile = resolve(root, 'dist/suzent-bot-core.js');

rmSync(emit, { recursive: true, force: true });
execFileSync(
  tsc,
  [
    '--target',
    'ES5',
    '--module',
    'ESNext',
    '--moduleResolution',
    'bundler',
    '--lib',
    'ES2020,DOM',
    '--downlevelIteration',
    '--strict',
    '--skipLibCheck',
    '--outDir',
    emit,
    resolve(root, 'src/embed.ts'),
  ],
  { stdio: 'inherit' }
);

mkdirSync(resolve(root, 'dist'), { recursive: true });
execFileSync(
  esbuild,
  [
    resolve(emit, 'embed.js'),
    '--bundle',
    '--format=iife',
    '--target=es2015',
    '--minify',
    `--outfile=${outfile}`,
  ],
  { stdio: 'inherit' }
);

const resource = resolve(
  root,
  '../SuzentCore/Sources/SuzentCore/Resources/suzent-bot-core.js'
);
cpSync(outfile, resource);
rmSync(emit, { recursive: true, force: true });
