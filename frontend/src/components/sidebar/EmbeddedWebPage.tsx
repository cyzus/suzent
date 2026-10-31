import { useEffect, useRef, useState } from 'react';
import { isTauri } from '@tauri-apps/api/core';
import { LogicalPosition, LogicalSize } from '@tauri-apps/api/dpi';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { WebviewWindow } from '@tauri-apps/api/webviewWindow';
import { useI18n } from '../../i18n';

let nextWebviewId = 0;

interface EmbeddedWebPageProps {
  url: string;
  visible: boolean;
}

export function EmbeddedWebPage({ url, visible }: EmbeddedWebPageProps): React.ReactElement {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  // Wayland cannot place top-level windows, so Linux keeps the iframe.
  const native = isTauri() && !navigator.userAgent.includes('Linux');

  useEffect(() => {
    if (!native || !visible || !containerRef.current) return;

    setError(null);
    const container = containerRef.current;
    const parent = getCurrentWindow();
    // A parented undecorated window instead of an in-window child webview: child
    // webviews need Tauri's `unstable` feature, which makes the app's own webview
    // a child too, and on macOS wry then lets arrow keys type U+F700-range glyphs.
    let page: WebviewWindow | null = null;
    let disposed = false;
    let created = false;
    let lastBounds = '';

    const screenBounds = async (): Promise<{
      x: number;
      y: number;
      width: number;
      height: number;
    }> => {
      const [origin, scale] = await Promise.all([parent.innerPosition(), parent.scaleFactor()]);
      const { x, y } = origin.toLogical(scale);
      const rect = container.getBoundingClientRect();
      return { x: x + rect.left, y: y + rect.top, width: rect.width, height: rect.height };
    };

    const syncBounds = async (): Promise<void> => {
      if (!created || disposed || !page) return;
      const bounds = await screenBounds();
      const key = `${bounds.x},${bounds.y},${bounds.width},${bounds.height}`;
      if (key === lastBounds || bounds.width < 1 || bounds.height < 1) return;
      lastBounds = key;
      await Promise.all([
        page.setPosition(new LogicalPosition(bounds.x, bounds.y)),
        page.setSize(new LogicalSize(bounds.width, bounds.height)),
      ]);
    };
    const sync = (): void => {
      syncBounds().catch((reason: unknown) => setError(String(reason)));
    };

    void screenBounds().then((bounds) => {
      if (disposed) return;
      page = new WebviewWindow(`web-page-${++nextWebviewId}`, {
        url,
        parent,
        x: bounds.x,
        y: bounds.y,
        width: Math.max(1, bounds.width),
        height: Math.max(1, bounds.height),
        decorations: false,
        resizable: false,
        shadow: false,
        skipTaskbar: true,
        focus: false,
      });
      void page.once('tauri://created', () => {
        created = true;
        if (disposed) {
          void page?.close();
        } else {
          sync();
        }
      });
      void page.once<string>('tauri://error', (event) => {
        if (!disposed) setError(String(event.payload));
      });
    });

    const observer = new ResizeObserver(sync);
    observer.observe(container);
    const timer = window.setInterval(sync, 100);
    return () => {
      disposed = true;
      observer.disconnect();
      window.clearInterval(timer);
      if (created) void page?.close();
    };
  }, [native, url, visible]);

  if (!native) {
    return visible ? (
      <iframe
        src={url}
        title={t('webActivities.webPage')}
        className="w-full h-full border-0 bg-white"
      />
    ) : (
      <div className="w-full h-full bg-white" />
    );
  }

  return (
    <div ref={containerRef} className="w-full h-full bg-white dark:bg-zinc-900">
      {error && (
        <p role="alert" className="p-4 text-sm text-red-700 dark:text-red-300">
          {t('webActivities.embedError')}
          <span className="block mt-2 text-xs break-words">{error}</span>
        </p>
      )}
    </div>
  );
}
