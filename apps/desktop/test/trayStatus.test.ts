import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  ATTENTION_BGRA,
  badged,
  clipTitle,
  faded,
  menuEntries,
  needsAttention,
  snapshotFromRows,
  tooltip,
} from '../src/trayStatus';

const rows = [
  { chatId: 'a', title: 'Plan the trip', state: 'waiting', waitingKind: 'approval' },
  { chatId: 'b', title: null, state: 'running' },
  { chatId: 'c', title: 'Idle', state: 'idle' },
];

test('chats are sorted into waiting and running', () => {
  const snapshot = snapshotFromRows(rows);
  assert.equal(snapshot.kind, 'ready');
  assert.ok(needsAttention(snapshot));
  assert.equal(tooltip(snapshot, false), 'SUZENT · 1 waiting for you · 1 running');
  assert.equal(tooltip(snapshot, true), 'SUZENT · 1 个聊天在等你 · 1 个正在运行');
});

test('the menu lists chats and always ends with Open and Quit', () => {
  const entries = menuEntries(snapshotFromRows(rows), false);
  const chats = entries.filter((entry) => entry.type === 'chat');
  assert.deepEqual(
    chats.map((entry) => entry.type === 'chat' && entry.label.trim()),
    ['Plan the trip — needs approval', 'Untitled chat']
  );
  assert.deepEqual(
    entries.slice(-2).map((entry) => entry.type),
    ['show', 'quit']
  );
  const starting = menuEntries({ kind: 'starting' }, true);
  assert.equal(starting[0].type === 'label' && starting[0].label, '◌ 后端正在启动…');
});

test('long titles are clipped by character, not byte', () => {
  const clipped = clipTitle('一'.repeat(40), 'x');
  assert.equal(Array.from(clipped).length, 28);
  assert.ok(clipped.endsWith('…'));
});

test('the badge puts an opaque dot in the corner and keeps the far corner', () => {
  const size = 32;
  const bitmap = Buffer.alloc(size * size * 4, 0);
  for (let i = 0; i < bitmap.length; i += 4) bitmap.set([10, 20, 30, 255], i);
  const out = badged(bitmap, size, size);
  const at = (x: number, y: number) => out.subarray((y * size + x) * 4, (y * size + x) * 4 + 4);
  const center = Math.round(size - size * 0.19 - 1);
  assert.deepEqual([...at(center, center)], [...ATTENTION_BGRA, 255]);
  assert.deepEqual([...at(0, 0)], [10, 20, 30, 255]);
  assert.equal(faded(bitmap)[3], Math.round(255 * 0.45));
});
