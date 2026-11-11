import React, { useState } from 'react';
import { ArrowDownTrayIcon, CheckIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import type { A2UISurface } from '../../types/a2ui';
import { getApiBase } from '../../lib/api';
import { useChatStore } from '../../hooks/useChatStore';
import { useI18n } from '../../i18n';
import { BrutalIconButton } from '../BrutalButton';

type SaveState = { status: 'idle' } | { status: 'saved'; path: string } | { status: 'failed' };

/** Saves a canvas surface as an HTML page in the project's artifacts/ folder. */
export function SaveSurfaceButton({ surface }: { surface: A2UISurface }): React.ReactElement {
  const { t } = useI18n();
  const { currentChatId } = useChatStore();
  const [state, setState] = useState<SaveState>({ status: 'idle' });

  const save = async (): Promise<void> => {
    if (!currentChatId) return;
    try {
      const response = await fetch(`${getApiBase()}/canvas/${currentChatId}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ surface }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as { workspace_path: string };
      setState({ status: 'saved', path: data.workspace_path.replace(/^\/workspace\//, '') });
    } catch {
      setState({ status: 'failed' });
    }
    window.setTimeout(() => setState({ status: 'idle' }), 2500);
  };

  const label =
    state.status === 'saved'
      ? t('a2uiSurface.savedTo', { path: state.path })
      : state.status === 'failed'
        ? t('a2uiSurface.saveFailed')
        : t('a2uiSurface.saveAsFile');
  const Icon =
    state.status === 'saved'
      ? CheckIcon
      : state.status === 'failed'
        ? ExclamationTriangleIcon
        : ArrowDownTrayIcon;

  return (
    <BrutalIconButton
      type="button"
      onClick={() => void save()}
      disabled={!currentChatId}
      label={label}
      className="shrink-0 self-start"
    >
      <Icon className="h-4 w-4 stroke-2" />
    </BrutalIconButton>
  );
}
