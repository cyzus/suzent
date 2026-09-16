/**
 * Pick a directory *on the machine running the backend*.
 *
 * The desktop shell has a native dialog for this. A browser cannot expose host
 * paths — `<input type="file">` hands back opaque File objects, not the path
 * the backend needs to mount — so web mode browses the host through the
 * backend's own `/system/files` endpoint instead.
 *
 * Both modes are awaited the same way, so call sites stay a single line.
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import { getApiBase } from './api';
import { isWeb } from './runtime';
import { getInitialLocale, tForLocale } from '../i18n';

interface HostEntry {
  name: string;
  is_dir: boolean;
}

interface HostListing {
  path: string;
  items: HostEntry[];
  error?: string;
}

async function listHostDirectory(path: string): Promise<HostListing> {
  const response = await fetch(`${getApiBase()}/system/files?path=${encodeURIComponent(path)}`);
  const payload = (await response.json()) as HostListing;
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function joinHostPath(parent: string, name: string): string {
  // Windows drive roots already carry their separator ("C:\"); everything else
  // needs one, and the backend resolves whichever slash we send.
  if (!parent) return name;
  if (/[\\/]$/.test(parent)) return `${parent}${name}`;
  return `${parent}${parent.includes('\\') ? '\\' : '/'}${name}`;
}

function parentHostPath(path: string): string | null {
  const trimmed = path.replace(/[\\/]+$/, '');
  const cut = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
  if (cut < 0) return '';
  if (cut === 0) return '/';
  const parent = trimmed.slice(0, cut);
  // "C:" is not browsable; the drive root is "C:\".
  return /^[A-Za-z]:$/.test(parent) ? `${parent}\\` : parent;
}

const BUTTON_CLASS =
  'px-3 py-1.5 border-2 border-brutal-black bg-white text-xs font-bold uppercase ' +
  'shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:bg-neutral-100 disabled:opacity-40';

function HostDirectoryPicker(props: {
  multiple: boolean;
  onResolve: (value: string | string[] | null) => void;
}): React.ReactElement {
  const t = (key: string) => tForLocale(getInitialLocale(), key);
  const [path, setPath] = React.useState('');
  const [listing, setListing] = React.useState<HostListing | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelected] = React.useState<string[]>([]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listHostDirectory(path)
      .then((result) => {
        if (cancelled) return;
        setListing(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(String(err instanceof Error ? err.message : err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  const currentPath = listing?.path ?? path;
  const parent = currentPath ? parentHostPath(currentPath) : null;
  const directories = (listing?.items ?? []).filter((item) => item.is_dir);

  const toggle = (full: string) => {
    if (!props.multiple) {
      setSelected([full]);
      return;
    }
    setSelected((prev) =>
      prev.includes(full) ? prev.filter((p) => p !== full) : [...prev, full]
    );
  };

  const confirm = () => {
    // Confirming with nothing ticked means "use the folder I'm looking at".
    const chosen = selected.length > 0 ? selected : currentPath ? [currentPath] : [];
    if (chosen.length === 0) {
      props.onResolve(null);
      return;
    }
    props.onResolve(props.multiple ? chosen : chosen[0]);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 p-4"
      onClick={() => props.onResolve(null)}
    >
      <div
        className="flex h-[32rem] w-full max-w-lg flex-col border-4 border-brutal-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b-4 border-brutal-black px-4 py-3">
          <h2 className="font-brutal text-lg font-black uppercase">{t('hostPicker.title')}</h2>
          <p className="mt-1 truncate font-mono text-xs text-neutral-600">
            {currentPath || t('hostPicker.roots')}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <p className="p-4 text-xs font-bold uppercase">{t('hostPicker.loading')}</p>
          ) : error ? (
            <p className="p-4 text-xs font-bold text-red-600">{error}</p>
          ) : (
            <ul>
              {parent !== null && (
                <li>
                  <button
                    className="w-full px-4 py-2 text-left font-mono text-xs hover:bg-neutral-100"
                    onClick={() => setPath(parent)}
                  >
                    ../
                  </button>
                </li>
              )}
              {directories.map((entry) => {
                const full = joinHostPath(currentPath, entry.name);
                return (
                  <li key={full} className="flex items-center gap-2 px-4 hover:bg-neutral-100">
                    <input
                      type="checkbox"
                      checked={selected.includes(full)}
                      onChange={() => toggle(full)}
                    />
                    <button
                      className="flex-1 py-2 text-left font-mono text-xs"
                      onClick={() => setPath(full)}
                    >
                      {entry.name}/
                    </button>
                  </li>
                );
              })}
              {directories.length === 0 && (
                <p className="p-4 text-xs text-neutral-500">{t('hostPicker.empty')}</p>
              )}
            </ul>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t-4 border-brutal-black px-4 py-3">
          <button className={BUTTON_CLASS} onClick={() => props.onResolve(null)}>
            {t('hostPicker.cancel')}
          </button>
          <button className={BUTTON_CLASS} onClick={confirm} disabled={loading}>
            {t('hostPicker.select')}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export async function pickHostDirectory(options: {
  multiple: boolean;
}): Promise<string | string[] | null> {
  if (!isWeb()) {
    const { open } = await import('@tauri-apps/plugin-dialog');
    return open({ directory: true, multiple: options.multiple });
  }

  return new Promise((resolve) => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    const finish = (value: string | string[] | null) => {
      root.unmount();
      host.remove();
      resolve(value);
    };
    root.render(<HostDirectoryPicker multiple={options.multiple} onResolve={finish} />);
  });
}
