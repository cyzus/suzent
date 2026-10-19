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
}: {
  onComplete: (model: string, task: string) => void;
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
  const [credentialsDirty, setCredentialsDirty] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [recommendations, setRecommendations] = useState<Roles>({});
  const [roles, setRoles] = useState<Roles>({});
  const [suggestions, setSuggestions] = useState<Roles>({});
  const [custom, setCustom] = useState(false);

  const [task, setTask] = useState('');

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
      setRoles(savedRoles);
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
  const available = providers.flatMap((p) =>
    checks[p.id]?.success ? configs[p.id]?.enabled_models || [] : []
  );
  const chosenRoles = custom ? roles : recommendations;
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
      // Explicit existing assignments are preserved; only empty roles receive recommendations.
      const merged = { ...proposed };
      for (const [key, value] of Object.entries(roles)) if (value.length) merged[key] = value;
      merged.primary = [model];
      setRecommendations(merged);
      setRoles(merged);
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
  return (
    <div className="mx-auto w-full max-w-3xl p-4 text-left sm:p-6">
      <nav className="mb-6 text-xs font-bold" aria-label={t('onboarding.progress')}>
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            aria-current={step === n ? 'step' : undefined}
            className={step === n ? '' : 'opacity-50'}
          >
            {n === 1 ? '' : ' → '}
            {n}. {t(`onboarding.step${n}`)}
          </span>
        ))}
      </nav>
      <h1 className="mb-2 text-2xl font-bold">{t(`onboarding.heading${step}`)}</h1>
      <p className="mb-6 text-sm text-neutral-500">{t(`onboarding.intro${step}`)}</p>
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
            <div className="mt-6 space-y-3 border-2 border-brutal-black p-4">
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
              <p className="text-xs text-neutral-500">{t('onboarding.probeNotice')}</p>
              <BrutalButton
                disabled={!selectedValid || verified || credentialsDirty}
                onClick={() => void verifyModel()}
              >
                {t(verified ? 'onboarding.verified' : 'onboarding.verify')}
              </BrutalButton>
            </div>
            <div className="mt-6 flex justify-end">
              <BrutalButton
                variant="dark"
                disabled={!selectedValid || !verified || credentialsDirty}
                onClick={() => void prepareRoles()}
              >
                {t('onboarding.continue')}
              </BrutalButton>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <div className="mb-5 flex gap-3">
              <BrutalButton isActive={!custom} onClick={() => setCustom(false)}>
                {t('onboarding.recommended')}
              </BrutalButton>
              <BrutalButton isActive={custom} onClick={() => setCustom(true)}>
                {t('onboarding.custom')}
              </BrutalButton>
            </div>
            {custom ? (
              <ModelRolesTab
                inlineVoiceModel
                roleModels={roles}
                suggestions={suggestions}
                unregisteredModels={suggestions._unregistered || []}
                onChange={setRoles}
              />
            ) : (
              <div className="divide-y divide-neutral-200 border-2 border-brutal-black">
                {Object.entries(labels).map(([key, label]) => (
                  <div key={key} className="grid gap-1 p-3 sm:grid-cols-2">
                    <strong className="text-sm">{t(`settings.roles.${label}`)}</strong>
                    <span className="break-all text-xs">
                      {recommendations[key]?.join(', ') || t('onboarding.noMatch')}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <p className="my-4 text-xs text-neutral-500">{t('onboarding.matchNotice')}</p>
            <div className="mt-6 flex justify-between">
              <BrutalButton onClick={() => setStep(1)}>{t('onboarding.back')}</BrutalButton>
              <BrutalButton
                variant="dark"
                disabled={!chosenRoles.primary?.length}
                onClick={() =>
                  void run(async () => {
                    if (chosenRoles.primary[0] !== model) {
                      const response = await fetch(
                        `${getApiBase()}/config/onboarding/verify-model`,
                        {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ model: chosenRoles.primary[0] }),
                        }
                      );
                      if (!response.ok || !(await response.json()).success) throw new Error();
                    }
                    if (
                      !(await saveRoleModels(chosenRoles)) ||
                      !(await saveUserPreferences({ model: chosenRoles.primary[0] }))
                    )
                      throw new Error();
                    setModel(chosenRoles.primary[0]);
                    await refreshBackendConfig();
                    setStep(3);
                  })
                }
              >
                {t(custom ? 'onboarding.saveContinue' : 'onboarding.useRecommended')}
              </BrutalButton>
            </div>
          </>
        )}
        {step === 3 && (
          <>
            <div className="mb-4 flex flex-wrap gap-2">
              {['research', 'file', 'project'].map((key) => (
                <BrutalButton
                  key={key}
                  size="sm"
                  onClick={() => setTask(t(`onboarding.${key}Prompt`))}
                >
                  {t(`onboarding.${key}`)}
                </BrutalButton>
              ))}
            </div>
            <textarea
              className="min-h-32 w-full border-2 border-brutal-black bg-white p-3 dark:bg-zinc-900"
              aria-label={t('onboarding.task')}
              value={task}
              onChange={(e) => setTask(e.target.value)}
            />
            <div className="mt-6 flex flex-wrap justify-between gap-3">
              <BrutalButton onClick={() => setStep(2)}>{t('onboarding.back')}</BrutalButton>
              <BrutalButton onClick={() => onComplete(model, '')}>
                {t('onboarding.skip')}
              </BrutalButton>
              <BrutalButton
                variant="dark"
                disabled={!task.trim()}
                onClick={() => onComplete(model, task)}
              >
                {t('onboarding.start')}
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
