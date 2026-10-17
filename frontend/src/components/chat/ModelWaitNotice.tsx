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
    <div role="status" className="mt-4 space-y-2 text-sm text-brutal-slate">
      <p>{t(message)}</p>
      {wait.stage === 'slow' && wait.canExtend && (
        <button
          type="button"
          disabled={pending}
          onClick={() => void extend()}
          className="border border-current px-3 py-1 disabled:opacity-50"
        >
          {t(pending ? 'modelWaitExtending' : 'modelWaitContinue')}
        </button>
      )}
      {failed && <p>{t('modelWaitExtensionFailed')}</p>}
    </div>
  );
}
