import { ClockIcon } from '@heroicons/react/24/outline';
import { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import type { ModelWaitState } from '../../lib/modelWait';

interface ModelWaitNoticeProps {
  wait: ModelWaitState;
  onExtend: (waitId: string) => Promise<boolean>;
}

export function ModelWaitNotice({ wait, onExtend }: ModelWaitNoticeProps): JSX.Element {
  const { t } = useI18n();
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [wait.waitId, wait.stage]);
  const message =
    wait.stage === 'extended'
      ? 'modelWaitExtended'
      : wait.stage === 'slow'
        ? 'modelResponseSlow'
        : 'modelResponseWaiting';
  const extend = async (): Promise<void> => {
    setPending(true);
    setFailed(false);
    try {
      if (!(await onExtend(wait.waitId))) setFailed(true);
    } finally {
      setPending(false);
    }
  };
  return (
    <div className="space-y-1 text-xs leading-5 text-neutral-600 dark:text-neutral-400">
      <div className="flex flex-wrap items-baseline gap-x-2.5">
        <div role="status" className="flex min-w-0 items-start gap-1.5">
          <ClockIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          <span>{t(message)}</span>
        </div>
        {wait.stage === 'slow' && wait.canExtend && (
          <button
            type="button"
            disabled={pending}
            onClick={() => void extend()}
            className="min-h-7 font-medium text-neutral-700 underline decoration-neutral-400 underline-offset-2 transition-colors enabled:hover:text-brutal-black enabled:hover:decoration-current focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-current disabled:opacity-60 dark:text-neutral-300 dark:decoration-neutral-500 dark:enabled:hover:text-white"
          >
            {t(pending ? 'modelWaitExtending' : 'modelWaitContinue')}
          </button>
        )}
      </div>
      {failed && (
        <p role="status" className="text-red-700 dark:text-red-300">
          {t('modelWaitExtensionFailed')}
        </p>
      )}
    </div>
  );
}
