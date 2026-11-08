import React, { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { useI18n } from '../i18n';
import { isWeb } from '../lib/runtime';
import { BrutalDialog } from './BrutalDialog';

type CloseChoice = 'tray' | 'quit';

/**
 * Asks what closing the window should do. The desktop shell sends
 * `close-prompt` only while the close preference is "ask"; dismissing the
 * dialog keeps the window open.
 */
export function ClosePrompt(): React.ReactElement | null {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [remember, setRemember] = useState(true);

  useEffect(() => {
    if (isWeb()) return;
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    void import('@tauri-apps/api/event').then(({ listen }) =>
      listen<number>('close-prompt', (event) => {
        void invoke('ack_close_prompt', { seq: event.payload });
        setRemember(true);
        setOpen(true);
      }).then((stop) => {
        if (cancelled) stop();
        else unlisten = stop;
      })
    );
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  if (isWeb()) return null;

  const resolve = (choice: CloseChoice) => async () => {
    await invoke('resolve_close', { choice, remember });
  };

  return (
    <BrutalDialog
      open={open}
      title={t('closePrompt.title')}
      message={
        <>
          <p>{t('closePrompt.message')}</p>
          <label className="mt-4 flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="mt-0.5 h-5 w-5 border-2 border-brutal-black accent-brutal-black"
            />
            <span>
              <span className="block text-xs font-bold uppercase">{t('closePrompt.remember')}</span>
              <span className="mt-1 block text-sm text-neutral-600 dark:text-neutral-400">
                {t('closePrompt.rememberHint')}
              </span>
            </span>
          </label>
        </>
      }
      actions={[
        { label: t('closePrompt.quit'), onClick: resolve('quit') },
        { label: t('closePrompt.tray'), tone: 'primary', onClick: resolve('tray') },
      ]}
      onClose={() => setOpen(false)}
    />
  );
}
