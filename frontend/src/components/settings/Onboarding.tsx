import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { useChatStore } from '../../hooks/useChatStore';
import { BrutalButton } from '../BrutalButton';
import { BrutalSelect } from '../BrutalSelect';
import { ProvidersTab } from './ProvidersTab';
import { ModelRolesTab } from './ModelRolesTab';

import {
  ApiProvider,
  UserConfig,
  fetchApiKeys,
  fetchRoleSuggestions,
  saveApiKeys,
  saveRoleModels,
  saveUserPreferences,
  verifyProvider,
  saveCustomProvider,
  getApiBase,
} from '../../lib/api';

type Roles = Record<string, string[]>;
type Check = { success: boolean; message: string };
const labels: Record<string, string> = {
  primary: 'primary',
  cheap: 'cheap',
  decision: 'decision',
  title: 'autoTitle',
  suggestion: 'suggestion',
  memory_extraction: 'memoryExtraction',
  dream: 'dream',
  goal_judge: 'goalJudge',
  permission_review: 'permissionReview',
  vision: 'vision',
  embedding: 'embedding',
  image_generation: 'imageGeneration',
  image_edit: 'imageEdit',
  video_generation: 'videoGeneration',
  tts: 'tts',
};

export function Onboarding({
  onComplete,
  onExit,
}: {
  onComplete: (model: string) => void;
  onExit?: () => void;
}): React.ReactElement {
  const { t } = useI18n();
  const { refreshBackendConfig } = useChatStore();
  const [step, setStep] = useState(1);
  const [providers, setProviders] = useState<ApiProvider[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const originals = useRef<Record<string, string>>({});
  const [configs, setConfigs] = useState<Record<string, UserConfig>>({});
  const [tabs, setTabs] = useState<Record<string, 'credentials' | 'models'>>({});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [checks, setChecks] = useState<Record<string, Check>>({});
  const [model, setModel] = useState('');
  const [verified, setVerified] = useState(false);
  const [connection, setConnection] = useState('untested');
  const [credentialsDirty, setCredentialsDirty] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [recommendations, setRecommendations] = useState<Roles>({});
  const [roles, setRoles] = useState<Roles>({});
  const savedRolesRef = useRef<Roles>({});
  const [roleMode, setRoleMode] = useState<'current' | 'filled' | 'recommended' | 'edited'>(
    'current'
  );
  const [confirmReset, setConfirmReset] = useState(false);
  const [suggestions, setSuggestions] = useState<Roles>({});
  const [custom, setCustom] = useState(false);

  const [manageProviders, setManageProviders] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
    headingRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [step]);

  const load = useCallback(async (): Promise<void> => {
    setBusy(true);
    setError('');
    try {
      const data = await fetchApiKeys();
      if (!data) throw new Error();
      const response = await fetch(`${getApiBase()}/config/role-models`);
      if (!response.ok) throw new Error();
      const savedRoles = (await response.json()).roles;
      setProviders(data.providers);
      const values = Object.fromEntries(
        data.providers.flatMap((p) => p.fields.map((f) => [f.key, f.value]))
      );
      originals.current = values;
      setKeys(values);
      setConfigs(
        Object.fromEntries(
          data.providers.map((p) => [
            p.id,
            p.user_config || { enabled_models: [], custom_models: [] },
          ])
        )
      );
      savedRolesRef.current = savedRoles;
      setRoles(savedRoles);
      const enabled = data.providers.flatMap((p) => p.user_config?.enabled_models || []);
      setModel((current) =>
        enabled.includes(current)
          ? current
          : enabled.includes(savedRoles.primary?.[0])
            ? savedRoles.primary[0]
            : ''
      );
      setVerified(false);
    } catch {
      setError(t('onboarding.loadFailed'));
    } finally {
      setBusy(false);
    }
  }, [t]);
  useEffect(() => {
    void load();
  }, [load]);

  function invalidate(): void {
    setConnection('untested');
    setVerified(false);
  }
  async function saveProviders(): Promise<void> {
    const changed = Object.fromEntries(
      Object.entries(keys).filter(([k, v]) => v !== originals.current[k])
    );
    if (!(await saveApiKeys({ ...changed, _PROVIDER_CONFIG_: JSON.stringify(configs) })))
      throw new Error();
    originals.current = { ...keys };
  }
  async function run(action: () => Promise<void>): Promise<void> {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch {
      setError(t('onboarding.actionFailed'));
    } finally {
      setBusy(false);
    }
  }
  async function verify(provider: ApiProvider): Promise<void> {
    invalidate();
    setChecks((c) => {
      const next = { ...c };
      delete next[provider.id];
      return next;
    });
    await run(async () => {
      await saveProviders();
      const result = await verifyProvider(provider.id, {});
      setChecks((c) => ({
        ...c,
        [provider.id]: {
          success: result.success,
          message: t(result.success ? 'onboarding.connected' : 'onboarding.connectionFailed'),
        },
      }));
      if (result.success) {
        setProviders((ps) =>
          ps.map((p) => (p.id === provider.id ? { ...p, models: result.models } : p))
        );
        setTabs((ts) => ({ ...ts, [provider.id]: 'models' }));
      }
    });
  }
  const available = [...new Set(providers.flatMap((p) => configs[p.id]?.enabled_models || []))];
  const chosenRoles = roles;
  const hasSavedRoles = Object.values(savedRolesRef.current).some((value) => value.length > 0);
  const canFill = Object.entries(recommendations).some(
    ([key, value]) => value.length > 0 && !roles[key]?.length
  );
  const selectedValid = available.includes(model);
  async function verifyModel(): Promise<void> {
    invalidate();
    await run(async () => {
      await saveProviders();
      const res = await fetch(`${getApiBase()}/config/onboarding/verify-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      });
      if (!res.ok || !(await res.json()).success) throw new Error();
      setVerified(true);
    });
  }
  async function prepareRoles(): Promise<void> {
    await run(async () => {
      await saveProviders();
      const res = await fetch(`${getApiBase()}/config/role-recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      });
      if (!res.ok) throw new Error();
      const proposed: Roles = (await res.json()).roles;
      setRecommendations({ ...proposed, primary: [model] });
      setRoles({ ...(hasSavedRoles ? savedRolesRef.current : proposed), primary: [model] });
      setRoleMode(hasSavedRoles ? 'current' : 'recommended');
      setCustom(false);
      setConfirmReset(false);
      const compatible = await fetchRoleSuggestions();
      const enabled = new Set(available);
      setSuggestions(
        Object.fromEntries(
          Object.entries(compatible).map(([k, v]) => [k, v.filter((id) => enabled.has(id))])
        )
      );
      setStep(2);
    });
  }
  if (busy && !providers.length)
    return (
      <div className="mx-auto max-w-3xl p-8" role="status" aria-live="polite">
        {t('common.loading')}
      </div>
    );
  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8 text-left sm:px-8 sm:py-12">
      <header className="mb-10 flex items-center justify-between border-b border-neutral-200 pb-4 dark:border-zinc-700">
        <span className="text-sm font-black tracking-[0.2em]">SUZENT</span>
        {onExit && (
          <BrutalButton variant="ghost" size="sm" disabled={busy} onClick={onExit}>
            {t('onboarding.exit')}
          </BrutalButton>
        )}
      </header>
      <nav
        className="mb-8 grid grid-cols-2 gap-3 text-xs font-bold"
        aria-label={t('onboarding.progress')}
      >
        {[1, 2].map((n) => (
          <span
            key={n}
            aria-current={step === n ? 'step' : undefined}
            className={`border-t-2 pt-3 ${step >= n ? 'border-current' : 'border-neutral-200 text-neutral-400'}`}
          >
            {step > n ? '✓' : n}. {t(`onboarding.step${n}`)}
          </span>
        ))}
      </nav>
      <h1
        ref={headingRef}
        tabIndex={-1}
        className="mb-3 scroll-mt-6 text-3xl font-bold tracking-tight outline-none sm:text-4xl"
      >
        {t(`onboarding.heading${step}`)}
      </h1>
      <p className="mb-8 text-sm leading-relaxed text-neutral-500">
        {t(`onboarding.intro${step}`)}
      </p>
      {error && (
        <div role="alert" className="mb-4 border-l-4 border-current p-3">
          {error}
          {!providers.length && (
            <BrutalButton onClick={() => void load()}>{t('common.retry')}</BrutalButton>
          )}
        </div>
      )}
      <fieldset
        disabled={busy}
        onInputCapture={() => {
          if (step === 1) invalidate();
        }}
        className="min-w-0 border-0 p-0 disabled:opacity-60"
      >
        {step === 1 && (
          <>
            {available.length > 0 && (
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border border-neutral-200 p-4 dark:border-zinc-700">
                <p className="text-sm">
                  {t('onboarding.existingModels', { count: String(available.length) })}
                </p>
                <BrutalButton
                  variant="ghost"
                  size="sm"
                  onClick={() => setManageProviders(!manageProviders)}
                  aria-expanded={manageProviders}
                >
                  {t(manageProviders ? 'onboarding.hideProviders' : 'onboarding.manageProviders')}
                </BrutalButton>
              </div>
            )}
            <div hidden={available.length > 0 && !manageProviders}>
              <ProvidersTab
                onCredentialDraftChange={setCredentialsDirty}
                onboarding
                providers={providers}
                apiKeys={keys}
                userConfigs={configs}
                showKey={showKeys}
                activeTabs={tabs}
                verifying={{}}
                verification={checks}
                onKeyChange={(key, value) => {
                  setKeys((k) => ({ ...k, [key]: value }));
                  setChecks({});
                  invalidate();
                }}
                onToggleShowKey={(key) => setShowKeys((s) => ({ ...s, [key]: !s[key] }))}
                onTabChange={(id, tab) => setTabs((s) => ({ ...s, [id]: tab }))}
                onConfigChange={(id, config) => {
                  setConfigs((s) => ({ ...s, [id]: config }));
                  invalidate();
                }}
                onAddCustomModel={(id, value) => {
                  const name = value.trim();
                  if (!name) return;
                  setConfigs((s) => {
                    const c = s[id];
                    return {
                      ...s,
                      [id]: {
                        ...c,
                        custom_models: [...new Set([...c.custom_models, name])],
                        enabled_models: [...new Set([...c.enabled_models, name])],
                      },
                    };
                  });
                  invalidate();
                }}
                onVerify={(provider) => void verify(provider)}
                onAddProvider={async (payload) => {
                  await saveProviders();
                  const result = await saveCustomProvider(payload);
                  if (!result.success) throw new Error(t('onboarding.actionFailed'));
                  await load();
                  setChecks({});
                  invalidate();
                }}
                onDeleteProvider={async () => {}}
                onChatGPTAuthChanged={() => {
                  setChecks({});
                  invalidate();
                }}
              />
            </div>
            <div className="mt-6 space-y-4 border border-neutral-300 p-5 dark:border-zinc-600">
              <BrutalSelect
                label={t('onboarding.defaultModel')}
                value={model}
                options={available}
                disabled={!available.length}
                onChange={(value) => {
                  setModel(value);
                  invalidate();
                }}
              />
              <p className="text-xs text-neutral-500" role="status">
                {t(
                  !available.length
                    ? 'onboarding.enableFirst'
                    : credentialsDirty
                      ? 'onboarding.saveCredentialsFirst'
                      : 'onboarding.selectThenVerify'
                )}
              </p>
              <p role="status" className="text-xs">
                {t(verified ? 'onboarding.verified' : `onboarding.connection_${connection}`)}
              </p>
              <BrutalButton
                disabled={!selectedValid || credentialsDirty}
                onClick={() =>
                  void run(async () => {
                    setConnection('untested');
                    await saveProviders();
                    const res = await fetch(`${getApiBase()}/config/onboarding/check-connection`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ model }),
                    });
                    const result = await res.json();
                    setConnection(
                      ['connected', 'unsupported', 'unconfirmed'].includes(result.status)
                        ? result.status
                        : 'unconfirmed'
                    );
                  })
                }
              >
                {t('onboarding.checkConnection')}
              </BrutalButton>
              <details className="border-t border-neutral-200 pt-4 dark:border-zinc-700">
                <summary className="cursor-pointer text-xs font-bold">
                  {t('onboarding.optionalTest')}
                </summary>
                <p className="my-3 text-xs leading-relaxed text-neutral-500">
                  {t('onboarding.probeNotice')}
                </p>
                <BrutalButton
                  disabled={!selectedValid || verified || credentialsDirty}
                  onClick={() => void verifyModel()}
                >
                  {t(verified ? 'onboarding.verified' : 'onboarding.verify')}
                </BrutalButton>
              </details>
            </div>
            <div className="mt-8 flex justify-end border-t border-neutral-200 pt-5 dark:border-zinc-700">
              <BrutalButton
                variant="dark"
                disabled={!selectedValid || credentialsDirty}
                onClick={() => void prepareRoles()}
              >
                {t('onboarding.continue')}
              </BrutalButton>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <div className="mb-5 flex flex-wrap gap-3">
              <BrutalButton isActive={!custom} onClick={() => setCustom(false)}>
                {t(roleMode === 'current' ? 'onboarding.currentRoles' : 'onboarding.rolesPreview')}
              </BrutalButton>
              <BrutalButton isActive={custom} onClick={() => setCustom(true)}>
                {t('onboarding.custom')}
              </BrutalButton>
            </div>
            <p className="mb-4 text-sm leading-relaxed" role="status">
              {t(`onboarding.roles_${roleMode}`)}
            </p>
            {hasSavedRoles && (
              <div className="mb-5 flex flex-wrap gap-2">
                <BrutalButton
                  size="sm"
                  disabled={!canFill}
                  onClick={() => {
                    setRoles((current) => {
                      const next = { ...current };
                      for (const [key, value] of Object.entries(recommendations))
                        if (!next[key]?.length) next[key] = value;
                      return next;
                    });
                    setRoleMode('filled');
                  }}
                >
                  {t('onboarding.fillMissing')}
                </BrutalButton>
                <BrutalButton variant="ghost" size="sm" onClick={() => setConfirmReset(true)}>
                  {t('onboarding.recommendAll')}
                </BrutalButton>
                {roleMode !== 'current' && (
                  <BrutalButton
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setRoles({ ...savedRolesRef.current, primary: [model] });
                      setRoleMode('current');
                      setConfirmReset(false);
                    }}
                  >
                    {t('onboarding.restoreRoles')}
                  </BrutalButton>
                )}
              </div>
            )}
            {hasSavedRoles && !canFill && (
              <p className="mb-4 text-xs text-neutral-500">{t('onboarding.nothingToFill')}</p>
            )}
            {confirmReset && (
              <div className="mb-5 space-y-3 border border-current p-4" role="alert">
                <p className="text-sm">{t('onboarding.replaceRolesNotice')}</p>
                <div className="flex flex-wrap gap-2">
                  <BrutalButton
                    size="sm"
                    onClick={() => {
                      setRoles({ ...recommendations });
                      setRoleMode('recommended');
                      setConfirmReset(false);
                    }}
                  >
                    {t('onboarding.confirmRecommend')}
                  </BrutalButton>
                  <BrutalButton size="sm" variant="ghost" onClick={() => setConfirmReset(false)}>
                    {t('common.cancel')}
                  </BrutalButton>
                </div>
              </div>
            )}
            {custom ? (
              <ModelRolesTab
                inlineVoiceModel
                roleModels={roles}
                suggestions={suggestions}
                unregisteredModels={suggestions._unregistered || []}
                onChange={(next) => {
                  setRoles(next);
                  setRoleMode('edited');
                }}
              />
            ) : (
              <div className="divide-y divide-neutral-200 border-2 border-brutal-black">
                {Object.entries(labels)
                  .filter(([key]) =>
                    [
                      'primary',
                      'cheap',
                      'vision',
                      'image_generation',
                      'image_edit',
                      'video_generation',
                      'tts',
                      'embedding',
                    ].includes(key)
                  )
                  .map(([key, label]) => (
                    <div key={key} className="grid gap-1 p-3 sm:grid-cols-2">
                      <strong className="text-sm">{t(`settings.roles.${label}`)}</strong>
                      <span className="break-all text-xs">
                        {roles[key]?.join(', ') || t('onboarding.noMatch')}
                      </span>
                    </div>
                  ))}
              </div>
            )}
            {!custom && (
              <details className="mt-4 border border-neutral-200 p-4 dark:border-zinc-700">
                <summary className="cursor-pointer text-sm font-bold">
                  {t('onboarding.backgroundRoles')}
                </summary>
                {Object.entries(labels)
                  .filter(
                    ([key]) =>
                      ![
                        'primary',
                        'cheap',
                        'vision',
                        'image_generation',
                        'image_edit',
                        'video_generation',
                        'tts',
                        'embedding',
                      ].includes(key)
                  )
                  .map(([key, label]) => (
                    <div
                      key={key}
                      className="grid gap-1 border-t border-neutral-100 py-3 text-xs sm:grid-cols-2"
                    >
                      <strong>{t(`settings.roles.${label}`)}</strong>
                      <span className="break-all">
                        {roles[key]?.join(', ') || t('onboarding.noMatch')}
                      </span>
                    </div>
                  ))}
              </details>
            )}
            <p className="my-4 text-xs leading-relaxed text-neutral-500">
              {t('onboarding.matchNotice')}
            </p>
            <div className="mt-8 flex flex-wrap justify-between gap-3 border-t border-neutral-200 pt-5">
              <BrutalButton onClick={() => setStep(1)}>{t('onboarding.back')}</BrutalButton>
              <BrutalButton
                variant="dark"
                disabled={!chosenRoles.primary?.length}
                onClick={() =>
                  void run(async () => {
                    if (
                      !(await saveRoleModels(chosenRoles)) ||
                      !(await saveUserPreferences({ model: chosenRoles.primary[0] }))
                    )
                      throw new Error();
                    setModel(chosenRoles.primary[0]);
                    await refreshBackendConfig();
                    onComplete(chosenRoles.primary[0]);
                  })
                }
              >
                {t(roleMode === 'current' ? 'onboarding.keepContinue' : 'onboarding.saveContinue')}
              </BrutalButton>
            </div>
          </>
        )}
      </fieldset>
      {busy && (
        <p className="mt-4 text-sm" role="status">
          {t('common.loading')}
        </p>
      )}
    </div>
  );
}
