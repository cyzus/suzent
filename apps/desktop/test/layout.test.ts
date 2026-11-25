import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';

import { bundledPythonEnv, dataDirFor, findSourceRoot, resolveLayout } from '../src/layout';

const has = (files: string[]) => (file: string) => files.includes(file);

test('a packaged app with a bundled runtime runs it', () => {
  const resources = path.join('/opt', 'Suzent', 'resources');
  const python = path.join(resources, 'runtime', 'python', 'bin', 'python3');
  const layout = resolveLayout({
    resourcesPath: resources,
    appPath: path.join(resources, 'app.asar'),
    isPackaged: true,
    platform: 'linux',
    env: {},
    home: '/home/me',
    exists: has([python, path.join(resources, 'suzent')]),
  });
  assert.equal(layout.mode, 'bundled');
  assert.equal(layout.python, python);
  assert.equal(layout.resourcesDir, path.join(resources, 'suzent'));
  assert.equal(layout.dataDir, path.join('/home/me', '.suzent'));
});

test('Windows looks for python.exe at the runtime root', () => {
  const resources = 'C:\\Suzent\\resources';
  const python = path.join(resources, 'runtime', 'python', 'python.exe');
  const layout = resolveLayout({
    resourcesPath: resources,
    appPath: resources,
    isPackaged: true,
    platform: 'win32',
    env: {},
    home: 'C:\\Users\\me',
    exists: has([python]),
  });
  assert.equal(layout.mode, 'bundled');
  assert.equal(layout.python, python);
  assert.equal(layout.resourcesDir, null);
});

test('a development run uses the checkout it lives in', () => {
  const repo = path.join('/src', 'suzent');
  const venv = path.join(repo, '.venv', 'bin', 'python');
  const layout = resolveLayout({
    resourcesPath: '/electron/resources',
    appPath: path.join(repo, 'apps', 'desktop'),
    isPackaged: false,
    platform: 'linux',
    env: {},
    home: '/home/me',
    exists: has([path.join(repo, 'pyproject.toml'), venv]),
  });
  assert.equal(layout.mode, 'source');
  assert.equal(layout.sourceRoot, repo);
  assert.equal(layout.python, venv);
});

test('SUZENT_DIR picks the checkout, and no venv falls back to uv', () => {
  const layout = resolveLayout({
    resourcesPath: '/r',
    appPath: '/elsewhere',
    isPackaged: false,
    platform: 'linux',
    env: { SUZENT_DIR: '/work/suzent' },
    home: '/home/me',
    exists: has([path.join('/work/suzent', 'pyproject.toml')]),
  });
  assert.equal(layout.sourceRoot, path.resolve('/work/suzent'));
  assert.equal(layout.python, null);
});

test('the data dir honours SUZENT_DATA_DIR and the side-by-side name', () => {
  assert.equal(dataDirFor({ SUZENT_DATA_DIR: '/data' }, '/home/me'), '/data');
  assert.equal(
    dataDirFor({ SUZENT_DATA_DIR_NAME: '.suzent-preview' }, '/home/me'),
    path.join('/home/me', '.suzent-preview')
  );
});

test('findSourceRoot stops at the filesystem root', () => {
  assert.equal(
    findSourceRoot('/a/b/c', () => false),
    null
  );
});

test('bundled processes get resources, caches and no bytecode writes', () => {
  const env = bundledPythonEnv(
    {
      mode: 'bundled',
      dataDir: '/home/me/.suzent',
      python: '/r/runtime/python/bin/python3',
      resourcesDir: '/r/suzent',
      sourceRoot: null,
    },
    { PATH: '/usr/bin', UV_CACHE_DIR: '/custom' }
  );
  assert.equal(env.SUZENT_PROJECT_DIR, '/r/suzent');
  assert.equal(env.PYTHONDONTWRITEBYTECODE, '1');
  assert.equal(env.SUZENT_PACKAGED, '1');
  assert.equal(env.PLAYWRIGHT_BROWSERS_PATH, path.join('/home/me/.suzent', 'ms-playwright'));
  assert.equal(env.UV_CACHE_DIR, '/custom');
  assert.equal(env.PATH, '/usr/bin');
});
