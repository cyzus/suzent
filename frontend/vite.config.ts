import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { execFileSync } from 'node:child_process';

function getBuildCommit(): string {
  if (process.env.SUZENT_BUILD_COMMIT) return process.env.SUZENT_BUILD_COMMIT;
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  } catch {
    return 'unknown';
  }
}

// Where dev-mode requests go. The desktop app injects its own port at runtime,
// but a browser tab on the Vite origin has to be told, and the backend worth
// developing against is usually one that is already running (the service or
// the desktop app's, on 25314) rather than a second one started just for this.
const DEV_BACKEND = process.env.VITE_SUZENT_BACKEND || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  define: {
    __FRONTEND_VERSION__: JSON.stringify(process.env.npm_package_version ?? 'unknown'),
    __FRONTEND_BUILD_COMMIT__: JSON.stringify(getBuildCommit()),
    __SUZENT_API_VERSION__: JSON.stringify(1),
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
    }
  }
});
