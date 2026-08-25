import React, { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { CopyButton } from './CopyButton';

/**
 * QR code for the zero-install browser node.
 *
 * Point a phone or TV camera at this and the device joins the mesh — no app,
 * no typing an IP on a phone keyboard, which is the whole friction this
 * removes. The URL is derived from the same pairing address the manual
 * instructions use, so LAN and tailnet each produce the right code.
 */
export function BrowserNodeQR({ host, port }: { host: string; port: number }): React.ReactElement {
  const url = `http://${host}:${port}/node`;
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSrc(null);
    setError(null);
    QRCode.toDataURL(url, { errorCorrectionLevel: 'M', margin: 1, width: 256 })
      .then((dataUrl) => {
        if (!cancelled) setSrc(dataUrl);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return (
    <div className="flex flex-col sm:flex-row items-center gap-4">
      <div className="border-3 border-brutal-black dark:border-white bg-white p-2 shadow-brutal shrink-0">
        {src ? (
          <img src={src} alt={`QR code for ${url}`} className="w-32 h-32 block" />
        ) : (
          <div className="w-32 h-32 flex items-center justify-center text-[10px] text-neutral-400 text-center px-2">
            {error ?? 'Generating…'}
          </div>
        )}
      </div>
      <div className="min-w-0 space-y-2 text-center sm:text-left">
        <p className="text-xs text-neutral-600 dark:text-neutral-400">
          Scan with a phone, tablet, or TV browser. The page turns that screen into a device your
          agent can write to and speak through — nothing is installed.
        </p>
        <div className="flex items-center gap-2 justify-center sm:justify-start">
          <code className="text-[11px] font-mono text-neutral-500 break-all">{url}</code>
          <CopyButton value={url} tone="blue" />
        </div>
      </div>
    </div>
  );
}
