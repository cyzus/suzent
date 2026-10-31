import React, { useEffect, useMemo, useState } from 'react';
import { BeakerIcon, CheckIcon, KeyIcon, TrashIcon, XMarkIcon } from '@heroicons/react/24/outline';

import { useI18n } from '../../i18n';
import {
  addMailAccount,
  fetchMailAccounts,
  fetchMailProviders,
  removeMailAccount,
  testMailAccount,
  updateMailAccount,
  type MailAccount,
  type MailProbeResult,
  type MailProvider,
} from '../../lib/api';
import { BrutalButton, BrutalIconButton } from '../BrutalButton';
import { BrutalOnOff } from '../BrutalOnOff';
import { BrutalSelect } from '../BrutalSelect';
import { SettingsHeader } from './SettingsHeader';
import {
  Badge,
  CollapsibleSettingsCard,
  SectionCardHeader,
  SettingsCard,
  SettingsListItem,
  SettingsPage,
} from './SettingsCard';

const INPUT_CLASS =
  'w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500';

type AddForm = {
  provider: string;
  email: string;
  password: string;
  displayName: string;
  imapHost: string;
  imapPort: string;
  smtpHost: string;
  smtpPort: string;
  smtpSecurity: 'ssl' | 'starttls';
};

const EMPTY_FORM: AddForm = {
  provider: 'qq',
  email: '',
  password: '',
  displayName: '',
  imapHost: '',
  imapPort: '993',
  smtpHost: '',
  smtpPort: '465',
  smtpSecurity: 'ssl',
};

type Probe = MailProbeResult & { testing?: boolean };

export function EmailTab(): React.ReactElement {
  const { t } = useI18n();
  const [providers, setProviders] = useState<MailProvider[]>([]);
  const [accounts, setAccounts] = useState<MailAccount[]>([]);
  const [form, setForm] = useState<AddForm>(EMPTY_FORM);
  const [showAddForm, setShowAddForm] = useState(false);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [probes, setProbes] = useState<Record<string, Probe>>({});
  const [passwordEdit, setPasswordEdit] = useState<{ id: string; value: string } | null>(null);

  useEffect(() => {
    fetchMailProviders()
      .then(setProviders)
      .catch(() => setProviders([]));
    fetchMailAccounts()
      .then(setAccounts)
      .catch(() => setAccounts([]));
  }, []);

  const provider = useMemo(
    () => providers.find((p) => p.id === form.provider),
    [providers, form.provider]
  );
  const isCustom = form.provider === 'custom';
  const providerLabel = (id: string) => providers.find((p) => p.id === id)?.label ?? id;

  const update = (changes: Partial<AddForm>) => setForm((prev) => ({ ...prev, ...changes }));

  const guessProvider = () => {
    const domain = form.email.split('@')[1]?.toLowerCase();
    if (!domain) return;
    const match = providers.find((p) => p.domains.includes(domain));
    if (match) update({ provider: match.id });
  };

  const handleAdd = async () => {
    setAdding(true);
    setAddError(null);
    try {
      const account = await addMailAccount({
        email: form.email.trim(),
        password: form.password,
        provider: form.provider,
        display_name: form.displayName.trim() || undefined,
        ...(isCustom
          ? {
              imap_host: form.imapHost.trim(),
              imap_port: Number(form.imapPort) || undefined,
              smtp_host: form.smtpHost.trim(),
              smtp_port: Number(form.smtpPort) || undefined,
              smtp_security: form.smtpSecurity,
            }
          : {}),
      });
      setAccounts((prev) => [...prev, account]);
      setProbes((prev) => ({ ...prev, [account.id]: { ok: true } }));
      setForm({ ...EMPTY_FORM, provider: form.provider });
      setShowAddForm(false);
    } catch (e) {
      setAddError(e instanceof Error ? e.message : String(e));
    } finally {
      setAdding(false);
    }
  };

  const replaceAccount = (account: MailAccount) =>
    setAccounts((prev) => prev.map((a) => (a.id === account.id ? account : a)));

  const handleToggleSend = async (account: MailAccount) => {
    setBusy(account.id);
    try {
      replaceAccount(await updateMailAccount(account.id, { allow_send: !account.allow_send }));
    } finally {
      setBusy(null);
    }
  };

  const handleTest = async (account: MailAccount) => {
    setProbes((prev) => ({ ...prev, [account.id]: { ok: false, testing: true } }));
    try {
      const result = await testMailAccount(account.id);
      setProbes((prev) => ({ ...prev, [account.id]: result }));
    } catch (e) {
      setProbes((prev) => ({ ...prev, [account.id]: { ok: false, error: String(e) } }));
    }
  };

  const handleSavePassword = async () => {
    if (!passwordEdit?.value) return;
    setBusy(passwordEdit.id);
    try {
      replaceAccount(await updateMailAccount(passwordEdit.id, { password: passwordEdit.value }));
      const id = passwordEdit.id;
      setPasswordEdit(null);
      const account = accounts.find((a) => a.id === id);
      if (account) await handleTest(account);
    } finally {
      setBusy(null);
    }
  };

  const handleRemove = async (account: MailAccount) => {
    setBusy(account.id);
    try {
      await removeMailAccount(account.id);
      setAccounts((prev) => prev.filter((a) => a.id !== account.id));
    } finally {
      setBusy(null);
    }
  };

  const canAdd =
    !adding &&
    form.email.includes('@') &&
    !!form.password &&
    !provider?.oauth_only &&
    (!isCustom || (!!form.imapHost.trim() && !!form.smtpHost.trim()));

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.email.title')} subtitle={t('settings.email.subtitle')} />

      <CollapsibleSettingsCard
        open={showAddForm}
        onOpenChange={setShowAddForm}
        openLabel={t('common.add')}
        closeLabel={t('common.close')}
        iconTone="blue"
        icon={
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 6v6m0 0v6m0-6h6m-6 0H6"
            />
          </svg>
        }
        title={t('settings.email.addTitle')}
        description={t('settings.email.addDesc')}
      >
        <div className="space-y-3">
          <BrutalSelect
            value={form.provider}
            onChange={(value) => update({ provider: value })}
            options={providers.map((p) => ({
              value: p.id,
              label: p.label,
              hint: p.oauth_only ? t('settings.email.oauthOnly') : undefined,
            }))}
          />
          {provider?.oauth_only ? (
            <p className="text-xs font-bold text-brutal-red">{t('settings.email.oauthOnly')}</p>
          ) : (
            <>
              <input
                value={form.email}
                onChange={(e) => update({ email: e.target.value })}
                onBlur={guessProvider}
                placeholder={t('settings.email.emailPlaceholder')}
                autoComplete="off"
                className={INPUT_CLASS}
              />
              <input
                type="password"
                value={form.password}
                onChange={(e) => update({ password: e.target.value })}
                placeholder={t('settings.email.passwordPlaceholder')}
                autoComplete="new-password"
                className={INPUT_CLASS}
              />
              <p className="text-xs text-neutral-600 dark:text-neutral-400">
                {t('settings.email.passwordHelp')}{' '}
                {provider?.password_help_url && (
                  <a
                    href={provider.password_help_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-bold text-brutal-blue underline dark:text-blue-400"
                  >
                    {t('settings.email.passwordHelpLink', { provider: provider.label })}
                  </a>
                )}
              </p>
              <input
                value={form.displayName}
                onChange={(e) => update({ displayName: e.target.value })}
                placeholder={t('settings.email.displayNamePlaceholder')}
                className={INPUT_CLASS}
              />
              {isCustom && (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_6rem]">
                  <input
                    value={form.imapHost}
                    onChange={(e) => update({ imapHost: e.target.value })}
                    placeholder={t('settings.email.imapHost')}
                    className={INPUT_CLASS}
                  />
                  <input
                    value={form.imapPort}
                    onChange={(e) => update({ imapPort: e.target.value })}
                    placeholder="993"
                    className={INPUT_CLASS}
                  />
                  <input
                    value={form.smtpHost}
                    onChange={(e) => update({ smtpHost: e.target.value })}
                    placeholder={t('settings.email.smtpHost')}
                    className={INPUT_CLASS}
                  />
                  <input
                    value={form.smtpPort}
                    onChange={(e) => update({ smtpPort: e.target.value })}
                    placeholder="465"
                    className={INPUT_CLASS}
                  />
                  <BrutalSelect
                    value={form.smtpSecurity}
                    onChange={(value) => update({ smtpSecurity: value as 'ssl' | 'starttls' })}
                    options={[
                      { value: 'ssl', label: 'SSL/TLS' },
                      { value: 'starttls', label: 'STARTTLS' },
                    ]}
                  />
                </div>
              )}
              {addError && (
                <p className="text-xs font-bold text-brutal-red break-words">{addError}</p>
              )}
              <BrutalButton
                variant="success"
                onClick={handleAdd}
                disabled={!canAdd}
                className="px-4 py-2 uppercase"
              >
                {adding ? t('settings.email.signingIn') : t('settings.email.addAccount')}
              </BrutalButton>
            </>
          )}
        </div>
      </CollapsibleSettingsCard>

      <SettingsCard>
        <SectionCardHeader
          iconTone="black"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
          }
          title={t('settings.email.accountsTitle')}
          description={t('settings.email.accountsDesc')}
        />

        {accounts.length === 0 ? (
          <div className="text-center py-8 text-neutral-500 dark:text-neutral-400 font-bold uppercase">
            {t('settings.email.noAccounts')}
          </div>
        ) : (
          <div className="space-y-4">
            {accounts.map((account) => {
              const probe = probes[account.id];
              return (
                <SettingsListItem key={account.id}>
                  <div className="flex flex-col md:flex-row items-start md:items-center gap-4 p-4 md:p-5">
                    <div className="flex-1 min-w-0 w-full">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-black tracking-wide text-brutal-black dark:text-white truncate">
                          {account.email}
                        </span>
                        <Badge>{providerLabel(account.provider)}</Badge>
                        {!account.has_password && (
                          <Badge tone="red">{t('settings.email.passwordMissing')}</Badge>
                        )}
                      </div>
                      <div className="mt-1 text-[10px] font-mono text-neutral-500 dark:text-neutral-400 truncate">
                        {account.id} · {account.imap_host}
                      </div>
                      <label className="mt-3 flex items-center gap-3">
                        <BrutalOnOff
                          size="sm"
                          checked={account.allow_send}
                          onChange={() => handleToggleSend(account)}
                          disabled={busy === account.id}
                          aria-label={t('settings.email.allowSend')}
                        />
                        <span className="text-xs">
                          <span className="font-bold">{t('settings.email.allowSend')}</span>
                          <span className="block text-neutral-500 dark:text-neutral-400">
                            {t('settings.email.allowSendDesc')}
                          </span>
                        </span>
                      </label>
                      {probe && (
                        <div className="mt-2 text-[10px] font-bold uppercase break-words">
                          {probe.testing ? (
                            <span className="text-neutral-500">{t('settings.email.testing')}</span>
                          ) : probe.ok ? (
                            <Badge tone="green">{t('settings.email.connected')}</Badge>
                          ) : (
                            <span className="normal-case text-brutal-red">{probe.error}</span>
                          )}
                        </div>
                      )}
                      {passwordEdit?.id === account.id && (
                        <div className="mt-3 flex gap-2">
                          <input
                            type="password"
                            value={passwordEdit.value}
                            onChange={(e) =>
                              setPasswordEdit({ id: account.id, value: e.target.value })
                            }
                            placeholder={t('settings.email.passwordPlaceholder')}
                            autoComplete="new-password"
                            className={INPUT_CLASS}
                          />
                          <BrutalIconButton
                            variant="primary"
                            onClick={handleSavePassword}
                            disabled={!passwordEdit.value || busy === account.id}
                            label={t('common.save')}
                          >
                            <CheckIcon className="h-4 w-4 stroke-[2.5]" />
                          </BrutalIconButton>
                          <BrutalIconButton
                            onClick={() => setPasswordEdit(null)}
                            label={t('common.cancel')}
                          >
                            <XMarkIcon className="h-4 w-4 stroke-[2.5]" />
                          </BrutalIconButton>
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 shrink-0 w-full md:w-auto justify-end md:self-start">
                      <BrutalIconButton
                        onClick={() => handleTest(account)}
                        disabled={probe?.testing}
                        label={t('settings.email.test')}
                      >
                        <BeakerIcon className="h-4 w-4 stroke-2" />
                      </BrutalIconButton>
                      <BrutalIconButton
                        isActive={passwordEdit?.id === account.id}
                        onClick={() =>
                          setPasswordEdit(
                            passwordEdit?.id === account.id ? null : { id: account.id, value: '' }
                          )
                        }
                        label={t('settings.email.changePassword')}
                      >
                        <KeyIcon className="h-4 w-4 stroke-2" />
                      </BrutalIconButton>
                      <BrutalIconButton
                        variant="danger"
                        onClick={() => handleRemove(account)}
                        disabled={busy === account.id}
                        label={t('common.remove')}
                      >
                        <TrashIcon className="h-4 w-4 stroke-2" />
                      </BrutalIconButton>
                    </div>
                  </div>
                </SettingsListItem>
              );
            })}
          </div>
        )}
      </SettingsCard>
    </SettingsPage>
  );
}
