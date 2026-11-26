/**
 * Where this Suzent install keeps its Python runtime, its read-only
 * resources and its writable data.
 *
 * A packaged app is self-contained: the installer ships a relocatable CPython
 * with Suzent installed in it next to the bundled config, skills and plugins:
 *
 *   <resources>/runtime/python/   python.exe (Windows) or bin/python3
 *   <resources>/suzent/           config/, skills/, plugins/, extensions/browser/
 *
 * A development run uses the source checkout instead: the repo's `.venv`, or
 * `uv run` when there is none. Writable state always lives in the data dir
 * (`~/.suzent`), never next to the app, which may be read-only.
 */

import fs from 'node:fs';
import path from 'node:path';

export type RuntimeMode = 'bundled' | 'source';

export interface Layout {
  mode: RuntimeMode;
  dataDir: string;
  /** Bundled CPython, or the source checkout's venv python when it exists. */
  python: string | null;
  /** Read-only resources passed as SUZENT_PROJECT_DIR (bundled mode only). */
  resourcesDir: string | null;
  /** The source checkout (source mode only). */
  sourceRoot: string | null;
}

export interface LayoutInput {
  resourcesPath: string;
  appPath: string;
  isPackaged: boolean;
  platform: NodeJS.Platform;
  env: NodeJS.ProcessEnv;
  home: string;
  exists?: (file: string) => boolean;
}

function defaultExists(file: string): boolean {
  try {
    fs.accessSync(file);
    return true;
  } catch {
    return false;
  }
}

export function pythonIn(runtimeDir: string, platform: NodeJS.Platform): string {
  return platform === 'win32'
    ? path.join(runtimeDir, 'python.exe')
    : path.join(runtimeDir, 'bin', 'python3');
}

export function venvPython(root: string, platform: NodeJS.Platform): string {
  return platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
}

export function dataDirFor(env: NodeJS.ProcessEnv, home: string): string {
  const override = env.SUZENT_DATA_DIR?.trim();
  if (override) return override;
  const name = env.SUZENT_DATA_DIR_NAME?.trim() || '.suzent';
  return path.join(home, name);
}

/** Walks up from `start` to the checkout that holds pyproject.toml. */
export function findSourceRoot(
  start: string,
  exists: (file: string) => boolean,
  maxDepth = 6
): string | null {
  let dir = path.resolve(start);
  for (let depth = 0; depth <= maxDepth; depth += 1) {
    if (exists(path.join(dir, 'pyproject.toml'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

export function resolveLayout(input: LayoutInput): Layout {
  const exists = input.exists ?? defaultExists;
  const dataDir = dataDirFor(input.env, input.home);
  const bundledPython = pythonIn(
    path.join(input.resourcesPath, 'runtime', 'python'),
    input.platform
  );
  const forceSource = input.env.SUZENT_DESKTOP_SOURCE === '1';
  if (input.isPackaged && !forceSource && exists(bundledPython)) {
    const resourcesDir = path.join(input.resourcesPath, 'suzent');
    return {
      mode: 'bundled',
      dataDir,
      python: bundledPython,
      resourcesDir: exists(resourcesDir) ? resourcesDir : null,
      sourceRoot: null,
    };
  }

  const explicit = input.env.SUZENT_DIR?.trim();
  const sourceRoot =
    explicit && exists(path.join(explicit, 'pyproject.toml'))
      ? path.resolve(explicit)
      : findSourceRoot(input.appPath, exists);
  const python = sourceRoot ? venvPython(sourceRoot, input.platform) : null;
  return {
    mode: 'source',
    dataDir,
    python: python && exists(python) ? python : null,
    resourcesDir: null,
    sourceRoot,
  };
}

/**
 * Environment for any bundled-python process (the backend and CLI calls):
 * resources via SUZENT_PROJECT_DIR, no bytecode written into the install dir,
 * no user site-packages, and caches kept in the data dir.
 */
export function bundledPythonEnv(layout: Layout, env: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const next: NodeJS.ProcessEnv = { ...env, SUZENT_DATA_DIR: layout.dataDir };
  if (layout.mode !== 'bundled') return next;
  next.PYTHONDONTWRITEBYTECODE = '1';
  next.PYTHONNOUSERSITE = '1';
  next.SUZENT_PACKAGED = '1';
  if (layout.resourcesDir) next.SUZENT_PROJECT_DIR = layout.resourcesDir;
  next.PLAYWRIGHT_BROWSERS_PATH ??= path.join(layout.dataDir, 'ms-playwright');
  next.UV_CACHE_DIR ??= path.join(layout.dataDir, 'uv-cache');
  return next;
}
