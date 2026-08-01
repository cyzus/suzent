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
      '/config': 'http://127.0.0.1:8000',
      '/preferences': 'http://127.0.0.1:8000',
      '/chat': 'http://127.0.0.1:8000',
      '/chats': 'http://127.0.0.1:8000',
      '/plans': 'http://127.0.0.1:8000',
      '/plan': 'http://127.0.0.1:8000',
      '/mcp_servers': 'http://127.0.0.1:8000',
      '/memory': 'http://127.0.0.1:8000',
      '/sandbox': 'http://127.0.0.1:8000',
      '/skills': 'http://127.0.0.1:8000',
      '/files': 'http://127.0.0.1:8000',
    }
  }
});
