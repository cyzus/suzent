/// <reference types="vite/client" />

declare const __FRONTEND_VERSION__: string;

interface Window {
  __SUZENT_BACKEND_PORT__?: number;
  __TAURI__?: any;
}
