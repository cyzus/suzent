import React, { useEffect, useState } from 'react';

import { useI18n } from '../../i18n';
import { fetchMemoryExternalAccess, saveMemoryExternalAccess } from '../../lib/api';
import { SettingsHeader } from './SettingsHeader';
import { SectionCardHeader, SettingsCard, SettingsPage } from './SettingsCard';
import { BrutalOnOff } from '../BrutalOnOff';
import { CopyButton } from './CopyButton';

export const CLAUDE_CODE_MCP_COMMAND = 'claude mcp add suzent -- suzent mcp serve';

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

      <OtherAgentsCard />
    </SettingsPage>
  );
}

function OtherAgentsCard(): React.ReactElement {
  const { t } = useI18n();
  const [writeEnabled, setWriteEnabled] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchMemoryExternalAccess()
      .then((access) => {
        if (!cancelled && access) setWriteEnabled(access.write_enabled);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const onWriteChange = (enabled: boolean): void => {
    setError('');
    setWriteEnabled(enabled);
    saveMemoryExternalAccess(enabled)
      .then((access) => setWriteEnabled(access.write_enabled))
      .catch(() => {
        setWriteEnabled(!enabled);
        setError(t('settings.memoryConfig.otherAgentsSaveFailed'));
      });
  };

  return (
    <SettingsCard>
      <SectionCardHeader
        title={t('settings.memoryConfig.otherAgentsTitle')}
        description={t('settings.memoryConfig.otherAgentsDesc')}
      />
      <div className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">
        {t('settings.memoryConfig.otherAgentsCommand')}
      </div>
      <div className="flex items-center gap-2">
        <code className="flex-1 min-w-0 font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all">
          {CLAUDE_CODE_MCP_COMMAND}
        </code>
        <CopyButton value={CLAUDE_CODE_MCP_COMMAND} />
      </div>
      <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-2">
        {t('settings.memoryConfig.otherAgentsOtherApps')}
      </p>

      <div className="mt-4 pt-4 border-t-2 border-dashed border-brutal-black dark:border-zinc-600 flex items-center justify-between gap-4">
        <div>
          <h4 className="text-sm font-bold uppercase">
            {t('settings.memoryConfig.otherAgentsWrite')}
          </h4>
          <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">
            {t('settings.memoryConfig.otherAgentsWriteDesc')}
          </p>
          {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
        </div>
        <BrutalOnOff checked={writeEnabled} onChange={onWriteChange} />
      </div>
    </SettingsCard>
  );
}
