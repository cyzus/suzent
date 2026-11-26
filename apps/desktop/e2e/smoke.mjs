// End-to-end smoke test: launch the desktop app, let it start its backend,
// check the bridge and the window, then quit and make sure the backend went
// with it. Usage: node e2e/smoke.mjs [--app <path to packaged executable>]
// [--screenshot <file>]. Without --app it runs this checkout in development
// mode (build first with `npm run build`).
import { _electron as electron } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const here = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(here, '..');
const { values } = parseArgs({
  options: { app: { type: 'string' }, screenshot: { type: 'string' } },
});

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'suzent-e2e-'));
const require = (await import('node:module')).createRequire(import.meta.url);
const executablePath = values.app ?? require('electron');
const args = values.app ? [] : [appDir];
if (process.platform === 'linux') args.unshift('--no-sandbox');

const fail = (message) => {
  console.error(`FAIL: ${message}`);
  process.exitCode = 1;
};

const app = await electron.launch({
  executablePath,
  args,
  env: { ...process.env, SUZENT_DATA_DIR: dataDir, SUZENT_PORT: '0' },
  timeout: 120_000,
});
app.process().stdout?.on('data', (chunk) => process.stdout.write(`[main] ${chunk}`));
app.process().stderr?.on('data', (chunk) => process.stdout.write(`[main] ${chunk}`));

try {
  const page = await app.firstWindow();
  const started = Date.now();
  // A first bundled start compiles nothing (bytecode ships precompiled), but
  // a cold disk or antivirus scan can still make it slow.
  await page.waitForFunction(() => typeof window.__SUZENT_BACKEND_PORT__ === 'number', null, {
    timeout: 300_000,
  });
  const port = await page.evaluate(() => window.__SUZENT_BACKEND_PORT__);
  console.log(`backend ready on ${port} after ${Date.now() - started} ms`);

  const health = await (await fetch(`http://127.0.0.1:${port}/health`)).json();
  if (health.app !== 'suzent' || health.status !== 'ok')
    fail(`unexpected health ${JSON.stringify(health)}`);

  const cors = await page.evaluate(
    async (p) => (await fetch(`http://127.0.0.1:${p}/health`)).ok,
    port
  );
  if (!cors) fail('the page cannot reach its backend (CORS)');

  const about = await page.evaluate(() => window.suzentDesktop.invoke('get_desktop_about'));
  console.log('about', JSON.stringify(about));
  if (about.app_version !== health.version)
    fail(`app ${about.app_version} != backend ${health.version}`);
  if (values.app && about.runtime !== 'bundled')
    fail(`packaged app runs a ${about.runtime} runtime`);

  await page.waitForFunction(() => document.documentElement.classList.contains('electron-shell'));
  await page.waitForTimeout(3000);
  const visible = await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows()[0]?.isVisible()
  );
  if (!visible) fail('the window never became visible (frontend_ready)');
  if (values.screenshot) await page.screenshot({ path: values.screenshot });

  await app.evaluate(({ app: electronApp }) => electronApp.quit());
  await app.waitForEvent('close', { timeout: 30_000 }).catch(() => undefined);
  const deadline = Date.now() + 20_000;
  let stopped = false;
  while (Date.now() < deadline) {
    try {
      await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(500) });
    } catch {
      stopped = true;
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  if (!stopped) fail('the backend kept running after quit');
} catch (error) {
  fail(error instanceof Error ? error.stack : String(error));
  const log = path.join(dataDir, 'runtime', 'server.log');
  if (fs.existsSync(log)) console.error(fs.readFileSync(log, 'utf8').slice(-4000));
  await app.close().catch(() => undefined);
}
if (!process.exitCode) console.log('smoke test passed');
