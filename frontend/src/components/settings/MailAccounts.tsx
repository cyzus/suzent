import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  addMailAccount,
  fetchMailProviders,
  fetchMailState,
  removeMailAccount,
  startMailOAuthSignIn,
  testMailAccount,
  updateMailAccount,
  type MailAccount,
  type MailOAuthSignIn,
  type MailProvider,
} from '../../lib/api';
import { BrutalOnOff } from '../BrutalOnOff';
import { BrutalSelect } from '../BrutalSelect';
import { Badge, SettingsListAction } from './SettingsCard';

const INPUT_CLASS =
  'w-full min-w-0 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500';

type Form = {
  provider: string;
  email: string;
  password: string;
  imapHost: string;
  smtpHost: string;
  usePasswordForOAuth: boolean;
};

const EMPTY_FORM: Form = {
  provider: 'qq',
  email: '',
  password: '',
  imapHost: '',
  smtpHost: '',
  usePasswordForOAuth: false,
};

type Probe = { ok: boolean; error?: string; testing?: boolean };

/** "host" or "host:port"; port 587 means STARTTLS, anything else implicit TLS. */
function server(value: string): { host: string; port?: number } {
  const [host, port] = value.trim().split(':');
  return { host, port: Number(port) || undefined };
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Mailboxes the Email plugin signs in to, shown inside its plugin card. */
export function MailAccounts({
  openLink,
}: {
  openLink: (url: string) => void;
}): React.ReactElement {
  const { t } = useI18n();
  const [providers, setProviders] = useState<MailProvider[]>([]);
  const [accounts, setAccounts] = useState<MailAccount[]>([]);
  const [oauthSignIn, setOauthSignIn] = useState<MailOAuthSignIn | null>(null);
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [probes, setProbes] = useState<Record<string, Probe>>({});
  const [passwordFor, setPasswordFor] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');

  const refreshAccounts = useCallback(async (): Promise<void> => {
    try {
      const state = await fetchMailState();
      setAccounts(state.accounts);
      setOauthSignIn(state.oauthSignIn ?? null);
    } catch {
      setAccounts([]);
    }
  }, []);

  useEffect(() => {
    fetchMailProviders()
      .then(setProviders)
      .catch(() => setProviders([]));
    void refreshAccounts();
  }, [refreshAccounts]);

  const waitingForOAuth = oauthSignIn?.state === 'waiting';

  useEffect(() => {
    if (!waitingForOAuth) return;
    const timer = window.setInterval(() => void refreshAccounts(), 1500);
    return () => window.clearInterval(timer);
  }, [waitingForOAuth, refreshAccounts]);

  useEffect(() => {
    if (oauthSignIn?.state === 'signed_in' && oauthSignIn.accountId) {
      setProbes((prev) => ({ ...prev, [oauthSignIn.accountId!]: { ok: true } }));
      setForm((prev) => ({ ...EMPTY_FORM, provider: prev.provider }));
    }
  }, [oauthSignIn?.state, oauthSignIn?.accountId]);

  const provider = useMemo(
    () => providers.find((p) => p.id === form.provider),
    [providers, form.provider]
  );
  const isCustom = form.provider === 'custom';
  const supportsOAuth = !!provider?.oauth_provider;
  const useOAuth = supportsOAuth && (provider?.oauth_only || !form.usePasswordForOAuth);
  const update = (changes: Partial<Form>): void => setForm((prev) => ({ ...prev, ...changes }));
  const replace = (account: MailAccount): void =>
    setAccounts((prev) => prev.map((a) => (a.id === account.id ? account : a)));

  const guessProvider = (): void => {
    const domain = form.email.split('@')[1]?.toLowerCase();
    const match = domain && providers.find((p) => p.domains.includes(domain));
    if (match) update({ provider: match.id, usePasswordForOAuth: false });
  };

  const customServers = () => {
    const imap = server(form.imapHost);
    const smtp = server(form.smtpHost);
    return {
      imap_host: imap.host,
      imap_port: imap.port,
      smtp_host: smtp.host,
      smtp_port: smtp.port,
      smtp_security: smtp.port === 587 ? ('starttls' as const) : ('ssl' as const),
    };
  };

  const add = async (): Promise<void> => {
    setAdding(true);
    setError(null);
    try {
      if (useOAuth) {
        const session = await startMailOAuthSignIn({
          email: form.email.trim(),
          provider: form.provider,
          oauth_provider: provider?.oauth_provider ?? undefined,
          ...(isCustom ? customServers() : {}),
        });
        setOauthSignIn(session);
        if (session.authorizeUrl) openLink(session.authorizeUrl);
        return;
      }
      const account = await addMailAccount({
        email: form.email.trim(),
        password: form.password,
        provider: form.provider,
        ...(isCustom ? customServers() : {}),
      });
      setAccounts((prev) => [...prev, account]);
      setProbes((prev) => ({ ...prev, [account.id]: { ok: true } }));
      setForm({ ...EMPTY_FORM, provider: form.provider });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setAdding(false);
    }
  };

  const reSignInOAuth = async (account: MailAccount): Promise<void> => {
    setBusy(account.id);
    setError(null);
    try {
      const session = await startMailOAuthSignIn({
        email: account.email,
        provider: account.provider,
        oauth_provider: account.oauth_provider ?? undefined,
      });
      setOauthSignIn(session);
      if (session.authorizeUrl) openLink(session.authorizeUrl);
    } catch (err) {
      setProbes((prev) => ({ ...prev, [account.id]: { ok: false, error: errorText(err) } }));
    } finally {
      setBusy(null);
    }
  };

  const test = async (id: string): Promise<void> => {
    setProbes((prev) => ({ ...prev, [id]: { ok: false, testing: true } }));
    try {
      const result = await testMailAccount(id);
      setProbes((prev) => ({ ...prev, [id]: result }));
    } catch (err) {
      setProbes((prev) => ({ ...prev, [id]: { ok: false, error: errorText(err) } }));
    }
  };

  const run = async (id: string, action: () => Promise<void>): Promise<void> => {
    setBusy(id);
    try {
      await action();
    } catch (err) {
      setProbes((prev) => ({ ...prev, [id]: { ok: false, error: errorText(err) } }));
    } finally {
      setBusy(null);
    }
  };

  const canAdd =
    !adding &&
    !waitingForOAuth &&
    form.email.includes('@') &&
    (useOAuth || !!form.password) &&
    (!isCustom || (!!form.imapHost.trim() && !!form.smtpHost.trim()));

  const oauthError = oauthSignIn?.state === 'failed' ? oauthSignIn.error : null;

  return (
    <div className="space-y-3 border-t-2 border-dashed border-neutral-300 pt-3 dark:border-white/15">
      {accounts.length > 0 && (
        <div className="space-y-2.5">
          {accounts.map((account) => {
            const probe = probes[account.id];
            const isOAuthAccount = account.auth_type === 'xoauth2';
            const providerLabel =
              providers.find((p) => p.id === account.provider)?.label ?? account.provider;
            return (
              <div
                key={account.id}
                className="space-y-2.5 border-2 border-brutal-black/15 bg-neutral-50/70 p-3 dark:border-white/10 dark:bg-zinc-950/40"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="truncate font-mono text-sm font-bold">{account.email}</span>
                    <Badge tone="neutral">{providerLabel}</Badge>
                    {!account.has_password ? (
                      <Badge tone="red">{t('settings.email.passwordMissing')}</Badge>
                    ) : probe?.ok ? (
                      <Badge tone="green">{t('settings.plugins.connected')}</Badge>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <SettingsListAction
                      disabled={probe?.testing}
                      onClick={() => void test(account.id)}
                    >
                      {probe?.testing ? t('settings.plugins.working') : t('settings.email.test')}
                    </SettingsListAction>
                    {isOAuthAccount ? (
                      <SettingsListAction
                        disabled={busy === account.id || waitingForOAuth}
                        onClick={() => void reSignInOAuth(account)}
                      >
                        {t('settings.email.reSignIn')}
                      </SettingsListAction>
                    ) : (
                      <SettingsListAction
                        active={passwordFor === account.id}
                        onClick={() => {
                          setNewPassword('');
                          setPasswordFor(passwordFor === account.id ? null : account.id);
                        }}
                      >
                        {t('settings.email.changePassword')}
                      </SettingsListAction>
                    )}
                    <SettingsListAction
                      tone="red"
                      disabled={busy === account.id}
                      onClick={() =>
                        void run(account.id, async () => {
                          await removeMailAccount(account.id);
                          setAccounts((prev) => prev.filter((a) => a.id !== account.id));
                        })
                      }
                    >
                      {t('settings.plugins.remove')}
                    </SettingsListAction>
                  </div>
                </div>
                <div className="flex flex-col gap-2 pt-0.5 sm:flex-row sm:items-start sm:gap-6">
                  <label className="flex shrink-0 items-center gap-2 text-xs font-bold">
                    <BrutalOnOff
                      size="sm"
                      checked={account.allow_send}
                      disabled={busy === account.id}
                      onChange={() =>
                        void run(account.id, async () =>
                          replace(
                            await updateMailAccount(account.id, {
                              allow_send: !account.allow_send,
                            })
                          )
                        )
                      }
                      aria-label={t('settings.email.allowSend')}
                    />
                    {t('settings.email.allowSend')}
                  </label>
                  <label className="flex items-start gap-2 text-xs font-bold">
                    <div className="pt-0.5">
                      <BrutalOnOff
                        size="sm"
                        checked={account.watch_inbox}
                        disabled={busy === account.id}
                        onChange={() =>
                          void run(account.id, async () =>
                            replace(
                              await updateMailAccount(account.id, {
                                watch_inbox: !account.watch_inbox,
                              })
                            )
                          )
                        }
                        aria-label={t('settings.email.watchInbox')}
                      />
                    </div>
                    <span>
                      {t('settings.email.watchInbox')}
                      <span className="block text-[11px] font-normal text-neutral-500 dark:text-neutral-400">
                        {t('settings.email.watchInboxHint')}
                      </span>
                    </span>
                  </label>
                </div>
                {passwordFor === account.id && !isOAuthAccount && (
                  <form
                    className="flex flex-col gap-2 pt-1 sm:flex-row"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!newPassword) return;
                      void run(account.id, async () => {
                        replace(await updateMailAccount(account.id, { password: newPassword }));
                        setPasswordFor(null);
                        await test(account.id);
                      });
                    }}
                  >
                    <input
                      type="password"
                      autoComplete="new-password"
                      aria-label={t('settings.email.passwordPlaceholder')}
                      placeholder={t('settings.email.passwordPlaceholder')}
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      className={INPUT_CLASS}
                    />
                    <SettingsListAction tone="blue" type="submit" disabled={!newPassword}>
                      {t('common.save')}
                    </SettingsListAction>
                  </form>
                )}
                {probe && !probe.ok && !probe.testing && probe.error && (
                  <p role="alert" className="break-words text-xs text-red-700 dark:text-red-300">
                    {probe.error}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      <form
        className={`space-y-2.5 ${accounts.length > 0 ? 'border-t-2 border-dashed border-neutral-300 pt-3 dark:border-white/15' : ''}`}
        onSubmit={(event) => {
          event.preventDefault();
          if (canAdd) void add();
        }}
      >
        <BrutalSelect
          value={form.provider}
          onChange={(value) => update({ provider: value, usePasswordForOAuth: false })}
          options={providers.map((p) => ({ value: p.id, label: p.label }))}
        />
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={form.email}
            onChange={(event) => update({ email: event.target.value })}
            onBlur={guessProvider}
            aria-label={t('settings.email.emailPlaceholder')}
            placeholder={t('settings.email.emailPlaceholder')}
            autoComplete="off"
            className={INPUT_CLASS}
          />
          {!useOAuth && (
            <input
              type="password"
              value={form.password}
              onChange={(event) => update({ password: event.target.value })}
              aria-label={t('settings.email.passwordPlaceholder')}
              placeholder={t('settings.email.passwordPlaceholder')}
              autoComplete="new-password"
              className={INPUT_CLASS}
            />
          )}
        </div>
        {isCustom && (
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={form.imapHost}
              onChange={(event) => update({ imapHost: event.target.value })}
              aria-label={t('settings.email.imapHost')}
              placeholder={t('settings.email.imapHost')}
              className={INPUT_CLASS}
            />
            <input
              value={form.smtpHost}
              onChange={(event) => update({ smtpHost: event.target.value })}
              aria-label={t('settings.email.smtpHost')}
              placeholder={t('settings.email.smtpHost')}
              className={INPUT_CLASS}
            />
          </div>
        )}
        {waitingForOAuth && (
          <p className="text-xs text-blue-700 dark:text-blue-300">
            {t('settings.email.waitingForBrowser')}
          </p>
        )}
        {(error || oauthError) && (
          <p role="alert" className="break-words text-xs text-red-700 dark:text-red-300">
            {error || oauthError}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          {supportsOAuth && !provider?.oauth_only ? (
            <button
              type="button"
              className="text-xs text-neutral-500 underline dark:text-neutral-400"
              onClick={() => update({ usePasswordForOAuth: !form.usePasswordForOAuth })}
            >
              {useOAuth
                ? t('settings.email.useAppPassword')
                : t('settings.email.useBrowserSignIn')}
            </button>
          ) : !useOAuth && provider?.password_help_url ? (
            <button
              type="button"
              className="text-xs text-neutral-500 underline dark:text-neutral-400"
              onClick={() => openLink(provider.password_help_url)}
            >
              {t('settings.email.getPassword')}
            </button>
          ) : (
            <span />
          )}
          <SettingsListAction tone="blue" type="submit" disabled={!canAdd}>
            {adding || waitingForOAuth
              ? t('settings.plugins.working')
              : useOAuth
                ? t('settings.email.signInBrowser')
                : t('settings.email.add')}
          </SettingsListAction>
        </div>
      </form>
    </div>
  );
}
