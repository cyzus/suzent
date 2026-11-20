import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { useChatStore } from '../../hooks/useChatStore';
import { isImeComposing } from '../../lib/ime';
import { BrutalButton } from '../BrutalButton';
import { BrutalSelect } from '../BrutalSelect';
import { ProviderIcon, ProvidersTab, baseUrlField, regionName } from './ProvidersTab';

import {
  ApiProvider,
  Model,
  UserConfig,
  fetchApiKeys,
  fetchChatGPTStatus,
  getApiBase,
  saveApiKeys,
  saveCustomProvider,
  saveRoleModels,
  saveUserPreferences,
  startChatGPTLogin,
  verifyProvider,
} from '../../lib/api';
import type { ChatGPTLoginResponse } from '../../types/api';

type Roles = Record<string, string[]>;
type Screen = 'pick' | 'connect' | 'manual' | 'done';
type Failure = 'auth' | 'quota' | 'busy' | 'model' | 'network' | 'unknown';
type Progress = 'saving' | 'listing' | 'probing';

/** The services a first-time user is offered, best first, by where they are. */
const PICKS = {
  china: ['deepseek', 'dashscope', 'moonshot', 'zhipuai'],
  global: ['chatgpt', 'anthropic', 'openai', 'gemini'],
} as const;
const GROUPS = ['china', 'global', 'relay', 'local'] as const;
const STEP: Record<Screen, number> = { pick: 1, connect: 2, manual: 2, done: 3 };
const EMPTY_CONFIG: UserConfig = { enabled_models: [], custom_models: [] };

/** Services that run on the user's machine take an address rather than a key. */
function runsLocally(provider: ApiProvider): boolean {
  return provider.group === 'local' || provider.id === 'litellm_proxy';
}

function chatIds(models: Model[]): string[] {
  return models.filter((m) => !m.mode || m.mode === 'chat').map((m) => m.id);
}

export function Onboarding({
  onComplete,
  onExit,
}: {
  onComplete: (model: string) => void;
  onExit?: () => void;
}): React.ReactElement {
  const { t, locale } = useI18n();
  const { refreshBackendConfig } = useChatStore();
  const [screen, setScreen] = useState<Screen>('pick');
  const [providers, setProviders] = useState<ApiProvider[]>([]);
  const [chinaMode, setChinaMode] = useState(false);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const originals = useRef<Record<string, string>>({});
  const [configs, setConfigs] = useState<Record<string, UserConfig>>({});
  const savedRoles = useRef<Roles>({});
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [model, setModel] = useState('');
  const [showMore, setShowMore] = useState(false);

  const [selectedId, setSelectedId] = useState('');
  const [progress, setProgress] = useState<Progress | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [connectedLabel, setConnectedLabel] = useState('');

  const [manualTabs, setManualTabs] = useState<Record<string, 'credentials' | 'models'>>({});
  const [manualShowKeys, setManualShowKeys] = useState<Record<string, boolean>>({});
  const [manualChecks, setManualChecks] = useState<
    Record<string, { success: boolean; message: string }>
  >({});
  const [credentialsDirty, setCredentialsDirty] = useState(false);

  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
    headingRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [screen]);

  const load = useCallback(async (): Promise<void> => {
    setBusy(true);
    setError('');
    try {
      const data = await fetchApiKeys();
      if (!data) throw new Error();
      const response = await fetch(`${getApiBase()}/config/role-models`);
      if (!response.ok) throw new Error();
      const roles: Roles = (await response.json()).roles;
      setProviders(data.providers);
      setChinaMode(data.china_mode === true);
      const values = Object.fromEntries(
        data.providers.flatMap((p) => p.fields.map((f) => [f.key, f.value]))
      );
      originals.current = values;
      setKeys(values);
      setConfigs(
        Object.fromEntries(data.providers.map((p) => [p.id, p.user_config || EMPTY_CONFIG]))
      );
      savedRoles.current = roles;
      const enabled = data.providers.flatMap((p) => p.user_config?.enabled_models || []);
      setModel((current) =>
        enabled.includes(current)
          ? current
          : enabled.includes(roles.primary?.[0])
            ? roles.primary[0]
            : (enabled[0] ?? '')
      );
    } catch {
      setError(t('onboarding.loadFailed'));
    } finally {
      setBusy(false);
    }
  }, [t]);
  useEffect(() => {
    void load();
  }, [load]);

  const available = [...new Set(providers.flatMap((p) => configs[p.id]?.enabled_models || []))];
  const selected = providers.find((p) => p.id === selectedId);
  const providerName = (provider: ApiProvider): string => {
    const key = `onboarding.services.${provider.id}.name`;
    const name = t(key);
    return name === key ? provider.label : name;
  };

  async function saveProviders(
    nextKeys: Record<string, string> = keys,
    nextConfigs: Record<string, UserConfig> = configs
  ): Promise<void> {
    const changed = Object.fromEntries(
      Object.entries(nextKeys).filter(([k, v]) => v !== originals.current[k])
    );
    if (!(await saveApiKeys({ ...changed, _PROVIDER_CONFIG_: JSON.stringify(nextConfigs) })))
      throw new Error();
    originals.current = { ...nextKeys };
  }

  function choose(provider: ApiProvider): void {
    setSelectedId(provider.id);
    setFailure(null);
    setProgress(null);
    setScreen('connect');
  }

  /**
   * Save, list the service's models, enable the recommended ones and send one
   * tiny reply so a wrong key or an empty balance shows up here, not in chat.
   */
  async function connect(provider: ApiProvider): Promise<void> {
    setFailure(null);
    setBusy(true);
    try {
      setProgress('saving');
      await saveProviders();
      setProgress('listing');
      const result = await verifyProvider(provider.id, {});
      if (result.error) throw new Error();
      if (!result.success) {
        setFailure(runsLocally(provider) ? 'network' : 'auth');
        return;
      }
      const listed = result.used_catalog_fallback ? [] : chatIds(result.models);
      const defaults = provider.default_models.map((m) => m.id);
      const preferred = listed.length ? defaults.filter((id) => listed.includes(id)) : defaults;
      const primary = preferred[0] ?? listed[0] ?? chatIds(result.models)[0];
      if (!primary) {
        setFailure('model');
        return;
      }
      const current = configs[provider.id] || EMPTY_CONFIG;
      const nextConfigs = {
        ...configs,
        [provider.id]: {
          ...current,
          enabled_models: [
            ...new Set([...current.enabled_models, ...(preferred.length ? preferred : [primary])]),
          ],
        },
      };
      setConfigs(nextConfigs);
      setProviders((ps) =>
        ps.map((p) => (p.id === provider.id ? { ...p, models: result.models } : p))
      );
      await saveProviders(keys, nextConfigs);
      setModel(primary);
      setConnectedLabel(providerName(provider));

      setProgress('probing');
      const probe = await fetch(`${getApiBase()}/config/onboarding/verify-model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: primary }),
      });
      const verdict = await probe.json().catch(() => ({}));
      if (!probe.ok || !verdict.success) {
        setFailure((verdict.reason as Failure) || 'unknown');
        return;
      }
      setScreen('done');
    } catch {
      setFailure('unknown');
    } finally {
      setProgress(null);
      setBusy(false);
    }
  }

  async function finish(): Promise<void> {
    setBusy(true);
    setError('');
    try {
      await saveProviders();
      const res = await fetch(`${getApiBase()}/config/role-recommendations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, models: available }),
      });
      if (!res.ok) throw new Error();
      const proposed: Roles = (await res.json()).roles;
      const roles: Roles = { ...proposed };
      for (const [role, models] of Object.entries(savedRoles.current))
        if (models.length > 0) roles[role] = models;
      roles.primary = [model];
      if (!(await saveRoleModels(roles)) || !(await saveUserPreferences({ model })))
        throw new Error();
      await refreshBackendConfig();
      onComplete(model);
    } catch {
      setError(t('onboarding.actionFailed'));
    } finally {
      setBusy(false);
    }
  }

  if (busy && !providers.length)
    return (
      <div className="mx-auto max-w-3xl p-8" role="status" aria-live="polite">
        {error || t('common.loading')}
        {error && (
          <BrutalButton className="ml-3" onClick={() => void load()}>
            {t('common.retry')}
          </BrutalButton>
        )}
      </div>
    );

  const picks = PICKS[chinaMode ? 'china' : 'global']
    .map((id) => providers.find((p) => p.id === id))
    .filter((p): p is ApiProvider => !!p);
  const others = providers.filter((p) => !picks.includes(p));
  const step = STEP[screen];

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
        className="mb-8 grid grid-cols-3 gap-3 text-xs font-bold"
        aria-label={t('onboarding.progress')}
      >
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            aria-current={step === n ? 'step' : undefined}
            className={`border-t-2 pt-3 ${step >= n ? 'border-current' : 'border-neutral-200 text-neutral-400 dark:border-zinc-700'}`}
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
        {screen === 'connect' && selected
          ? t('onboarding.connectHeading', { name: providerName(selected) })
          : t(`onboarding.heading_${screen}`)}
      </h1>
      <p className="mb-8 text-sm leading-relaxed text-neutral-500 dark:text-neutral-400">
        {screen === 'done' && connectedLabel
          ? t('onboarding.intro_done_connected', { name: connectedLabel })
          : t(`onboarding.intro_${screen}`)}
      </p>
      {error && (
        <div role="alert" className="mb-4 border-l-4 border-current p-3 text-sm">
          {error}
        </div>
      )}

      {screen === 'pick' && (
        <>
          {available.length > 0 && (
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-2 border-brutal-black p-4 dark:border-zinc-500">
              <p className="text-sm">
                {t('onboarding.existingModels', { count: String(available.length) })}
              </p>
              <BrutalButton variant="dark" size="sm" onClick={() => setScreen('done')}>
                {t('onboarding.useExisting')}
              </BrutalButton>
            </div>
          )}
          <p className="mb-3 text-xs font-bold text-neutral-500 dark:text-neutral-400">
            {t('onboarding.recommendedFor', {
              where: t(chinaMode ? 'onboarding.whereChina' : 'onboarding.whereGlobal'),
            })}
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {picks.map((provider, index) => (
              <button
                key={provider.id}
                type="button"
                onClick={() => choose(provider)}
                className="flex items-start gap-3 border-2 border-brutal-black bg-white p-4 text-left shadow-brutal-sm transition-transform hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue dark:border-zinc-500 dark:bg-zinc-900 dark:shadow-none"
              >
                <ProviderIcon provider={provider} />
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2 font-bold">
                    {providerName(provider)}
                    {index === 0 && (
                      <span className="border border-current px-1.5 text-[10px] font-bold">
                        {t('onboarding.recommendedBadge')}
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
                    {t(`onboarding.services.${provider.id}.desc`)}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <button
            type="button"
            aria-expanded={showMore}
            onClick={() => setShowMore(!showMore)}
            className="mt-6 text-sm font-bold underline underline-offset-4"
          >
            {t(showMore ? 'onboarding.fewerServices' : 'onboarding.moreServices', {
              count: String(others.length),
            })}
          </button>
          {showMore && (
            <div className="mt-4 space-y-5">
              {GROUPS.map((group) => {
                const members = others.filter((p) => (p.group ?? 'global') === group);
                if (!members.length) return null;
                return (
                  <section key={group}>
                    <h2 className="mb-2 text-xs font-bold text-neutral-500 dark:text-neutral-400">
                      {t(`onboarding.group_${group}`)}
                    </h2>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {members.map((provider) => (
                        <button
                          key={provider.id}
                          type="button"
                          onClick={() => choose(provider)}
                          className="flex items-center gap-3 border border-neutral-300 p-2 text-left text-sm hover:border-current dark:border-zinc-600"
                        >
                          <ProviderIcon provider={provider} />
                          <span className="min-w-0 truncate">{providerName(provider)}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
          <div className="mt-10 border-t border-neutral-200 pt-5 text-xs text-neutral-500 dark:border-zinc-700 dark:text-neutral-400">
            {t('onboarding.manualHint')}{' '}
            <button
              type="button"
              className="font-bold text-current underline underline-offset-4"
              onClick={() => setScreen('manual')}
            >
              {t('onboarding.manualLink')}
            </button>
          </div>
        </>
      )}

      {screen === 'connect' && selected && (
        <ConnectForm
          provider={selected}
          name={providerName(selected)}
          keys={keys}
          busy={busy}
          progress={progress}
          failure={failure}
          onKeyChange={(key, value) => {
            setKeys((k) => ({ ...k, [key]: value }));
            setFailure(null);
          }}
          onConnect={() => void connect(selected)}
          onSkipCheck={() => setScreen('done')}
          onBack={() => setScreen('pick')}
          locale={locale}
        />
      )}

      {screen === 'manual' && (
        <fieldset disabled={busy} className="min-w-0 border-0 p-0 disabled:opacity-60">
          <ProvidersTab
            onCredentialDraftChange={setCredentialsDirty}
            onboarding
            providers={providers}
            apiKeys={keys}
            userConfigs={configs}
            showKey={manualShowKeys}
            activeTabs={manualTabs}
            verifying={{}}
            verification={manualChecks}
            onKeyChange={(key, value) => {
              setKeys((k) => ({ ...k, [key]: value }));
              setManualChecks({});
            }}
            onToggleShowKey={(key) => setManualShowKeys((s) => ({ ...s, [key]: !s[key] }))}
            onTabChange={(id, tab) => setManualTabs((s) => ({ ...s, [id]: tab }))}
            onConfigChange={(id, config) => setConfigs((s) => ({ ...s, [id]: config }))}
            onAddCustomModel={(id, value) => {
              const raw = value.trim();
              if (!raw) return;
              const name = raw.includes('/') ? raw : `${id}/${raw}`;
              setConfigs((s) => {
                const c = s[id] || EMPTY_CONFIG;
                return {
                  ...s,
                  [id]: {
                    ...c,
                    custom_models: [...new Set([...c.custom_models, name])],
                    enabled_models: [...new Set([...c.enabled_models, name])],
                  },
                };
              });
            }}
            onVerify={(provider) =>
              void (async () => {
                setBusy(true);
                try {
                  await saveProviders();
                  const result = await verifyProvider(provider.id, {});
                  const ok = result.success;
                  setManualChecks((c) => ({
                    ...c,
                    [provider.id]: {
                      success: ok,
                      message: t(ok ? 'onboarding.connected' : 'onboarding.connectionFailed'),
                    },
                  }));
                  const fetched = ok ? chatIds(result.models) : [];
                  if (ok) {
                    setProviders((ps) =>
                      ps.map((p) => (p.id === provider.id ? { ...p, models: result.models } : p))
                    );
                  }
                  if (fetched.length > 0) {
                    setConfigs((prev) => {
                      const current = prev[provider.id] || EMPTY_CONFIG;
                      if (current.enabled_models.length > 0) return prev;
                      return {
                        ...prev,
                        [provider.id]: { ...current, enabled_models: [fetched[0]] },
                      };
                    });
                    setModel((current) => current || fetched[0]);
                  }
                } catch {
                  setError(t('onboarding.actionFailed'));
                } finally {
                  setBusy(false);
                }
              })()
            }
            onAddProvider={async (payload) => {
              await saveProviders();
              const result = await saveCustomProvider(payload);
              if (!result.success) throw new Error(t('onboarding.actionFailed'));
              await load();
              setManualChecks({});
            }}
            onDeleteProvider={async () => {}}
            onChatGPTAuthChanged={() => setManualChecks({})}
          />
          <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-200 pt-5 dark:border-zinc-700">
            <BrutalButton onClick={() => setScreen('pick')}>{t('onboarding.back')}</BrutalButton>
            <span className="text-xs text-neutral-500 dark:text-neutral-400" role="status">
              {t(
                !available.length
                  ? 'onboarding.enableFirst'
                  : credentialsDirty
                    ? 'onboarding.saveCredentialsFirst'
                    : 'onboarding.manualReady'
              )}
            </span>
            <BrutalButton
              variant="dark"
              disabled={!available.length || credentialsDirty}
              onClick={() =>
                void (async () => {
                  setBusy(true);
                  try {
                    await saveProviders();
                    setConnectedLabel('');
                    if (!available.includes(model)) setModel(available[0]);
                    setScreen('done');
                  } catch {
                    setError(t('onboarding.actionFailed'));
                  } finally {
                    setBusy(false);
                  }
                })()
              }
            >
              {t('onboarding.continue')}
            </BrutalButton>
          </div>
        </fieldset>
      )}

      {screen === 'done' && (
        <fieldset disabled={busy} className="min-w-0 border-0 p-0 disabled:opacity-60">
          <div className="space-y-4 border-2 border-brutal-black p-5 dark:border-zinc-500">
            <BrutalSelect
              label={t('onboarding.defaultModel')}
              value={available.includes(model) ? model : ''}
              options={available}
              disabled={!available.length}
              onChange={setModel}
            />
            <p className="text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
              {t('onboarding.rolesAuto')}
            </p>
          </div>
          <div className="mt-8 flex flex-wrap justify-between gap-3 border-t border-neutral-200 pt-5 dark:border-zinc-700">
            <BrutalButton onClick={() => setScreen('pick')}>
              {t('onboarding.changeService')}
            </BrutalButton>
            <BrutalButton
              variant="dark"
              disabled={!available.includes(model)}
              onClick={() => void finish()}
            >
              {t('onboarding.start')}
            </BrutalButton>
          </div>
        </fieldset>
      )}
    </div>
  );
}

function ConnectForm({
  provider,
  name,
  keys,
  busy,
  progress,
  failure,
  onKeyChange,
  onConnect,
  onSkipCheck,
  onBack,
  locale,
}: {
  provider: ApiProvider;
  name: string;
  keys: Record<string, string>;
  busy: boolean;
  progress: Progress | null;
  failure: Failure | null;
  onKeyChange: (key: string, value: string) => void;
  onConnect: () => void;
  onSkipCheck: () => void;
  onBack: () => void;
  locale: string;
}): React.ReactElement {
  const { t } = useI18n();
  const local = runsLocally(provider);
  const secret = provider.fields.find((f) => f.type === 'secret');
  const address = baseUrlField(provider);
  const regions = provider.regions ?? [];
  const savedAddress = address ? (keys[address.key] ?? '').trim().replace(/\/+$/, '') : '';
  const region = savedAddress
    ? regions.find((r) => r.base_url.replace(/\/+$/, '') === savedAddress)
    : regions[0];
  const keyUrl = region?.key_url || provider.key_url;
  const keyValue = secret ? (keys[secret.key] ?? '') : '';
  // A key already saved comes back masked; it still counts as entered.
  const hasKey = !!keyValue.trim() || !!secret?.isSet;
  const ready = local || !secret || hasKey;

  const field = (f: NonNullable<typeof secret>, label: string, hint?: string) => (
    <label className="block space-y-1.5">
      <span className="block text-xs font-bold">{label}</span>
      <input
        type={f.type === 'secret' ? 'password' : 'text'}
        autoComplete="off"
        spellCheck={false}
        value={keys[f.key] ?? ''}
        placeholder={f.placeholder}
        onChange={(e) => onKeyChange(f.key, e.target.value.trim())}
        onKeyDown={(e) => {
          if (isImeComposing(e)) return;
          if (e.key === 'Enter' && ready && !busy) onConnect();
        }}
        className="w-full border-2 border-brutal-black bg-white px-3 py-2.5 font-mono text-sm outline-none focus:border-brutal-blue dark:border-zinc-500 dark:bg-zinc-900"
      />
      {hint && <span className="block text-xs text-neutral-500 dark:text-neutral-400">{hint}</span>}
    </label>
  );

  if (provider.id === 'chatgpt')
    return <ChatGPTSignIn onBack={onBack} onSignedIn={onConnect} busy={busy} failure={failure} />;

  return (
    <div className="space-y-6">
      {regions.length > 1 && address && (
        <div className="space-y-2">
          <span className="block text-xs font-bold">
            {t(provider.region_label === 'plan' ? 'onboarding.pickPlan' : 'onboarding.pickRegion')}
          </span>
          <div role="radiogroup" className="flex flex-wrap gap-2">
            {regions.map((r) => {
              const active = region?.id === r.id;
              return (
                <button
                  key={r.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => onKeyChange(address.key, r.base_url)}
                  className={`border-2 border-brutal-black px-3 py-1.5 text-xs font-bold dark:border-zinc-500 ${active ? 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black' : ''}`}
                >
                  {regionName(r, locale)}
                </button>
              );
            })}
          </div>
          {provider.split_accounts && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              {t('settings.providers.regionPicker.splitAccounts')}
            </p>
          )}
        </div>
      )}

      {local ? (
        address && field(address, t('onboarding.localAddress'), t('onboarding.localHint'))
      ) : (
        <>
          <ol className="space-y-2 text-sm leading-relaxed">
            <li>
              1.{' '}
              {keyUrl ? (
                <a
                  href={keyUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="font-bold underline underline-offset-4"
                >
                  {t('onboarding.keyStep1', { name })} ↗
                </a>
              ) : (
                t('onboarding.keyStep1', { name })
              )}
            </li>
            <li>2. {t('onboarding.keyStep2')}</li>
            <li>3. {t('onboarding.keyStep3')}</li>
          </ol>
          {secret &&
            field(
              secret,
              t('onboarding.keyLabel'),
              secret.isSet && !keyValue ? t('onboarding.keySaved') : undefined
            )}
        </>
      )}

      {((!local && address) || (local && secret)) && (
        <details className="border-t border-neutral-200 pt-4 dark:border-zinc-700">
          <summary className="cursor-pointer text-xs font-bold">{t('onboarding.advanced')}</summary>
          <div className="mt-4">
            {local && secret
              ? field(secret, t('onboarding.keyOptional'))
              : address &&
                field(address, t('onboarding.customAddress'), t('onboarding.customAddressHint'))}
          </div>
        </details>
      )}

      <p className="text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
        {t('onboarding.probeNotice')}
      </p>

      <ConnectStatus progress={progress} failure={failure} name={name} />

      <div className="flex flex-wrap justify-between gap-3 border-t border-neutral-200 pt-5 dark:border-zinc-700">
        <BrutalButton onClick={onBack} disabled={busy}>
          {t('onboarding.changeService')}
        </BrutalButton>
        <div className="flex flex-wrap gap-2">
          {failure && failure !== 'auth' && (
            <BrutalButton variant="ghost" disabled={busy} onClick={onSkipCheck}>
              {t('onboarding.continueAnyway')}
            </BrutalButton>
          )}
          <BrutalButton variant="dark" disabled={!ready || busy} onClick={onConnect}>
            {t(failure ? 'onboarding.retry' : 'onboarding.connect')}
          </BrutalButton>
        </div>
      </div>
    </div>
  );
}

function ConnectStatus({
  progress,
  failure,
  name,
}: {
  progress: Progress | null;
  failure: Failure | null;
  name: string;
}): React.ReactElement | null {
  const { t } = useI18n();
  if (progress)
    return (
      <p role="status" aria-live="polite" className="text-sm font-bold">
        {t(`onboarding.progress_${progress}`)}
      </p>
    );
  if (failure)
    return (
      <p role="alert" className="border-l-4 border-brutal-red px-3 py-2 text-sm leading-relaxed">
        {t(`onboarding.failure_${failure}`, { name })}
      </p>
    );
  return null;
}

function ChatGPTSignIn({
  onBack,
  onSignedIn,
  busy,
  failure,
}: {
  onBack: () => void;
  onSignedIn: () => void;
  busy: boolean;
  failure: Failure | null;
}): React.ReactElement {
  const { t } = useI18n();
  const [login, setLogin] = useState<ChatGPTLoginResponse | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void fetchChatGPTStatus().then((status) => setSignedIn(status?.connected === true));
  }, []);
  useEffect(() => {
    if (!login) return;
    const timer = setInterval(async () => {
      const status = await fetchChatGPTStatus();
      if (!status?.connected) return;
      setLogin(null);
      setSignedIn(true);
      onSignedIn();
    }, 3000);
    return () => clearInterval(timer);
  }, [login, onSignedIn]);

  return (
    <div className="space-y-6">
      <p className="text-sm leading-relaxed">{t('onboarding.chatgptExplain')}</p>
      {login?.verify_url ? (
        <div className="space-y-3 border-2 border-brutal-black p-4 dark:border-zinc-500">
          <p className="text-sm">{t('settings.providers.chatgpt.awaitingAuth')}</p>
          <a
            href={login.verify_url}
            target="_blank"
            rel="noreferrer"
            className="block break-all font-mono text-sm underline"
          >
            {login.verify_url}
          </a>
          <span className="inline-block select-all border-4 border-brutal-black px-3 py-2 font-mono text-2xl font-black tracking-[0.22em] dark:border-zinc-500">
            {login.user_code}
          </span>
          <p className="text-xs text-neutral-500 dark:text-neutral-400" role="status">
            {t('settings.providers.chatgpt.waiting')}
          </p>
        </div>
      ) : null}
      {error && (
        <p role="alert" className="border-l-4 border-brutal-red px-3 py-2 text-sm">
          {error}
        </p>
      )}
      {failure && (
        <p role="alert" className="border-l-4 border-brutal-red px-3 py-2 text-sm">
          {t(`onboarding.failure_${failure}`, { name: 'ChatGPT' })}
        </p>
      )}
      <div className="flex flex-wrap justify-between gap-3 border-t border-neutral-200 pt-5 dark:border-zinc-700">
        <BrutalButton onClick={onBack} disabled={busy}>
          {t('onboarding.changeService')}
        </BrutalButton>
        {signedIn ? (
          <BrutalButton variant="dark" disabled={busy} onClick={onSignedIn}>
            {t('onboarding.connect')}
          </BrutalButton>
        ) : (
          <BrutalButton
            variant="dark"
            disabled={busy || !!login}
            onClick={() =>
              void startChatGPTLogin().then((result) => {
                if (result.success) setLogin(result);
                else setError(t('onboarding.failure_unknown', { name: 'ChatGPT' }));
              })
            }
          >
            {t('onboarding.chatgptSignIn')}
          </BrutalButton>
        )}
      </div>
    </div>
  );
}
