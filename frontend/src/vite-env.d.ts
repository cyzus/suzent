/// <reference types="vite/client" />

declare const __FRONTEND_VERSION__: string;
declare const __FRONTEND_BUILD_COMMIT__: string;
declare const __SUZENT_API_VERSION__: number;

interface Window {
  __SUZENT_BACKEND_PORT__?: number;
  __TAURI__?: any;
}
