import assert from 'node:assert/strict';
import path from 'node:path';
import { test } from 'node:test';

import { storeHelperPath, storeServiceStatus } from '../src/storeStartup';

test('the store helper sits in resources\\bin', () => {
  assert.equal(storeHelperPath('C:\\pkg\\resources'), path.join('C:\\pkg\\resources', 'bin', 'suzent.exe'));
});

test('start at login reads like a service status', () => {
  const on = JSON.parse(
    storeServiceStatus({ state: 'enabled', enabled: true, error: null }, { port: 25314, ready: true }, '1.2.3')
  );
  assert.equal(on.installed, true);
  assert.equal(on.autostart, true);
  assert.equal(on.ready, true);
  assert.equal(on.port, 25314);
  assert.equal(on.version, '1.2.3');

  const blocked = JSON.parse(
    storeServiceStatus(
      { state: 'disabled_by_user', enabled: false, error: 'Turn Suzent back on there.' },
      null,
      '1.2.3'
    )
  );
  assert.equal(blocked.installed, false);
  assert.equal(blocked.running, false);
  assert.equal(blocked.version, null);
  assert.equal(blocked.error, 'Turn Suzent back on there.');
});
