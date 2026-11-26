import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import {
  closeActionPath,
  decideClose,
  loadCloseAction,
  saveCloseAction,
  trayHostFor,
} from '../src/closeAction';

test('Windows asks and macOS hides until the user picks', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'suzent-close-'));
  assert.equal(loadCloseAction(dir, 'windows'), 'ask');
  assert.equal(loadCloseAction(dir, 'macos'), 'tray');
  saveCloseAction(dir, 'quit');
  assert.equal(loadCloseAction(dir, 'windows'), 'quit');
  fs.writeFileSync(closeActionPath(dir), 'nope');
  assert.equal(loadCloseAction(dir, 'windows'), 'ask');
});

test('explicit exits and a missing tray always let the window close', () => {
  assert.equal(decideClose('windows', true, true, 'tray'), 'allow');
  assert.equal(decideClose('windows', false, false, 'tray'), 'allow');
  assert.equal(decideClose('unsupported', true, false, 'tray'), 'allow');
  assert.equal(decideClose('macos', true, false, 'tray'), 'hide');
  assert.equal(decideClose('windows', true, false, 'ask'), 'ask');
  assert.equal(decideClose('windows', true, false, 'quit'), 'quit');
});

test('Linux has no tray', () => {
  assert.equal(trayHostFor('linux'), 'unsupported');
  assert.equal(trayHostFor('win32'), 'windows');
  assert.equal(trayHostFor('darwin'), 'macos');
});
