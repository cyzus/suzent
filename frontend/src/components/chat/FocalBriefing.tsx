import React from 'react';
import { useI18n } from '../../i18n';

/**
 * Regent's opening greeting. Who it is and what waits on the user live in its
 * contact bar above the conversation, so this only says hello.
 */
export function FocalBriefing(): React.ReactElement {
  const { t } = useI18n();

  return (
    <div className="w-full max-w-2xl mb-6 text-left text-brutal-black dark:text-white">
      <h1 className="text-2xl font-bold tracking-tight">{t('focalBriefing.greeting')}</h1>
      <p className="mt-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">
        {t('focalBriefing.invitation')}
      </p>
    </div>
  );
}
