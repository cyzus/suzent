// allow prismjs imports without types
declare module 'prismjs';

interface Window {
    __TAURI__?: {
        window: {
            getCurrentWindow: () => {
                minimize: () => Promise<void>;
                toggleMaximize: () => Promise<void>;
                close: () => Promise<void>;
                startDragging: () => Promise<void>;
            };
        };
    };
    __SUZENT_BACKEND_PORT__?: number;
}
