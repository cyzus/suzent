import { ArrowPathIcon } from '@heroicons/react/24/outline';
import React from 'react';
import { useI18n } from '../../i18n';
import type { ModelRecoveryNotice as Notice } from '../../types/agui';

const REASONS = new Set(['timeout', 'connection', 'rate_limit', 'overloaded']);

/** Says that a model request failed and was sent again, and why. */
export const ModelRecoveryNotice: React.FC<{ notice: Notice }> = ({ notice }) => {
  const { t } = useI18n();
  const reason = REASONS.has(notice.reason) ? notice.reason : 'other';
  return (
    <div
      role="status"
      className="my-1.5 flex items-start gap-1.5 text-xs leading-5 text-neutral-600 dark:text-neutral-400"
    >
      <ArrowPathIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
      <span className="min-w-0 break-words">
        {t('modelRecovery.retried', {
          reason: t(`modelRecovery.reasons.${reason}`),
          attempt: notice.attempt,
          max: notice.maxAttempts,
        })}
        {notice.detail && (
          <span className="ml-1 font-mono text-[11px] text-neutral-500">({notice.detail})</span>
        )}
      </span>
    </div>
  );
};
