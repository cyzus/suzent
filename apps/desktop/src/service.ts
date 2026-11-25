/** Settings > Background service: the backend running at login without the window. */

import { execFile } from 'node:child_process';

import { bundledPythonEnv, type Layout } from './layout';

export function serviceCommand(
  layout: Layout,
  uv: string,
  args: string[]
): { command: string; args: string[]; cwd: string } {
  const cwd = layout.sourceRoot ?? layout.dataDir;
  if (layout.python) {
    return { command: layout.python, args: ['-m', 'suzent.cli', 'service', ...args], cwd };
  }
  return { command: uv, args: ['run', '--no-sync', 'suzent', 'service', ...args], cwd };
}

export function runServiceCli(
  layout: Layout,
  uv: string,
  args: string[],
  env: NodeJS.ProcessEnv = process.env
): Promise<string> {
  const { command, args: argv, cwd } = serviceCommand(layout, uv, args);
  return new Promise((resolve, reject) => {
    execFile(
      command,
      argv,
      { cwd, env: bundledPythonEnv(layout, env), windowsHide: true, timeout: 60_000 },
      (error, stdout, stderr) => {
        const out = stdout.toString().trim();
        if (!error) {
          resolve(out);
          return;
        }
        const err = stderr.toString().trim();
        reject(new Error(err || out || error.message));
      }
    );
  });
}

/** The CLI may log before its JSON; return the JSON object only. */
export function extractJsonPayload(output: string): string {
  const start = output.indexOf('{');
  if (start < 0) throw new Error('Service status did not contain JSON.');
  const payload = output.slice(start);
  JSON.parse(payload);
  return payload;
}
