import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import {
  DesktopUpdater,
  isMissingFeed,
  isNewer,
  loadAutoUpdate,
  loadMirror,
  mirrorPath,
  type UpdaterLike,
  type UpdateInfoLike,
} from '../src/updater';

class FakeUpdater implements UpdaterLike {
  autoDownload = true;
  autoInstallOnAppQuit = true;
  feeds: string[] = [];
  installed: [boolean?, boolean?] | null = null;
  failures = 0;
  failure = 'net::ERR_CONNECTION_TIMED_OUT';
  latest = '1.2.0';
  private downloaded: ((info: UpdateInfoLike) => void) | null = null;

  async checkForUpdates(): Promise<{ updateInfo: UpdateInfoLike }> {
    if (this.failures > 0) {
      this.failures -= 1;
      throw new Error(this.failure);
    }
    return { updateInfo: { version: this.latest } };
  }
  async downloadUpdate(): Promise<void> {
    this.downloaded?.({ version: this.latest });
  }
  quitAndInstall(isSilent?: boolean, isForceRunAfter?: boolean): void {
    this.installed = [isSilent, isForceRunAfter];
  }
  setFeedURL(options: { provider: 'generic'; url: string }): void {
    this.feeds.push(options.url);
  }
  on(event: string, listener: (value: never) => void): this {
    if (event === 'update-downloaded') this.downloaded = listener as (info: UpdateInfoLike) => void;
    return this;
  }
}

function dataDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'suzent-updater-'));
}

test('versions compare numerically', () => {
  assert.ok(isNewer('0.28.0', '0.27.3'));
  assert.ok(isNewer('v0.27.10', '0.27.9'));
  assert.ok(!isNewer('0.27.3', '0.27.3'));
  assert.ok(!isNewer('0.26.9', '0.27.0'));
});

test('auto-update is on by default and remembers being turned off', () => {
  const dir = dataDir();
  assert.equal(loadAutoUpdate(dir, {}), true);
  assert.equal(loadAutoUpdate(dir, { SUZENT_AUTO_UPDATE: '0' }), false);
  const fake = new FakeUpdater();
  const updater = new DesktopUpdater(fake, {
    currentVersion: '1.0.0',
    dataDir: dir,
    env: {},
    beforeInstall: async () => {},
  });
  updater.setAutoUpdate(false);
  assert.equal(fake.autoDownload, false);
  assert.equal(fake.autoInstallOnAppQuit, false);
  assert.equal(loadAutoUpdate(dir, {}), false);
});

test('mirror comes from the environment or the data dir, https only', () => {
  const dir = dataDir();
  assert.equal(loadMirror(dir, {}), null);
  assert.equal(loadMirror(dir, { SUZENT_UPDATE_MIRROR: 'http://plain' }), null);
  fs.mkdirSync(path.dirname(mirrorPath(dir)), { recursive: true });
  fs.writeFileSync(mirrorPath(dir), 'https://mirror.example/suzent/\n');
  assert.equal(loadMirror(dir, {}), 'https://mirror.example/suzent');
});

test('check falls back to the mirror when GitHub fails', async () => {
  const dir = dataDir();
  fs.mkdirSync(path.dirname(mirrorPath(dir)), { recursive: true });
  fs.writeFileSync(mirrorPath(dir), 'https://mirror.example/suzent');
  const fake = new FakeUpdater();
  fake.failures = 1;
  const updater = new DesktopUpdater(fake, {
    currentVersion: '1.0.0',
    dataDir: dir,
    env: {},
    beforeInstall: async () => {},
  });
  const status = await updater.check();
  assert.deepEqual(fake.feeds, ['https://mirror.example/suzent']);
  assert.deepEqual(status, {
    current_version: '1.0.0',
    latest_version: '1.2.0',
    update_available: true,
  });
});

test('a failed check without a mirror reports the error', async () => {
  const fake = new FakeUpdater();
  fake.failures = 1;
  const updater = new DesktopUpdater(fake, {
    currentVersion: '1.0.0',
    dataDir: dataDir(),
    env: {},
    beforeInstall: async () => {},
  });
  const status = await updater.check();
  assert.equal(status.update_available, false);
  assert.match(status.error ?? '', /TIMED_OUT/);
});

test('install now downloads, stops the backend, then quits into the installer', async () => {
  const fake = new FakeUpdater();
  const order: string[] = [];
  const updater = new DesktopUpdater(fake, {
    currentVersion: '1.0.0',
    dataDir: dataDir(),
    env: {},
    beforeInstall: async () => {
      order.push('stop backend');
    },
  });
  await assert.rejects(updater.applyStaged(), /No update/);
  await updater.installNow();
  assert.equal(updater.stagedTag(), 'v1.2.0');
  assert.deepEqual(order, ['stop backend']);
  assert.deepEqual(fake.installed, [true, true]);
});

test('install now refuses when already up to date', async () => {
  const fake = new FakeUpdater();
  fake.latest = '1.0.0';
  const updater = new DesktopUpdater(fake, {
    currentVersion: '1.0.0',
    dataDir: dataDir(),
    env: {},
    beforeInstall: async () => {},
  });
  await assert.rejects(updater.installNow(), /up to date/);
  assert.equal(fake.installed, null);
});

test('a release without an update feed means up to date, not an error', async () => {
  const fake = new FakeUpdater();
  fake.failures = 1;
  fake.failure =
    'Cannot find latest-mac.yml in the latest release artifacts (https://github.com/cyzus/suzent/releases/download/v0.27.3/latest-mac.yml): HttpError: 404';
  const updater = new DesktopUpdater(fake, {
    currentVersion: '0.28.0',
    dataDir: dataDir(),
    env: {},
    beforeInstall: async () => {},
  });
  const status = await updater.check();
  assert.equal(status.error, undefined);
  assert.equal(status.update_available, false);
  assert.ok(isMissingFeed('Cannot find latest.yml in the latest release artifacts'));
  assert.ok(!isMissingFeed('net::ERR_CONNECTION_TIMED_OUT'));
});
