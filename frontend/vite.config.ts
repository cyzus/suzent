import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
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
