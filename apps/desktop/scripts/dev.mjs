// Starts the frontend's Vite server (unless one is already up) and opens the
// shell on it, so frontend edits hot-reload like `tauri dev`.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(here, '..');
const frontendDir = path.resolve(appDir, '../../frontend');
const devUrl = process.env.SUZENT_DEV_URL || 'http://127.0.0.1:18080';
const electron = createRequire(import.meta.url)('electron');

async function reachable(url) {
  try {
    await fetch(url, { signal: AbortSignal.timeout(1000) });
    return true;
  } catch {
    return false;
  }
}

async function waitFor(url, child) {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error('The frontend dev server exited before it was ready');
    if (await reachable(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`The frontend dev server did not answer at ${url}`);
}

function stop(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' });
  } else {
    try {
      process.kill(-child.pid, 'SIGTERM');
    } catch {
      child.kill('SIGTERM');
    }
  }
}

let vite;
if (await reachable(devUrl)) {
  console.log(`Using the frontend dev server already running at ${devUrl}`);
} else {
  console.log('Starting the frontend dev server…');
  vite = spawn('npm', ['run', 'dev'], {
    cwd: frontendDir,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    detached: process.platform !== 'win32',
  });
  await waitFor(devUrl, vite).catch((error) => {
    stop(vite);
    console.error(error.message);
    process.exit(1);
  });
}

const shell = spawn(electron, ['.', ...process.argv.slice(2)], {
  cwd: appDir,
  stdio: 'inherit',
  env: { ...process.env, SUZENT_DEV_URL: devUrl },
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    shell.kill(signal);
    stop(vite);
  });
}

shell.on('exit', (code) => {
  stop(vite);
  process.exit(code ?? 0);
});
