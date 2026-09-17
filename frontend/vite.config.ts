import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { execFileSync } from 'node:child_process';

import { resolveDevBackend } from './devBackend.ts';

function getBuildCommit(): string {
  if (process.env.SUZENT_BUILD_COMMIT) return process.env.SUZENT_BUILD_COMMIT;
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  } catch {
    return 'unknown';
  }
}

export default defineConfig(async ({ command }) => {
  // Where dev-mode requests go. Discovered rather than configured: a browser
  // tab on the Vite origin has no equivalent of the port the Tauri shell
  // injects, and making that the developer's problem meant prefixing every
  // `npm run dev` with an environment variable.
  //
  // Vitest loads this config too, and has no backend to look for.
  const serving = command === 'serve' && !process.env.VITEST;
  const backend = serving ? await resolveDevBackend() : { url: '', source: 'build' };
  const DEV_BACKEND = backend.url;
  // Printed, not silent: the search can land on the wrong backend, and the
  // symptom of that is data from somewhere unexpected rather than an error.
  if (serving) console.log(`\n  suzent backend  ${backend.url}  (${backend.source})\n`);

  return {
    plugins: [react()],
    define: {
      __FRONTEND_VERSION__: JSON.stringify(process.env.npm_package_version ?? 'unknown'),
      __FRONTEND_BUILD_COMMIT__: JSON.stringify(getBuildCommit()),
      __SUZENT_API_VERSION__: JSON.stringify(1),
      // The client reads this the same way it would read the environment
      // variable, so an explicit VITE_SUZENT_BACKEND still wins and the
      // production build still gets nothing.
      'import.meta.env.VITE_SUZENT_BACKEND': JSON.stringify(DEV_BACKEND),
    },
    server: {
      host: '127.0.0.1',
      // Use a high fixed port outside current Windows dynamic range/exclusions.
      port: 18080,
      proxy: {
        // Proxy API routes to backend
        '/config': DEV_BACKEND,
        '/preferences': DEV_BACKEND,
        '/chat': DEV_BACKEND,
        '/chats': DEV_BACKEND,
        '/plans': DEV_BACKEND,
        '/plan': DEV_BACKEND,
        '/mcp_servers': DEV_BACKEND,
        '/memory': DEV_BACKEND,
        '/sandbox': DEV_BACKEND,
        '/skills': DEV_BACKEND,
        '/files': DEV_BACKEND,
      },
    },
  };
});
