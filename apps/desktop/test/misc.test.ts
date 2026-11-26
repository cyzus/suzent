import assert from 'node:assert/strict';
import { test } from 'node:test';

import { extractJsonPayload, serviceCommand } from '../src/service';

test('service status JSON is found after log lines', () => {
  assert.equal(extractJsonPayload('starting...\n{"installed": true}'), '{"installed": true}');
  assert.throws(() => extractJsonPayload('no json here'));
});

test('service commands use the install python, or uv for a bare checkout', () => {
  const bundled = serviceCommand(
    { mode: 'bundled', dataDir: '/d', python: '/p', resourcesDir: '/r', sourceRoot: null },
    'uv',
    ['status', '--json']
  );
  assert.deepEqual(bundled, {
    command: '/p',
    args: ['-m', 'suzent.cli', 'service', 'status', '--json'],
    cwd: '/d',
  });
  const bare = serviceCommand(
    { mode: 'source', dataDir: '/d', python: null, resourcesDir: null, sourceRoot: '/repo' },
    'uv',
    ['install']
  );
  assert.deepEqual(bare, {
    command: 'uv',
    args: ['run', '--no-sync', 'suzent', 'service', 'install'],
    cwd: '/repo',
  });
});
