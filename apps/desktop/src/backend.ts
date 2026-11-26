/**
 * The Python backend the window talks to: attached (a background service or a
 * backend someone started by hand) or owned (a child this app started and
 * stops on quit).
 */

import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

import { fetchHealth, identityProblem, mayAttach, SERVICE_PORT } from './health';
import { bundledPythonEnv, type Layout } from './layout';

export interface StartupError {
  message: string;
  /** False when starting again cannot succeed until the user acts on `message`. */
  recoverable: boolean;
}

export class StartupFailure extends Error {
  constructor(
    message: string,
    readonly recoverable = true
  ) {
    super(message);
  }

  toJSON(): StartupError {
    return { message: this.message, recoverable: this.recoverable };
  }
}

// The first launch compiles bytecode for every dependency, which with
// antivirus scanning can take minutes on Windows. A backend that dies is
// still reported at once, so the long wait only covers a slow start.
const PORT_FILE_TIMEOUT_MS = 300_000;
const HEALTH_TIMEOUT_MS = 120_000;
const STOP_GRACE_MS = 15_000;

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export interface BackendOptions {
  layout: Layout;
  appVersion: string;
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  /** `uv` for a source checkout without a .venv. */
  uv?: string;
  /** Aborting kills a backend that is still starting. */
  signal?: AbortSignal;
}

export class Backend {
  private child: ChildProcess | null = null;
  private exited = false;
  private controlToken: string | null = null;

  private constructor(
    readonly port: number,
    child: ChildProcess | null,
    controlToken: string | null
  ) {
    this.child = child;
    this.controlToken = controlToken;
    child?.once('exit', () => {
      this.exited = true;
    });
  }

  get owned(): boolean {
    return this.child !== null;
  }

  static attached(port: number): Backend {
    return new Backend(port, null, null);
  }

  async isRunning(): Promise<boolean> {
    if (this.child) return !this.exited;
    return (await fetchHealth(this.port)) !== null;
  }

  async stop(): Promise<void> {
    const child = this.child;
    this.child = null;
    if (!child || this.exited) return;
    const token = this.controlToken;
    this.controlToken = null;
    if (token) {
      try {
        await fetch(`http://127.0.0.1:${this.port}/service/stop`, {
          method: 'POST',
          headers: { 'X-Suzent-Service-Token': token },
          signal: AbortSignal.timeout(2000),
        });
      } catch {
        // Fall through to the wait and the kill below.
      }
      const deadline = Date.now() + STOP_GRACE_MS;
      while (Date.now() < deadline && !this.exited) await sleep(100);
    }
    if (!this.exited) killTree(child);
  }

  /**
   * Attaches to a healthy backend on `port` that belongs to this install.
   * Returns null when nothing answers there; throws a blocked failure when a
   * different Suzent holds the port.
   */
  static async attachIfMatching(port: number, options: BackendOptions): Promise<Backend | null> {
    const payload = await fetchHealth(port);
    if (!payload || !mayAttach(payload, options.layout)) return null;
    const problem = identityProblem(
      payload,
      options.layout,
      options.appVersion,
      port,
      options.platform
    );
    if (problem) throw new StartupFailure(problem, false);
    return Backend.attached(port);
  }

  static async start(hintPort: number, options: BackendOptions): Promise<Backend> {
    const { layout } = options;
    const platform = options.platform ?? process.platform;
    const runtimeDir = path.join(layout.dataDir, 'runtime');
    fs.mkdirSync(runtimeDir, { recursive: true });
    const portFile = path.join(runtimeDir, 'server.port');
    fs.rmSync(portFile, { force: true });
    const logFile = path.join(runtimeDir, 'server.log');
    const log = fs.openSync(logFile, 'a');

    const [command, args, cwd] = backendCommand(layout, options.uv ?? 'uv');
    const controlToken = randomUUID().replaceAll('-', '');
    const env = {
      ...bundledPythonEnv(layout, options.env ?? process.env),
      SUZENT_PORT: String(hintPort),
      SUZENT_HOST: '127.0.0.1',
      SUZENT_RUN_MODE: 'desktop-child',
      SUZENT_SERVICE_CONTROL_TOKEN: controlToken,
      // On Windows the backend ignores stdin EOF; this makes it exit with us.
      SUZENT_PARENT_PID: String(process.pid),
      PYTHONUNBUFFERED: '1',
      LOG_FILE: logFile,
    };
    let child: ChildProcess;
    try {
      child = spawn(command, args, {
        cwd,
        env,
        // The backend watches stdin and exits when this app goes away.
        stdio: ['pipe', log, log],
        windowsHide: true,
      });
    } finally {
      fs.closeSync(log);
    }
    const spawnError = new Promise<never>((_, reject) => {
      child.once('error', (error) =>
        reject(new StartupFailure(`Failed to start backend: ${error.message}`))
      );
      const signal = options.signal;
      if (signal?.aborted) reject(new StartupFailure('Backend start was cancelled'));
      signal?.addEventListener('abort', () =>
        reject(new StartupFailure('Backend start was cancelled'))
      );
    });
    const backendPromise = (async () => {
      const port = await waitForPortFile(portFile, child, logFile);
      console.log(`Backend (pid ${child.pid}) reported port ${port}; waiting for /health`);
      const backend = new Backend(port, child, controlToken);
      await waitForHealth(backend, options, platform);
      return backend;
    })();
    try {
      return await Promise.race([backendPromise, spawnError]);
    } catch (error) {
      if (child.exitCode === null) killTree(child);
      throw error;
    }
  }

  /** Attaches to the service (or SUZENT_PORT), else starts an owned backend. */
  static async connect(options: BackendOptions): Promise<Backend> {
    const env = options.env ?? process.env;
    const configured = Number.parseInt(env.SUZENT_PORT ?? '0', 10) || 0;
    if (options.layout.mode === 'source' && !options.layout.sourceRoot) {
      throw new StartupFailure(
        'This development build could not find the Suzent source checkout. Set SUZENT_DIR to it.',
        false
      );
    }
    const attached = await Backend.attachIfMatching(configured || SERVICE_PORT, options);
    if (attached) return attached;
    console.log(`No backend to attach to on ${configured || SERVICE_PORT}; starting one`);
    return Backend.start(configured, options);
  }
}

/**
 * On Windows killing a process leaves its children running, so a backend
 * killed mid-shutdown would orphan its git, MCP server and browser processes.
 */
export function killTree(child: ChildProcess, platform: NodeJS.Platform = process.platform): void {
  if (platform === 'win32' && child.pid) {
    const result = spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
      windowsHide: true,
      stdio: 'ignore',
    });
    if (result.status === 0) return;
  }
  child.kill();
}

export function backendCommand(layout: Layout, uv: string): [string, string[], string] {
  if (layout.mode === 'bundled' && layout.python) {
    // There is no repo in a bundled install; run from the data dir.
    return [layout.python, ['-m', 'suzent.server'], layout.dataDir];
  }
  const root = layout.sourceRoot ?? process.cwd();
  if (layout.python) return [layout.python, ['-m', 'suzent.server'], root];
  return [uv, ['run', '--no-sync', 'python', '-m', 'suzent.server'], root];
}

async function waitForPortFile(
  portFile: string,
  child: ChildProcess,
  logFile: string
): Promise<number> {
  const deadline = Date.now() + PORT_FILE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const port = Number.parseInt(fs.readFileSync(portFile, 'utf8').trim(), 10);
      if (Number.isInteger(port) && port > 0 && port < 65536) return port;
    } catch {
      // Not written yet.
    }
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new StartupFailure(
        `Backend exited with ${child.exitCode ?? child.signalCode} before reporting a port. Check ${logFile} for details.`
      );
    }
    await sleep(200);
  }
  throw new StartupFailure('Timed out waiting for backend to write server.port');
}

async function waitForHealth(
  backend: Backend,
  options: BackendOptions,
  platform: NodeJS.Platform
): Promise<void> {
  const started = Date.now();
  const deadline = started + HEALTH_TIMEOUT_MS;
  let lastNote = started;
  while (Date.now() < deadline) {
    const payload = await fetchHealth(backend.port, 2000);
    if (!payload && Date.now() - lastNote >= 10_000) {
      lastNote = Date.now();
      console.log(
        `Still no /health answer on ${backend.port} after ${Math.round((lastNote - started) / 1000)}s`
      );
    }
    if (payload) {
      const problem = identityProblem(
        payload,
        options.layout,
        options.appVersion,
        backend.port,
        platform
      );
      if (problem) throw new StartupFailure(problem, false);
      return;
    }
    if (!(await backend.isRunning())) {
      throw new StartupFailure('Backend exited while waiting for its health check');
    }
    await sleep(500);
  }
  throw new StartupFailure(
    `Backend failed health check within ${HEALTH_TIMEOUT_MS / 1000} seconds`
  );
}
