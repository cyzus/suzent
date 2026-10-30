import React, { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  ApiField,
  ApiProvider,
  Model,
  ProviderRegion,
  CustomProviderPayload,
  fetchChatGPTStatus,
  logoutChatGPT,
  startChatGPTLogin,
  syncCapabilities,
  UserConfig,
} from '../../lib/api';
import type { ChatGPTLoginResponse, ChatGPTStatusResponse } from '../../types/api';
import { BrutalMultiSelect } from '../BrutalMultiSelect';
import { BrutalButton } from '../BrutalButton';
import { SettingsHeader } from './SettingsHeader';
import { SettingsPage } from './SettingsCard';
import {
  getProviderColor,
  getProviderInitials,
  getProviderVisual,
  normalizeProviderLogoUrl,
} from '../../lib/providerVisuals';
import { isImeComposing } from '../../lib/ime';

// Shared styling for the trailing action buttons attached to credential inputs
// (Change / Save / Cancel). Color denotes hierarchy; everything else stays consistent.
const FIELD_ACTION_BASE =
  'shrink-0 min-w-[5rem] px-3 text-[10px] font-black uppercase text-center border-2 border-brutal-black whitespace-nowrap transition-colors';
const FIELD_ACTION_OUTLINE =
  'bg-white dark:bg-zinc-900 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700';
const FIELD_ACTION_PRIMARY =
  'bg-brutal-black text-white hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed';

type ProviderTab = 'credentials' | 'models';

function modelDetails(model: Model, t: ReturnType<typeof useI18n>['t']): string {
  const details = [model.id];
  if (model.context_length) {
    details.push(
      t('settings.providers.modelContext', { count: model.context_length.toLocaleString() })
    );
  }
  if (model.supports_vision) details.push(t('settings.providers.modelVision'));
  if (model.supports_reasoning) details.push(t('settings.providers.modelReasoning'));
  if (model.supports_function_calling) details.push(t('settings.providers.modelTools'));
  if (model.description) details.push(model.description);
  return details.join(' · ');
}

function getProviderTitleClass(label: string): string {
  if (label.length > 18) return 'text-sm';
  if (label.length > 12) return 'text-base';
  if (label.length > 9) return 'text-lg';
  return 'text-xl';
}

interface ProvidersTabProps {
  onboarding?: boolean;
  onCredentialDraftChange?: (dirty: boolean) => void;
  providers: ApiProvider[];
  apiKeys: Record<string, string>;
  userConfigs: Record<string, UserConfig>;
  showKey: Record<string, boolean>;
  activeTabs: Record<string, ProviderTab>;
  verifying: Record<string, boolean>;
  verification?: Record<string, { success: boolean; message: string }>;
  onKeyChange: (key: string, val: string) => void;
  onToggleShowKey: (key: string) => void;
  onTabChange: (providerId: string, tab: ProviderTab) => void;
  onConfigChange: (providerId: string, config: UserConfig) => void;
  onAddCustomModel: (providerId: string, modelId: string) => void;
  onVerify: (provider: ApiProvider) => void;
  onAddProvider: (payload: CustomProviderPayload) => Promise<void>;
  onDeleteProvider: (providerId: string) => Promise<void>;
  onChatGPTAuthChanged?: () => Promise<void> | void;
}

// ─── KeyStatusBadge ──────────────────────────────────────────────────────────

function KeyStatusBadge({ fields }: { fields: ApiField[] }) {
  const { t } = useI18n();
  const secretFields = fields.filter((f) => f.type === 'secret');
  if (secretFields.length === 0) return null;
  const hasKey = secretFields.some((f) => f.isSet);

  return (
    <span
      className={`text-[9px] font-black uppercase tracking-wider px-1.5 py-0.5 border-2 ${hasKey ? 'border-brutal-black bg-brutal-black text-white dark:bg-emerald-400/10 dark:text-emerald-300 dark:border-emerald-400/25' : 'border-brutal-black text-brutal-black dark:border-white/15 dark:text-zinc-400 bg-transparent'}`}
    >
      {t(`settings.providers.${hasKey ? 'keySet' : 'noKey'}`)}
    </span>
  );
}

// ─── ProviderIcon ────────────────────────────────────────────────────────────

function ProviderIcon({ provider }: { provider: ApiProvider }) {
  const [imgFailed, setImgFailed] = useState(false);
  const color = getProviderColor(provider.id, provider.user_defined);
  // Built-in providers use the bundled logo; a remote one would be blocked by
  // the desktop CSP. A user-defined provider can still point at its own.
  const logoUrl =
    getProviderVisual(provider.id)?.logoUrl ?? normalizeProviderLogoUrl(provider.logo_url);
  const initials = getProviderInitials(provider.label);
  return (
    <div
      className="w-9 h-9 border-2 border-brutal-black flex items-center justify-center flex-shrink-0 shadow-brutal-sm"
      style={{ backgroundColor: `#${color}` }}
    >
      {logoUrl && !imgFailed ? (
        <img
          src={logoUrl}
          alt={provider.label}
          className="w-5 h-5 object-contain"
          onError={() => setImgFailed(true)}
        />
      ) : (
        <span className="text-[10px] font-black text-white select-none">{initials}</span>
      )}
    </div>
  );
}

// ─── RegionPicker ────────────────────────────────────────────────────────────

/** The provider's *_BASE_URL field, which a region choice writes. */
function baseUrlField(provider: ApiProvider): ApiField | undefined {
  return provider.fields.find((field) => field.key.includes('BASE_URL'));
}

/**
 * The region whose endpoint is in use: the saved Base URL's, the first when
 * none is saved, or none when the saved one matches no region (a custom URL).
 */
function activeRegion(provider: ApiProvider, baseUrl: string): ProviderRegion | undefined {
  const regions = provider.regions ?? [];
  const trimmed = baseUrl.trim().replace(/\/+$/, '');
  if (!trimmed) return regions[0];
  return regions.find((region) => region.base_url.replace(/\/+$/, '') === trimmed);
}

function regionName(region: ProviderRegion, locale: string): string {
  return locale.startsWith('zh') && region.name_zh ? region.name_zh : region.name;
}

interface RegionPickerProps {
  provider: ApiProvider;
  selected?: ProviderRegion;
  custom: boolean;
  onSelect: (region: ProviderRegion) => void;
  onCustom: () => void;
}

function RegionPicker({ provider, selected, custom, onSelect, onCustom }: RegionPickerProps) {
  const { t, locale } = useI18n();
  const regions = provider.regions ?? [];
  const label = provider.region_label === 'plan' ? 'plan' : 'region';
  const chip = (active: boolean) =>
    `border-2 border-brutal-black px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors ${
      active
        ? 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black'
        : 'bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-700'
    }`;
  return (
    <div className="space-y-1.5">
      <span className="block text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 tracking-wider">
        {t(`settings.providers.regionPicker.${label}`)}
      </span>
      <div role="radiogroup" className="flex flex-wrap gap-1.5">
        {regions.map((region) => {
          const active = !custom && selected?.id === region.id;
          return (
            <button
              key={region.id}
              type="button"
              role="radio"
              aria-checked={active}
              title={region.base_url}
              onClick={() => onSelect(region)}
              className={chip(active)}
            >
              {regionName(region, locale)}
            </button>
          );
        })}
        <button
          type="button"
          role="radio"
          aria-checked={custom}
          onClick={onCustom}
          className={chip(custom)}
        >
          {t('settings.providers.regionPicker.custom')}
        </button>
      </div>
      {provider.split_accounts && (
        <p className="text-[10px] text-neutral-500 dark:text-neutral-400">
          {t('settings.providers.regionPicker.splitAccounts')}
        </p>
      )}
    </div>
  );
}

// ─── AddProviderForm ─────────────────────────────────────────────────────────

const CUSTOM_PROTOCOLS = ['openai', 'anthropic'] as const;
type CustomProtocol = (typeof CUSTOM_PROTOCOLS)[number];

/** An id the backend accepts, derived from the display name. */
export function slugifyProviderId(label: string): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  if (!slug) return '';
  return (/^[a-z]/.test(slug) ? slug : `p_${slug}`).slice(0, 40);
}

/**
 * The provider a custom endpoint becomes: an API key field and a Base URL
 * field of its own, so both stay editable on its card afterwards.
 */
export function buildCustomProvider(form: {
  id: string;
  label: string;
  protocol: CustomProtocol;
  baseUrl: string;
  apiKey: string;
}): { payload: CustomProviderPayload; keyField: string; baseUrlField: string } {
  const prefix = `CUSTOM_${form.id.toUpperCase()}`;
  const keyField = `${prefix}_API_KEY`;
  const baseUrlFieldKey = `${prefix}_BASE_URL`;
  const baseUrl = form.baseUrl.trim().replace(/\/+$/, '');
  return {
    keyField,
    baseUrlField: baseUrlFieldKey,
    payload: {
      id: form.id,
      label: form.label.trim(),
      api_type: form.protocol,
      base_url: baseUrl,
      env_keys: [keyField],
      fields: [
        { key: keyField, label: 'API Key', placeholder: 'sk-...', type: 'secret' },
        { key: baseUrlFieldKey, label: 'Base URL', placeholder: baseUrl, type: 'text' },
      ],
      default_models: [],
      ...(!form.apiKey.trim() && { api_key_optional: true }),
    },
  };
}

interface AddProviderFormProps {
  onSave: (payload: CustomProviderPayload, keys: Record<string, string>) => Promise<void>;
  onCancel: () => void;
}

function AddProviderForm({ onSave, onCancel }: AddProviderFormProps) {
  const { t } = useI18n();
  const [saving, setSaving] = useState(false);
  const [label, setLabel] = useState('');
  const [id, setId] = useState('');
  const [idEdited, setIdEdited] = useState(false);
  const [protocol, setProtocol] = useState<CustomProtocol>('openai');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [error, setError] = useState('');

  const providerId = idEdited ? id : slugifyProviderId(label);
  const inputClass =
    'w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500';
  const labelClass =
    'block text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 tracking-wider';

  const handleSave = async () => {
    if (!label.trim()) {
      setError(t('settings.providers.addForm.nameRequired'));
      return;
    }
    if (!/^[a-z][a-z0-9_]{0,39}$/.test(providerId)) {
      setError(t('settings.providers.addForm.idInvalid'));
      return;
    }
    if (!/^https?:\/\/\S+$/.test(baseUrl.trim())) {
      setError(t('settings.providers.addForm.baseUrlInvalid'));
      return;
    }
    setSaving(true);
    setError('');
    const custom = buildCustomProvider({ id: providerId, label, protocol, baseUrl, apiKey });
    try {
      await onSave(custom.payload, {
        [custom.baseUrlField]: custom.payload.base_url ?? '',
        ...(apiKey.trim() && { [custom.keyField]: apiKey.trim() }),
      });
    } catch (e: any) {
      setError(e.message || t('settings.providers.addForm.saveFailed'));
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 border-2 border-brutal-black bg-white p-4 shadow-brutal-sm dark:bg-zinc-800 sm:p-5">
      <div>
        <h3 className="font-black uppercase text-lg tracking-wide dark:text-white">
          {t('settings.providers.addForm.title')}
        </h3>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t('settings.providers.addForm.subtitle')}
        </p>
      </div>

      <div className="space-y-1">
        <label htmlFor="custom-provider-name" className={labelClass}>
          {t('settings.providers.addForm.name')} *
        </label>
        <input
          id="custom-provider-name"
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="My Relay"
          className={inputClass}
        />
        <p className="flex flex-wrap items-center gap-1 text-[10px] text-neutral-500 dark:text-neutral-400">
          <span>{t('settings.providers.addForm.id')}</span>
          <input
            type="text"
            aria-label={t('settings.providers.addForm.id')}
            value={providerId}
            onChange={(e) => {
              setIdEdited(true);
              setId(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'));
            }}
            placeholder="my_relay"
            className="min-w-0 flex-1 border-b border-dashed border-neutral-400 bg-transparent font-mono text-[10px] focus:outline-none dark:text-white"
          />
        </p>
      </div>

      <div className="space-y-1.5">
        <span className={labelClass}>{t('settings.providers.addForm.protocol')}</span>
        <div role="radiogroup" className="grid gap-2 sm:grid-cols-2">
          {CUSTOM_PROTOCOLS.map((option) => {
            const active = protocol === option;
            return (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setProtocol(option)}
                className={`border-2 border-brutal-black p-2.5 text-left transition-colors ${
                  active
                    ? 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black'
                    : 'bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-700'
                }`}
              >
                <span className="block text-xs font-black uppercase">
                  {t(`settings.providers.addForm.protocols.${option}`)}
                </span>
                <span className="block font-mono text-[10px] opacity-70">
                  {option === 'openai' ? '/chat/completions' : '/messages'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-1">
        <label htmlFor="custom-provider-base-url" className={labelClass}>
          {t('settings.providers.addForm.baseUrl')} *
        </label>
        <input
          id="custom-provider-base-url"
          type="url"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder={
            protocol === 'openai' ? 'https://api.example.com/v1' : 'https://api.example.com'
          }
          className={inputClass}
        />
        <p className="text-[10px] text-neutral-500 dark:text-neutral-400">
          {t(`settings.providers.addForm.baseUrlHint.${protocol}`)}
        </p>
      </div>

      <div className="space-y-1">
        <label htmlFor="custom-provider-api-key" className={labelClass}>
          {t('settings.providers.addForm.apiKey')}
        </label>
        <div className="flex">
          <input
            id="custom-provider-api-key"
            type={showApiKey ? 'text' : 'password'}
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            className={`${inputClass} ${apiKey ? 'border-r-0' : ''}`}
          />
          {apiKey && (
            <button
              type="button"
              onClick={() => setShowApiKey((v) => !v)}
              title={t(`settings.providers.${showApiKey ? 'hideKey' : 'showKey'}`)}
              className="w-9 shrink-0 border-2 border-brutal-black bg-white font-mono text-xs hover:bg-neutral-100 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-800"
            >
              {showApiKey ? '○' : '●'}
            </button>
          )}
        </div>
        <p className="text-[10px] text-neutral-500 dark:text-neutral-400">
          {t('settings.providers.addForm.apiKeyHint')}
        </p>
      </div>

      {error && (
        <p role="alert" className="text-red-600 text-xs font-bold">
          {error}
        </p>
      )}

      <div className="flex gap-3 justify-end pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-xs font-black uppercase border-2 border-brutal-black hover:bg-neutral-100 dark:hover:bg-zinc-700 dark:text-white"
        >
          {t('common.cancel')}
        </button>
        <BrutalButton
          variant="dark"
          onClick={handleSave}
          disabled={saving}
          className="text-xs px-4 py-2 font-black uppercase"
        >
          {saving ? t('common.saving') : t('settings.providers.addForm.save')}
        </BrutalButton>
      </div>
    </div>
  );
}

function ChatGPTProviderCard({
  provider,
  config,
  onConfigChange,
  onAuthChanged,
  onVerify,
  verifying,
  verification,
}: {
  provider: ApiProvider;
  config: UserConfig;
  onConfigChange: (providerId: string, config: UserConfig) => void;
  onAuthChanged?: () => Promise<void> | void;
  onVerify: (provider: ApiProvider) => void;
  verifying: boolean;
  verification?: { success: boolean; message: string };
}): React.ReactElement {
  const { t } = useI18n();
  const [status, setStatus] = useState<ChatGPTStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingLogin, setPendingLogin] = useState<ChatGPTLoginResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const result = await fetchChatGPTStatus();
      setStatus(result);
      setError(result?.error ?? null);
      if (result?.connected && config.enabled_models.length === 0) {
        const defaults = provider.default_models.map((m) => m.id);
        if (defaults.length > 0) {
          onConfigChange(provider.id, { ...config, enabled_models: defaults });
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [provider.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll /chatgpt/status until connected, while device code is displayed
  useEffect(() => {
    if (!pendingLogin) return;
    const timer = setInterval(async () => {
      const result = await fetchChatGPTStatus();
      if (result?.connected) {
        setPendingLogin(null);
        setStatus(result);
        if (config.enabled_models.length === 0) {
          const defaults = provider.default_models.map((m) => m.id);
          if (defaults.length > 0)
            onConfigChange(provider.id, { ...config, enabled_models: defaults });
        }
        await onAuthChanged?.();
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [pendingLogin]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSignIn = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await startChatGPTLogin();
      if (result.success) {
        setPendingLogin(result);
      } else {
        setError(result.error ?? 'Failed to start login');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    setLoading(true);
    setError(null);
    setPendingLogin(null);
    try {
      await logoutChatGPT();
      await refresh();
      await onAuthChanged?.();
    } finally {
      setLoading(false);
    }
  };

  const statusKey = status?.status ?? 'not_logged_in';
  const connected = status?.connected === true;
  const allModels =
    provider.models.length > 0 ? [...provider.models] : [...(provider.default_models || [])];

  for (const model of provider.models || []) {
    const index = allModels.findIndex((x) => x.id === model.id);
    if (index === -1) allModels.push(model);
    else allModels[index] = { ...allModels[index], ...model };
  }

  for (const modelId of config.custom_models) {
    if (!allModels.find((x) => x.id === modelId)) {
      allModels.push({ id: modelId, name: modelId });
    }
  }

  for (const modelId of config.enabled_models) {
    if (!allModels.find((x) => x.id === modelId)) {
      allModels.push({ id: modelId, name: modelId });
    }
  }
  const statusLabel = t(`settings.providers.chatgpt.status.${statusKey}` as any);
  const statusActionLabel = connected
    ? t('settings.providers.chatgpt.disconnect')
    : t('settings.providers.chatgpt.signIn');

  return (
    <details className="border-2 border-brutal-black bg-white shadow-brutal-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:shadow-none">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 bg-neutral-50 p-3 dark:bg-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <ProviderIcon provider={provider} />
          <div className="flex flex-col min-w-0">
            <span
              className={`font-black uppercase tracking-wide leading-tight dark:text-white whitespace-normal break-normal [overflow-wrap:normal] ${getProviderTitleClass(provider.label)}`}
            >
              {provider.label}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`hidden text-[10px] font-black uppercase sm:inline ${connected ? 'text-green-700 dark:text-green-400' : 'text-neutral-500 dark:text-neutral-400'}`}
          >
            {statusLabel}
          </span>
          <span className="text-[10px] font-bold">
            {t('settings.providers.enabledCount', { count: config.enabled_models.length })}
          </span>
          <span aria-hidden="true">▾</span>
        </div>
      </summary>

      <div className="flex flex-1 flex-col gap-4 border-t-2 border-brutal-black p-4 dark:border-zinc-600">
        <div className="flex flex-wrap items-center justify-between gap-3 border-2 border-brutal-black bg-neutral-50 p-3 dark:bg-zinc-900">
          <div className="flex min-w-0 items-center gap-2" role="status">
            <span
              className={`h-3 w-3 shrink-0 border-2 border-brutal-black ${connected ? 'bg-brutal-green' : 'bg-neutral-300'}`}
              aria-hidden="true"
            />
            <span className="text-xs font-bold">
              {loading
                ? t('settings.providers.chatgpt.loadingStatus')
                : pendingLogin
                  ? t('settings.providers.chatgpt.waiting')
                  : statusLabel}
            </span>
          </div>
          <BrutalButton
            type="button"
            variant={connected ? 'default' : 'primary'}
            size="xs"
            onClick={connected ? handleDisconnect : handleSignIn}
            disabled={loading || !!pendingLogin}
            title={pendingLogin ? statusLabel : statusActionLabel}
          >
            {statusActionLabel}
          </BrutalButton>
        </div>
        {pendingLogin && (
          <div className="space-y-3 p-3 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900">
            <p className="text-xs font-bold text-neutral-700 dark:text-neutral-300">
              {t('settings.providers.chatgpt.awaitingAuth')}
            </p>
            <a
              href={pendingLogin.verify_url}
              target="_blank"
              rel="noreferrer"
              className="block text-xs font-mono underline text-blue-600 dark:text-blue-400 break-all"
            >
              {pendingLogin.verify_url}
            </a>
            <div className="flex flex-col gap-2">
              <span className="inline-flex w-fit max-w-full font-mono text-xl sm:text-2xl font-black tracking-[0.22em] border-4 border-brutal-black px-3 py-2 dark:text-white select-all whitespace-nowrap overflow-x-auto">
                {pendingLogin.user_code}
              </span>
              <span className="text-[10px] text-neutral-400 uppercase font-bold animate-pulse">
                {t('settings.providers.chatgpt.waiting')}
              </span>
            </div>
          </div>
        )}

        {error && (
          <div className="border-2 border-red-600 bg-red-50 dark:bg-red-950/30 px-3 py-2">
            <p className="text-[11px] font-bold text-red-600">{error}</p>
          </div>
        )}

        {(pendingLogin || loading) && (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-2 border-b-2 border-neutral-200 dark:border-zinc-700 pb-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-400 sm:mr-auto">
              {loading
                ? t('settings.providers.chatgpt.loadingStatus')
                : t('settings.providers.chatgpt.subtitle')}
            </span>
            <div className="flex gap-2 sm:justify-end">
              {pendingLogin && (
                <button
                  onClick={() => setPendingLogin(null)}
                  disabled={loading}
                  className="px-3 py-1.5 text-[10px] font-black uppercase border-2 border-brutal-black text-neutral-500 dark:text-neutral-400 bg-white dark:bg-zinc-900 hover:bg-neutral-100 dark:hover:bg-zinc-700 disabled:opacity-50"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        )}

        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[10px] font-black uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                {t('settings.providers.modelsTab')}
              </p>
              <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
                {t('settings.providers.modelsAvailable', { count: String(allModels.length) })}
              </p>
            </div>
            <BrutalButton
              variant="primary"
              onClick={() => onVerify(provider)}
              disabled={verifying || !connected}
              className="text-xs px-4 py-2 font-black uppercase shrink-0"
            >
              {verifying ? t('settings.providers.fetching') : t('settings.providers.fetch')}
            </BrutalButton>
          </div>
          {verification && (
            <p
              role="status"
              className={`border-l-4 px-3 py-2 text-xs ${verification.success ? 'border-brutal-green' : 'border-brutal-red'}`}
            >
              {verification.message}
            </p>
          )}
          <BrutalMultiSelect
            variant="list"
            value={config.enabled_models}
            onChange={(newVal) =>
              onConfigChange(provider.id, { ...config, enabled_models: newVal })
            }
            options={allModels.map((m) => ({
              value: m.id,
              label: m.name || m.id,
              description: modelDetails(m, t),
            }))}
            emptyMessage={t('settings.providers.noModelsFound')}
            dropdownClassName="max-h-56"
          />
        </div>
      </div>
    </details>
  );
}

// ─── ProviderCatalog ─────────────────────────────────────────────────────────

const CATALOG_GROUPS = ['global', 'china', 'relay', 'local'] as const;

interface ProviderCatalogProps {
  providers: ApiProvider[];
  showCustom: boolean;
  customOpen: boolean;
  customForm: React.ReactNode;
  onPick: (provider: ApiProvider) => void;
  onCustom: () => void;
}

const ProviderCatalog = React.forwardRef<HTMLElement, ProviderCatalogProps>(
  function ProviderCatalog(
    { providers, showCustom, customOpen, customForm, onPick, onCustom },
    ref
  ) {
    const { t } = useI18n();
    // The backend already puts China first for Chinese users.
    const order = [...new Set([...providers.map((p) => p.group ?? 'global'), ...CATALOG_GROUPS])];
    const tile =
      'flex min-w-0 items-center gap-3 border-2 border-brutal-black bg-white p-2.5 text-left transition-colors hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue dark:border-zinc-600 dark:bg-zinc-900 dark:text-white dark:hover:bg-zinc-700';
    return (
      <section
        ref={ref}
        aria-labelledby="provider-catalog-title"
        className="space-y-4 border-2 border-brutal-black bg-neutral-50 p-4 shadow-brutal-sm dark:border-zinc-600 dark:bg-zinc-800 dark:shadow-none"
      >
        <div>
          <h3
            id="provider-catalog-title"
            className="font-black uppercase text-lg tracking-wide dark:text-white"
          >
            {t('settings.providers.catalog.title')}
          </h3>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {t('settings.providers.catalog.subtitle')}
          </p>
        </div>
        {order.map((group) => {
          const members = providers.filter((p) => (p.group ?? 'global') === group);
          if (members.length === 0) return null;
          return (
            <div key={group} className="space-y-2">
              <h4 className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                {t(`settings.providers.catalog.groups.${group}`)}
              </h4>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {members.map((provider) => (
                  <button
                    key={provider.id}
                    type="button"
                    onClick={() => onPick(provider)}
                    className={tile}
                  >
                    <ProviderIcon provider={provider} />
                    <span className="min-w-0 text-xs font-black uppercase leading-tight">
                      {provider.label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
        {showCustom && (
          <div className="space-y-2">
            <h4 className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
              {t('settings.providers.catalog.groups.custom')}
            </h4>
            {customOpen ? (
              customForm
            ) : (
              <button type="button" onClick={onCustom} className={`${tile} w-full`}>
                <span className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-dashed border-brutal-black text-lg font-black dark:border-zinc-500">
                  +
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-black uppercase">
                    {t('settings.providers.catalog.customTitle')}
                  </span>
                  <span className="block text-[10px] text-neutral-500 dark:text-neutral-400">
                    {t('settings.providers.catalog.customHint')}
                  </span>
                </span>
              </button>
            )}
          </div>
        )}
      </section>
    );
  }
);

// ─── ProvidersTab ─────────────────────────────────────────────────────────────

export function ProvidersTab({
  onboarding = false,
  onCredentialDraftChange,
  providers,
  apiKeys,
  userConfigs,
  showKey,
  activeTabs,
  verifying,
  verification = {},
  onKeyChange,
  onToggleShowKey,
  onTabChange,
  onConfigChange,
  onAddCustomModel,
  onVerify,
  onAddProvider,
  onDeleteProvider,
  onChatGPTAuthChanged,
}: ProvidersTabProps): React.ReactElement {
  const { t } = useI18n();
  const providerPanels = useRef<Record<string, HTMLElement | null>>({});
  const [jumpTarget, setJumpTarget] = useState<string | null>(null);
  useEffect(() => {
    if (!jumpTarget) return;
    const panel = providerPanels.current[jumpTarget];
    const details = panel instanceof HTMLDetailsElement ? panel : panel?.querySelector('details');
    if (details) {
      details.open = true;
      details.scrollIntoView({ block: 'nearest' });
      details.querySelector('summary')?.focus();
    }
    setJumpTarget(null);
  }, [jumpTarget]);
  const enabledGroups = providers
    .map((provider) => ({
      provider,
      models: [
        ...new Set((userConfigs[provider.id] || provider.user_config)?.enabled_models || []),
      ],
    }))
    .filter((group) => group.models.length > 0);
  const enabledCount = enabledGroups.reduce((total, group) => total + group.models.length, 0);
  const [query, setQuery] = useState('');
  const [modelQueries, setModelQueries] = useState<Record<string, string>>({});
  const [modelDrafts, setModelDrafts] = useState<Record<string, string>>({});
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  // Tracks which secret field keys are currently in edit mode (user clicked "Change")
  const [editingFields, setEditingFields] = useState<Set<string>>(new Set());
  // Providers whose Base URL is being typed by hand rather than picked.
  const [customRegion, setCustomRegion] = useState<Set<string>>(new Set());
  useEffect(() => {
    onCredentialDraftChange?.(editingFields.size > 0 || Object.keys(keyDrafts).length > 0);
  }, [editingFields, keyDrafts, onCredentialDraftChange]);

  const startEditing = (fieldKey: string) => {
    setEditingFields((prev) => new Set(prev).add(fieldKey));
    setKeyDrafts((prev) => ({ ...prev, [fieldKey]: '' }));
  };

  const cancelEditing = (field: ApiField) => {
    // Backing out of a custom Base URL goes back to the region picker.
    setCustomRegion((prev) => {
      const owners = providers.filter((p) => p.fields.some((f) => f.key === field.key));
      if (!owners.some((p) => prev.has(p.id))) return prev;
      const next = new Set(prev);
      for (const owner of owners) next.delete(owner.id);
      return next;
    });
    setEditingFields((prev) => {
      const s = new Set(prev);
      s.delete(field.key);
      return s;
    });
    setKeyDrafts((prev) => {
      const next = { ...prev };
      delete next[field.key];
      return next;
    });
  };

  // Only committed drafts enter the parent autosave state.
  const confirmEditing = (field: ApiField) => {
    onKeyChange(field.key, keyDrafts[field.key] ?? '');
    setKeyDrafts((prev) => {
      const next = { ...prev };
      delete next[field.key];
      return next;
    });
    setEditingFields((prev) => {
      const s = new Set(prev);
      s.delete(field.key);
      return s;
    });
  };

  // Providers picked from the catalog this session stay listed while being set up.
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [catalogOpen, setCatalogOpen] = useState(false);
  const catalogRef = useRef<HTMLElement | null>(null);

  const isConfigured = (provider: ApiProvider) =>
    provider.user_defined ||
    added.has(provider.id) ||
    ((userConfigs[provider.id] || provider.user_config)?.enabled_models?.length ?? 0) > 0 ||
    provider.fields.some((field) => field.isSet || !!apiKeys[field.key]);
  const matches = (provider: ApiProvider) =>
    `${provider.label} ${provider.id}`.toLowerCase().includes(query.trim().toLowerCase());
  // Onboarding keeps the flat list; Settings lists only what is in use.
  const listed = onboarding ? providers : providers.filter(isConfigured);
  const catalog = onboarding ? [] : providers.filter((provider) => !isConfigured(provider));
  const showCatalog =
    !onboarding &&
    (catalogOpen || listed.length === 0 || (!!query.trim() && catalog.some(matches)));

  const pickFromCatalog = (provider: ApiProvider) => {
    setAdded((prev) => new Set(prev).add(provider.id));
    setCatalogOpen(false);
    setQuery('');
    setJumpTarget(provider.id);
  };

  const openCatalog = () => {
    setCatalogOpen(true);
    requestAnimationFrame(() => catalogRef.current?.scrollIntoView({ block: 'start' }));
  };

  const handleSaveProvider = async (
    payload: CustomProviderPayload,
    keys: Record<string, string>
  ) => {
    await onAddProvider(payload);
    for (const [key, value] of Object.entries(keys)) onKeyChange(key, value);
    setShowAddForm(false);
    setCatalogOpen(false);
    setQuery('');
    setJumpTarget(payload.id);
  };

  const handleDelete = async (providerId: string) => {
    setDeletingId(providerId);
    try {
      await onDeleteProvider(providerId);
    } finally {
      setDeletingId(null);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await syncCapabilities();
      if (result.success) {
        setSyncResult(
          t('settings.providers.syncDone', {
            providers: String(result.providers ?? 0),
            models: String(result.models ?? 0),
          })
        );
      } else {
        setSyncResult(result.error || t('settings.providers.syncFailed'));
      }
    } finally {
      setSyncing(false);
      setTimeout(() => setSyncResult(null), 5000);
    }
  };

  return (
    <SettingsPage>
      {!onboarding && (
        <SettingsHeader
          title={t('settings.providers.title')}
          subtitle={t('settings.providers.subtitle')}
          actions={
            !onboarding && (
              <>
                {syncResult && (
                  <span className="text-[10px] font-bold text-neutral-300 max-w-[200px] truncate">
                    {syncResult}
                  </span>
                )}
                <BrutalButton
                  onClick={handleSync}
                  disabled={syncing}
                  title={t('settings.providers.syncTooltip')}
                  variant="primary"
                  size="sm"
                >
                  {syncing ? t('settings.providers.syncing') : t('settings.providers.sync')}
                </BrutalButton>
                <BrutalButton
                  onClick={() =>
                    showCatalog && listed.length > 0 ? setCatalogOpen(false) : openCatalog()
                  }
                  variant="light"
                  size="sm"
                  aria-expanded={showCatalog}
                >
                  {showCatalog && listed.length > 0
                    ? t('common.cancel')
                    : t('settings.providers.addProvider')}
                </BrutalButton>
              </>
            )
          }
        />
      )}

      <details className="border-2 border-brutal-black bg-white shadow-brutal-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:shadow-none">
        <summary className="cursor-pointer p-3 text-sm font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue">
          {t('settings.providers.enabledSummary', {
            models: enabledCount,
            providers: enabledGroups.length,
          })}
        </summary>
        <div className="space-y-3 border-t-2 border-brutal-black p-3 dark:border-zinc-600">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {t('settings.providers.enabledSummaryHint')}
          </p>
          {enabledCount === 0 && <p className="text-xs">{t('settings.providers.enabledEmpty')}</p>}
          {enabledGroups.map(({ provider, models }) => (
            <div key={provider.id}>
              <h3 className="mb-2 text-xs font-black uppercase">{provider.label}</h3>
              <div className="flex flex-wrap gap-2">
                {models.map((id) => {
                  const model = [...provider.models, ...provider.default_models].find(
                    (item) => item.id === id
                  );
                  return (
                    <BrutalButton
                      key={id}
                      size="xs"
                      title={id}
                      onClick={() => {
                        setQuery('');
                        setModelQueries((prev) => ({ ...prev, [provider.id]: '' }));
                        onTabChange(provider.id, 'models');
                        setJumpTarget(provider.id);
                      }}
                      className="max-w-full break-all text-left"
                    >
                      {model?.name || id}
                      <span aria-hidden="true">↗</span>
                    </BrutalButton>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </details>

      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        aria-label={t('settings.providers.searchProviders')}
        placeholder={t('settings.providers.searchProviders')}
        className="w-full border-2 border-brutal-black bg-white px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400"
      />
      {!providers.some(matches) && (
        <p className="text-sm dark:text-white">{t('settings.providers.noMatchingProviders')}</p>
      )}
      <div className="space-y-3">
        {listed.map((provider) => {
          const visible = matches(provider);
          const activeTab = activeTabs[provider.id] || 'credentials';
          const conf = userConfigs[provider.id] || { enabled_models: [], custom_models: [] };
          const isEnabled = conf.enabled_models.length > 0;
          const regionField = provider.regions?.length ? baseUrlField(provider) : undefined;
          const savedBaseUrl = regionField
            ? (keyDrafts[regionField.key] ?? apiKeys[regionField.key] ?? '')
            : '';
          const region = regionField ? activeRegion(provider, savedBaseUrl) : undefined;
          // A saved URL that is none of the regions' was typed by hand.
          const customBaseUrl =
            !!regionField && (customRegion.has(provider.id) || (!!savedBaseUrl.trim() && !region));
          const keyUrl = (!customBaseUrl && region?.key_url) || provider.key_url;

          if (provider.id === 'chatgpt') {
            return (
              <div
                key={provider.id}
                ref={(element) => {
                  providerPanels.current[provider.id] = element;
                }}
                className={visible ? '' : 'hidden'}
              >
                <ChatGPTProviderCard
                  provider={provider}
                  config={conf}
                  onConfigChange={onConfigChange}
                  onAuthChanged={onChatGPTAuthChanged}
                  onVerify={onVerify}
                  verifying={!!verifying[provider.id]}
                  verification={verification[provider.id]}
                />
              </div>
            );
          }

          const allModels =
            provider.models.length > 0
              ? [...provider.models]
              : [...(provider.default_models || [])];

          for (const model of provider.models || []) {
            const index = allModels.findIndex((x) => x.id === model.id);
            if (index === -1) allModels.push(model);
            else allModels[index] = { ...allModels[index], ...model };
          }

          for (const modelId of conf.custom_models) {
            if (!allModels.find((x) => x.id === modelId)) {
              allModels.push({ id: modelId, name: modelId });
            }
          }

          for (const modelId of conf.enabled_models) {
            if (!allModels.find((x) => x.id === modelId)) {
              allModels.push({ id: modelId, name: modelId });
            }
          }

          return (
            <details
              ref={(element) => {
                providerPanels.current[provider.id] = element;
              }}
              key={provider.id}
              className={`${visible ? '' : 'hidden'} border-2 border-brutal-black bg-white shadow-brutal-sm dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:shadow-none`}
            >
              {/* Provider Header */}
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 bg-neutral-50 p-3 dark:bg-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue">
                <div className="flex flex-1 items-center gap-3 min-w-0">
                  <ProviderIcon provider={provider} />
                  <div className="flex flex-col min-w-0">
                    <span
                      className={`block max-w-full whitespace-normal break-normal [overflow-wrap:normal] font-black uppercase tracking-wide leading-tight dark:text-white ${getProviderTitleClass(provider.label)}`}
                      title={provider.label}
                    >
                      {provider.label}
                    </span>
                    {provider.user_defined && !onboarding && (
                      <span className="text-[9px] font-bold uppercase tracking-wider text-neutral-400">
                        {t('settings.providers.customProvider')}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <KeyStatusBadge
                    fields={provider.fields.map((field) => ({
                      ...field,
                      isSet: field.isSet || !!apiKeys[field.key],
                    }))}
                  />
                  <span className="text-[10px] font-bold">
                    {t('settings.providers.enabledCount', { count: conf.enabled_models.length })}
                  </span>
                  <span aria-hidden="true">▾</span>
                  <div
                    className={`w-4 h-4 rounded-full border-2 border-brutal-black dark:border-zinc-500 ${isEnabled ? 'bg-brutal-green' : 'bg-transparent'}`}
                  ></div>
                </div>
              </summary>

              {/* Tabs */}
              <div className="flex border-b-2 border-brutal-black bg-brutal-black">
                <button
                  onClick={() => onTabChange(provider.id, 'credentials')}
                  className={`flex-1 border-r-2 border-brutal-black p-2 text-xs font-bold uppercase tracking-wider transition-colors ${activeTab === 'credentials' ? 'bg-brutal-black text-white dark:bg-zinc-900' : 'bg-white text-brutal-black hover:bg-neutral-100 dark:bg-zinc-800 dark:text-white dark:hover:bg-zinc-700'}`}
                >
                  {t('settings.providers.apiKeysTab')}
                </button>
                <button
                  onClick={() => onTabChange(provider.id, 'models')}
                  className={`flex-1 p-2 font-bold uppercase text-xs tracking-wider transition-colors ${activeTab === 'models' ? 'bg-brutal-black text-white dark:bg-zinc-900' : 'bg-white dark:bg-zinc-800 text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700'}`}
                >
                  {t('settings.providers.modelsTab')}
                </button>
              </div>

              <div className="flex flex-1 flex-col gap-4 p-4">
                {activeTab === 'credentials' && (
                  <div className="space-y-4">
                    {regionField && (
                      <RegionPicker
                        provider={provider}
                        selected={region}
                        custom={customBaseUrl}
                        onSelect={(picked) => {
                          setCustomRegion((prev) => {
                            const next = new Set(prev);
                            next.delete(provider.id);
                            return next;
                          });
                          onKeyChange(regionField.key, picked.base_url);
                        }}
                        onCustom={() => {
                          setCustomRegion((prev) => new Set(prev).add(provider.id));
                          startEditing(regionField.key);
                        }}
                      />
                    )}
                    {keyUrl && (
                      <a
                        href={keyUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-block text-xs font-bold underline text-blue-600 dark:text-blue-400"
                      >
                        {t('settings.providers.getKey', { provider: provider.label })}
                      </a>
                    )}
                    {provider.fields.map((field) => {
                      // A picked region already says where requests go.
                      if (field.key === regionField?.key && !customBaseUrl) return null;
                      const val = keyDrafts[field.key] ?? apiKeys[field.key] ?? '';
                      const isConfigured =
                        (field.isSet || !!apiKeys[field.key]) &&
                        !editingFields.has(field.key) &&
                        keyDrafts[field.key] === undefined;
                      const isEnvKey = field.source === 'env'; // display-only hint

                      return (
                        <div key={field.key} className="space-y-1">
                          <div className="flex items-center justify-between">
                            <label className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400 tracking-wider">
                              {field.label}
                            </label>
                            {isConfigured && (
                              <span className="text-[9px] font-bold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                                {t(
                                  `settings.providers.${isEnvKey ? 'environmentValue' : 'savedValue'}`
                                )}
                              </span>
                            )}
                          </div>

                          {isConfigured ? (
                            /* Locked/display state */
                            <div className="flex gap-0 min-w-0">
                              <div className="flex-1 min-w-0 flex items-center bg-neutral-100 dark:bg-zinc-800 border-2 border-brutal-black px-3 py-2">
                                <span className="font-mono text-xs text-neutral-500 dark:text-neutral-400 truncate">
                                  {field.type === 'secret' ? '••••••••' : val}
                                </span>
                              </div>
                              <button
                                onClick={() => startEditing(field.key)}
                                className={`border-l-0 ${FIELD_ACTION_BASE} ${FIELD_ACTION_OUTLINE}`}
                              >
                                {t('settings.providers.changeKey')}
                              </button>
                            </div>
                          ) : (
                            /* Edit state */
                            (() => {
                              const isEditing = editingFields.has(field.key);
                              const showToggle = field.type === 'secret' && val.length > 0;
                              // Confirm/Cancel pair only when actively editing a previously-set field
                              const showConfirm = keyDrafts[field.key] !== undefined;
                              const showCancel = isEditing || keyDrafts[field.key] !== undefined;
                              const canConfirm = val.trim().length > 0;
                              const hasRight = showToggle || showConfirm || showCancel;
                              return (
                                <div className="flex gap-0">
                                  <div className="relative flex-1">
                                    <input
                                      type={
                                        field.type === 'secret'
                                          ? showKey[field.key]
                                            ? 'text'
                                            : 'password'
                                          : 'text'
                                      }
                                      aria-label={field.label}
                                      autoComplete="off"
                                      value={val}
                                      onChange={(e) =>
                                        setKeyDrafts((prev) => ({
                                          ...prev,
                                          [field.key]: e.target.value,
                                        }))
                                      }
                                      onKeyDown={(e) => {
                                        if (isImeComposing(e)) return;
                                        if (e.key === 'Enter' && canConfirm) confirmEditing(field);
                                      }}
                                      placeholder={field.placeholder}
                                      autoFocus={isEditing}
                                      className={`w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 transition-all dark:text-white ${hasRight ? 'border-r-0' : ''}`}
                                    />
                                  </div>
                                  {showToggle && (
                                    <button
                                      onClick={() => onToggleShowKey(field.key)}
                                      className={`w-9 flex items-center justify-center bg-white dark:bg-zinc-900 border-2 border-brutal-black hover:bg-neutral-100 dark:hover:bg-zinc-800 font-mono text-xs dark:text-white select-none ${showConfirm || showCancel ? 'border-r-0' : ''}`}
                                      title={
                                        showKey[field.key]
                                          ? t('settings.providers.hideKey')
                                          : t('settings.providers.showKey')
                                      }
                                    >
                                      {showKey[field.key] ? '○' : '●'}
                                    </button>
                                  )}
                                  {showConfirm && (
                                    <button
                                      onClick={() => confirmEditing(field)}
                                      disabled={!canConfirm}
                                      className={`${FIELD_ACTION_BASE} ${FIELD_ACTION_PRIMARY} ${showCancel ? 'border-r-0' : ''}`}
                                    >
                                      {t('common.save')}
                                    </button>
                                  )}
                                  {showCancel && (
                                    <button
                                      onClick={() => cancelEditing(field)}
                                      className={`${FIELD_ACTION_BASE} ${FIELD_ACTION_OUTLINE}`}
                                    >
                                      {t('common.cancel')}
                                    </button>
                                  )}
                                </div>
                              );
                            })()
                          )}
                        </div>
                      );
                    })}
                    {provider.fields.length === 0 && (
                      <p className="text-xs text-neutral-400 italic">
                        {t('settings.providers.noCredentials')}
                      </p>
                    )}
                  </div>
                )}

                {activeTab === 'credentials' && (
                  <div className="space-y-2">
                    <BrutalButton
                      size="sm"
                      variant="primary"
                      disabled={
                        verifying[provider.id] ||
                        provider.fields.some(
                          (field) =>
                            keyDrafts[field.key] !== undefined || editingFields.has(field.key)
                        )
                      }
                      onClick={() => onVerify(provider)}
                    >
                      {verifying[provider.id]
                        ? t('settings.providers.fetching')
                        : t('settings.providers.testConnection')}
                    </BrutalButton>
                    <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
                      {t('settings.providers.connectionHint')}
                    </p>
                  </div>
                )}
                {verification[provider.id] && (
                  <p
                    role="status"
                    className={`border-l-4 px-3 py-2 text-xs ${verification[provider.id].success ? 'border-brutal-green' : 'border-brutal-red'}`}
                  >
                    {verification[provider.id].message}
                  </p>
                )}
                {provider.fields.some(
                  (field) => keyDrafts[field.key] !== undefined || editingFields.has(field.key)
                ) && (
                  <p className="text-xs text-amber-700 dark:text-amber-300">
                    {t('settings.providers.unsavedCredentials')}
                  </p>
                )}
                {activeTab === 'models' && (
                  <div className="flex flex-col h-full pt-2">
                    {/* Input Row with Fetch Button */}
                    <div className="flex flex-col sm:flex-row gap-2 mb-4 min-w-0">
                      <div className="flex flex-1 min-w-0 gap-0">
                        <input
                          type="text"
                          aria-label={t('settings.providers.addModelIdPlaceholder')}
                          value={modelDrafts[provider.id] || ''}
                          onChange={(event) =>
                            setModelDrafts((prev) => ({
                              ...prev,
                              [provider.id]: event.target.value,
                            }))
                          }
                          placeholder={t('settings.providers.addModelIdPlaceholder')}
                          className="flex-1 min-w-0 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
                          onKeyDown={(e) => {
                            if (isImeComposing(e)) return;
                            if (e.key === 'Enter') {
                              onAddCustomModel(provider.id, e.currentTarget.value);
                              setModelDrafts((prev) => ({ ...prev, [provider.id]: '' }));
                            }
                          }}
                        />
                        <button
                          type="button"
                          aria-label={t('settings.providers.addModelIdPlaceholder')}
                          disabled={!modelDrafts[provider.id]?.trim()}
                          onClick={() => {
                            onAddCustomModel(provider.id, modelDrafts[provider.id]);
                            setModelDrafts((prev) => ({ ...prev, [provider.id]: '' }));
                          }}
                          className="disabled:opacity-40 bg-brutal-black text-white w-10 font-bold border-2 border-brutal-black hover:bg-neutral-800 flex items-center justify-center text-lg"
                        >
                          +
                        </button>
                      </div>
                      <BrutalButton
                        variant="primary"
                        onClick={() => onVerify(provider)}
                        disabled={
                          verifying[provider.id] ||
                          provider.fields.some(
                            (field) =>
                              keyDrafts[field.key] !== undefined || editingFields.has(field.key)
                          )
                        }
                        className="text-xs px-4 py-2 font-black uppercase shrink-0"
                      >
                        {verifying[provider.id]
                          ? t('settings.providers.fetching')
                          : t('settings.providers.fetch')}
                      </BrutalButton>
                    </div>

                    <input
                      type="search"
                      value={modelQueries[provider.id] || ''}
                      onChange={(event) =>
                        setModelQueries((prev) => ({
                          ...prev,
                          [provider.id]: event.target.value,
                        }))
                      }
                      placeholder={t('settings.providers.searchModels')}
                      aria-label={t('settings.providers.searchModels')}
                      className="mb-3 border-2 border-brutal-black bg-white px-3 py-2 text-xs dark:bg-zinc-900 dark:text-white"
                    />
                    <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
                      {t('settings.providers.enabledCount', {
                        count: conf.enabled_models.length,
                      })}
                    </p>
                    {/* Models List (Scrollable) */}
                    <BrutalMultiSelect
                      variant="list"
                      value={conf.enabled_models}
                      onChange={(newVal) =>
                        onConfigChange(provider.id, { ...conf, enabled_models: newVal })
                      }
                      options={allModels
                        .filter((m) =>
                          `${m.name} ${m.id}`
                            .toLowerCase()
                            .includes((modelQueries[provider.id] || '').trim().toLowerCase())
                        )
                        .map((m) => ({
                          value: m.id,
                          label: m.name || m.id,
                          description: modelDetails(m, t),
                        }))}
                      emptyMessage={t('settings.providers.noModelsFound')}
                      emptyAction={
                        !(modelQueries[provider.id] || '').trim() && (
                          <button
                            disabled={
                              verifying[provider.id] ||
                              provider.fields.some(
                                (field) =>
                                  keyDrafts[field.key] !== undefined || editingFields.has(field.key)
                              )
                            }
                            onClick={() => onVerify(provider)}
                            className="underline hover:text-black"
                          >
                            {t('settings.providers.fetchModels')}
                          </button>
                        )
                      }
                      dropdownClassName="max-h-80"
                    />

                    {/* Footer */}
                    <div className="flex justify-between items-center px-1 mt-2">
                      <span className="text-[10px] text-neutral-500 dark:text-neutral-400 font-bold uppercase tracking-wider">
                        {t('settings.providers.modelsAvailable', {
                          count: String(allModels.length),
                        })}
                      </span>
                    </div>
                  </div>
                )}
                {provider.user_defined && !onboarding && (
                  <div className="border-t border-neutral-200 pt-3 dark:border-zinc-700">
                    <BrutalButton
                      size="xs"
                      variant="danger"
                      disabled={deletingId === provider.id}
                      onClick={() => handleDelete(provider.id)}
                    >
                      {t('settings.providers.deleteProvider')}
                    </BrutalButton>
                  </div>
                )}
              </div>
            </details>
          );
        })}
      </div>
      {showCatalog && (
        <ProviderCatalog
          ref={catalogRef}
          providers={catalog.filter(matches)}
          showCustom={!query.trim() || 'custom'.includes(query.trim().toLowerCase())}
          customOpen={showAddForm}
          onPick={pickFromCatalog}
          onCustom={() => setShowAddForm(true)}
          customForm={
            <AddProviderForm onSave={handleSaveProvider} onCancel={() => setShowAddForm(false)} />
          }
        />
      )}
      {onboarding && showAddForm && (
        <AddProviderForm onSave={handleSaveProvider} onCancel={() => setShowAddForm(false)} />
      )}
      {onboarding && (
        <BrutalButton variant="ghost" size="sm" onClick={() => setShowAddForm((v) => !v)}>
          {t(showAddForm ? 'common.cancel' : 'onboarding.otherProvider')}
        </BrutalButton>
      )}
    </SettingsPage>
  );
}
