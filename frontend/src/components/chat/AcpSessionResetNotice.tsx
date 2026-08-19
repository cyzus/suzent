import React from 'react';
import { useI18n } from '../../i18n';
import type { AcpNotice } from '../../types/agui';

/**
 * Tells the user that resuming an ACP session started a fresh one instead.
 *
 * Without this the agent simply appears to have forgotten the conversation.
 */
export const AcpSessionResetNotice: React.FC<{ notice: AcpNotice }> = ({ notice }) => {
  const { t } = useI18n();
  return (
    <div className="my-2 border-2 border-dashed border-neutral-400 dark:border-zinc-600 px-2 py-1.5">
      <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-neutral-500">
        {t('acp.sessionReset.header')}
      </div>
      <div className="text-[11px] font-mono text-neutral-600 dark:text-neutral-400 break-words">
        {t('acp.sessionReset.body', { agent: notice.agentId || 'agent' })}
      </div>
    </div>
  );
};
