import { useEffect, useRef, useState } from 'react';
import { isTauri } from '@tauri-apps/api/core';
import { LogicalPosition, LogicalSize } from '@tauri-apps/api/dpi';
import { Webview } from '@tauri-apps/api/webview';
import { getCurrentWindow } from '@tauri-apps/api/window';
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
  const native = isTauri();

  useEffect(() => {
    if (!native || !visible || !containerRef.current) return;

    setError(null);
    const container = containerRef.current;
    const rect = container.getBoundingClientRect();
    const webview = new Webview(getCurrentWindow(), `web-page-${++nextWebviewId}`, {
      url,
      x: rect.left,
      y: rect.top,
      width: Math.max(1, rect.width),
      height: Math.max(1, rect.height),
      focus: false,
    });
    let disposed = false;
    let created = false;
    let lastBounds = '';

    const syncBounds = (): void => {
      if (!created || disposed) return;
      const bounds = container.getBoundingClientRect();
      const key = `${bounds.left},${bounds.top},${bounds.width},${bounds.height}`;
      if (key === lastBounds || bounds.width < 1 || bounds.height < 1) return;
      lastBounds = key;
      void Promise.all([
        webview.setPosition(new LogicalPosition(bounds.left, bounds.top)),
        webview.setSize(new LogicalSize(bounds.width, bounds.height)),
      ]).catch((reason: unknown) => setError(String(reason)));
    };

    void webview.once('tauri://created', () => {
      created = true;
      if (disposed) {
        void webview.close();
      } else {
        syncBounds();
      }
    });
    void webview.once<string>('tauri://error', (event) => {
      if (!disposed) setError(String(event.payload));
    });

    const observer = new ResizeObserver(syncBounds);
    observer.observe(container);
    const timer = window.setInterval(syncBounds, 100);
    return () => {
      disposed = true;
      observer.disconnect();
      window.clearInterval(timer);
      if (created) void webview.close();
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
