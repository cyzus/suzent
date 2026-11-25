import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { Backend, backendCommand, StartupFailure } from '../src/backend';
import type { Layout } from '../src/layout';

const fixture = path.resolve(__dirname, '..', '..', 'test', 'fixtures', 'fake_backend.py');
const python = process.platform === 'win32' ? 'python' : 'python3';

function sourceLayout(): { layout: Layout; root: string } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'suzent-backend-'));
  // A "venv python" that runs the fake server instead of suzent.server.
  const shim = path.join(root, process.platform === 'win32' ? 'python.cmd' : 'python');
  if (process.platform === 'win32') {
    fs.writeFileSync(shim, `@echo off\r\n${python} "${fixture}"\r\n`);
  } else {
    fs.writeFileSync(shim, `#!/bin/sh\nexec ${python} "${fixture}"\n`, { mode: 0o755 });
  }
  return {
    root,
    layout: {
      mode: 'source',
      dataDir: path.join(root, 'data'),
      python: shim,
      resourcesDir: null,
      sourceRoot: root,
    },
  };
}

test('backendCommand runs the bundled runtime from the data dir', () => {
  const [command, args, cwd] = backendCommand(
    { mode: 'bundled', dataDir: '/d', python: '/p', resourcesDir: null, sourceRoot: null },
    'uv'
  );
  assert.deepEqual([command, args, cwd], ['/p', ['-m', 'suzent.server'], '/d']);
  const [uv, uvArgs] = backendCommand(
    { mode: 'source', dataDir: '/d', python: null, resourcesDir: null, sourceRoot: '/repo' },
    'uv'
  );
  assert.equal(uv, 'uv');
  assert.deepEqual(uvArgs, ['run', '--no-sync', 'python', '-m', 'suzent.server']);
});

test(
  'start waits for the port and health, and stop shuts the child down',
  { skip: process.platform === 'win32' },
  async () => {
    const { layout, root } = sourceLayout();
    const env = { ...process.env, FAKE_SOURCE_ROOT: root, FAKE_VERSION: '9.9.9' };
    const backend = await Backend.start(0, { layout, appVersion: '9.9.9', env });
    assert.ok(backend.owned);
    assert.ok(backend.port > 0);
    assert.ok(await backend.isRunning());
    await backend.stop();
    assert.equal(
      await Backend.attachIfMatching(backend.port, { layout, appVersion: '9.9.9', env }),
      null
    );
  }
);

test(
  'a backend from another checkout is refused, not adopted',
  { skip: process.platform === 'win32' },
  async () => {
    const { layout } = sourceLayout();
    const env = { ...process.env, FAKE_SOURCE_ROOT: '/somewhere/else', FAKE_VERSION: '9.9.9' };
    await assert.rejects(
      Backend.start(0, { layout, appVersion: '9.9.9', env }),
      (error: unknown) =>
        error instanceof StartupFailure && !error.recoverable && /somewhere/.test(error.message)
    );
  }
);

test(
  'a backend that dies before reporting a port fails fast',
  { skip: process.platform === 'win32' },
  async () => {
    const { layout, root } = sourceLayout();
    fs.mkdirSync(path.join(layout.dataDir, 'runtime'), { recursive: true });
    const shim = layout.python as string;
    fs.writeFileSync(shim, '#!/bin/sh\nexit 4\n', { mode: 0o755 });
    const started = Date.now();
    await assert.rejects(
      Backend.start(0, {
        layout,
        appVersion: '1',
        env: { ...process.env, FAKE_SOURCE_ROOT: root },
      }),
      /before reporting a port/
    );
    assert.ok(Date.now() - started < 10_000);
  }
);

test(
  'aborting a start kills the backend that is still starting',
  { skip: process.platform === 'win32' },
  async () => {
    const { layout } = sourceLayout();
    const env = { ...process.env, FAKE_SLOW_START: '1', SUZENT_DATA_DIR: layout.dataDir };
    const controller = new AbortController();
    const started = Backend.start(0, {
      layout,
      appVersion: '9.9.9',
      env,
      signal: controller.signal,
    });
    const pidFile = path.join(layout.dataDir, 'runtime', 'fake.pid');
    while (!fs.existsSync(pidFile)) await new Promise((resolve) => setTimeout(resolve, 50));
    const pid = Number(fs.readFileSync(pidFile, 'utf8'));
    controller.abort();
    await assert.rejects(started, /cancelled/);
    await new Promise((resolve) => setTimeout(resolve, 300));
    assert.throws(() => process.kill(pid, 0));
  }
);
