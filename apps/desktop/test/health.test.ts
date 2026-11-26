import assert from 'node:assert/strict';
import { test } from 'node:test';

import { identityProblem, mayAttach } from '../src/health';
import type { Layout } from '../src/layout';

const bundled: Layout = {
  mode: 'bundled',
  dataDir: '/d',
  python: '/p',
  resourcesDir: null,
  sourceRoot: null,
};
const source: Layout = {
  mode: 'source',
  dataDir: '/d',
  python: null,
  resourcesDir: null,
  sourceRoot: '/repo',
};

test('a bundled app shares only a bundled backend of its own version', () => {
  const ok = { app: 'suzent', status: 'ok', version: '1.2.3', source_root: null };
  assert.equal(identityProblem(ok, bundled, '1.2.3', 25314), null);
  assert.match(
    identityProblem({ ...ok, version: '1.2.2' }, bundled, '1.2.3', 25314) ?? '',
    /1\.2\.2/
  );
  assert.equal(mayAttach({ ...ok, source_root: '/repo' }, bundled), false);
  assert.equal(mayAttach(ok, bundled), true);
});

test('a development run shares only its own checkout', () => {
  const ok = { app: 'suzent', status: 'ok', version: '1.2.3', source_root: '/repo' };
  assert.equal(identityProblem(ok, source, '1.2.3', 25314, 'linux'), null);
  const other = identityProblem({ ...ok, source_root: '/other' }, source, '1.2.3', 25314, 'linux');
  assert.match(other ?? '', /\/other/);
  assert.notEqual(identityProblem({ app: 'nope', status: 'ok' }, source, '1.2.3', 1), null);
});

test('Windows compares checkout paths case-insensitively', () => {
  const ok = { app: 'suzent', status: 'ok', version: '1', source_root: 'C:\\Repo' };
  const layout = { ...source, sourceRoot: 'c:\\repo' };
  assert.equal(identityProblem(ok, layout, '1', 1, 'win32'), null);
});
