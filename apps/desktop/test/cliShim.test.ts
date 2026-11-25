import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { installShim, isStableInstall, shimScript, SHIM_MARKER } from '../src/cliShim';

function tempDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'suzent-shim-'));
}

// The wrapper is a shell script for macOS and Linux; Windows uses resources\bin.
const unixOnly = { skip: process.platform === 'win32' };

test('writes the wrapper, then leaves it alone', unixOnly, () => {
  const bin = tempDir();
  const result = installShim(bin, '/Applications/SUZENT.app/Contents/MacOS/SUZENT', '/r', {});
  assert.equal(result, 'written');
  const target = path.join(bin, 'suzent');
  assert.ok(fs.readFileSync(target, 'utf8').includes(SHIM_MARKER));
  assert.equal(fs.statSync(target).mode & 0o111, 0o111);
  assert.equal(
    installShim(bin, '/Applications/SUZENT.app/Contents/MacOS/SUZENT', '/r', {}),
    'unchanged'
  );
  assert.equal(installShim(bin, '/elsewhere/SUZENT', '/r2', {}), 'written');
});

test('never replaces a suzent command that is not ours', unixOnly, () => {
  const bin = tempDir();
  const target = path.join(bin, 'suzent');
  fs.writeFileSync(target, '#!/bin/sh\nexec ~/suzent/.venv/bin/suzent "$@"\n');
  assert.equal(installShim(bin, '/a', '/r', {}), 'skipped-foreign');
  fs.rmSync(target);
  fs.symlinkSync(path.join(bin, 'missing'), target);
  assert.equal(installShim(bin, '/a', '/r', {}), 'skipped-foreign');
});

test('skips AppImage mounts', () => {
  assert.equal(isStableInstall('/tmp/.mount_SUZENTabc/resources', {}), false);
  assert.equal(isStableInstall('/opt/SUZENT/resources', { APPIMAGE: '/x.AppImage' }), false);
  assert.equal(isStableInstall('/opt/SUZENT/resources', {}), true);
});

test('quotes paths with spaces and quotes', () => {
  const script = shimScript(
    "/Users/a b/it's/SUZENT",
    '/Applications/SUZENT.app/Contents/Resources'
  );
  assert.ok(script.includes(`SUZENT_APP='/Users/a b/it'"'"'s/SUZENT'`));
});
