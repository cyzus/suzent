import React from 'react';

import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';
import { SettingsCard, SettingsPage } from './SettingsCard';
import { BrutalOnOff } from '../BrutalOnOff';

interface MemoryTabProps {
  memoryEnabled: boolean;
  onMemoryEnabledChange: (enabled: boolean) => void;
  /** Model assigned to the "embedding" role (Model Roles tab). */
  embeddingModel?: string;
  /** Effective model for the memory_extraction role, including inherited defaults. */
  extractionModel?: string;
  /** Navigate the settings modal to the Model Roles tab. */
  onOpenModelRoles?: () => void;
}

export function MemoryTab({
  memoryEnabled,
  onMemoryEnabledChange,
  embeddingModel,
  extractionModel,
  onOpenModelRoles,
}: MemoryTabProps): React.ReactElement {
  const { t } = useI18n();

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.memoryConfig.title')} />

      {/* Global memory enable toggle */}
      <SettingsCard>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold uppercase">
              {t('settings.memoryConfig.globalMemory')}
            </h3>
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
              {memoryEnabled ? t('config.memory.enabledDesc') : t('config.memory.disabledDesc')}
            </p>
          </div>
          <BrutalOnOff checked={memoryEnabled} onChange={onMemoryEnabledChange} />
        </div>

        <div className="mt-4 pt-4 border-t-2 border-dashed border-brutal-black dark:border-zinc-600">
          <div className="flex items-baseline justify-between gap-2 mb-2">
            <span className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400">
              {t('settings.memoryConfig.modelsLabel')}
            </span>
            {onOpenModelRoles && (
              <button
                type="button"
                onClick={onOpenModelRoles}
                className="group inline-flex items-center gap-1.5 px-2 py-1 text-[10px] font-bold uppercase tracking-wide border-2 border-brutal-black bg-neutral-100 text-brutal-black dark:bg-zinc-700 dark:text-white brutal-btn"
              >
                {t('settings.memoryConfig.editInModelRoles')}
                <svg
                  className="w-3 h-3 transition-transform group-hover:translate-x-0.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  strokeWidth={3}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">
                {t('settings.memoryConfig.embeddingModelLabel')}
              </div>
              <div className="font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all min-h-[2.25rem]">
                {embeddingModel || t('settings.memoryConfig.modelNotConfigured')}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">
                {t('settings.memoryConfig.extractionModelLabel')}
              </div>
              <div className="font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all min-h-[2.25rem]">
                {extractionModel || t('settings.memoryConfig.modelNotConfigured')}
              </div>
            </div>
          </div>
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
