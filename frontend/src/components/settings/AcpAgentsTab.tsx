import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, fetchAcpSessions, probeAcpAgent } from '../../lib/api';
import type { AcpProbeResult } from '../../lib/api';
import type { AcpAgentDescriptor } from '../../types/api';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalButton, BrutalLink } from '../BrutalButton';
import {
  SectionCardHeader,
  SettingsCard,
  SettingsHelp,
  SettingsListItem,
  Badge,
  SettingsPage,
} from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';
import { AcpAgentIcon } from '../AcpAgentIcon';
import { AcpConnections } from './AcpConnections';
import { fetchAcpLogins, startAcpLogin, cancelAcpLogin, isLoginActive } from '../../lib/acpLogin';
import type { AcpLoginState } from '../../lib/acpLogin';

// ---------------------------------------------------------------------------
// Auth status badge
// ---------------------------------------------------------------------------

function AuthBadge({ status, t }: { status?: string; t: (k: string) => string }) {
  if (!status || status === 'unknown') {
    return <Badge tone="neutral">{t('settings.acp.authUnknown')}</Badge>;
  }
  if (status === 'ok') {
    return <Badge tone="green">{t('settings.acp.authOk')}</Badge>;
  }
  return <Badge tone="red">{t('settings.acp.authMissing')}</Badge>;
}

// ---------------------------------------------------------------------------
// Tab component — status-only view (no session creation)
// ---------------------------------------------------------------------------

type ProbeState =
  | { status: 'probing' }
  | { status: 'ok'; data: AcpProbeResult }
  | { status: 'error'; message: string };

export function AcpAgentsTab(): React.ReactElement {
  const { t } = useI18n();
  const [agents, setAgents] = useState<AcpAgentDescriptor[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [sessionCounts, setSessionCounts] = useState<
    Record<string, { saved: number; active: number }>
  >({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [authenticating, setAuthenticating] = useState<Record<string, boolean>>({});
  const [logins, setLogins] = useState<Record<string, AcpLoginState>>({});
  const [methods, setMethods] = useState<Record<string, string>>({});
  const [loginError, setLoginError] = useState(false);
  const completed = useRef<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async (): Promise<void> => {
      try {
        const next = await fetchAcpLogins();
        if (cancelled) return;
        setLogins(next);
        setLoginError(false);
        for (const [id, state] of Object.entries(next)) {
          if (state.result && !isLoginActive(state) && completed.current[id] !== state.attempt) {
            completed.current[id] = state.attempt;
            setProbes((previous) => ({ ...previous, [id]: { status: 'ok', data: state.result! } }));
          }
        }
      } catch {
        if (!cancelled) setLoginError(true);
      } finally {
        if (!cancelled) timer = setTimeout(() => void poll(), 1500);
      }
    };
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const handleProbe = useCallback(async (agent: AcpAgentDescriptor) => {
    setProbes((prev) => ({ ...prev, [agent.id]: { status: 'probing' } }));
    try {
      if (agent.probe) {
        const ok = await agent.probe();
        setProbes((prev) => ({
          ...prev,
          [agent.id]: ok
            ? { status: 'ok', data: { status: 'ready', authMethods: [] } }
            : { status: 'error', message: 'probe returned false' },
        }));
        return;
      }
      const data = await probeAcpAgent(agent.id);
      setProbes((prev) => ({ ...prev, [agent.id]: { status: 'ok', data } }));
    } catch (e) {
      setProbes((prev) => ({
        ...prev,
        [agent.id]: { status: 'error', message: String(e) },
      }));
    }
  }, []);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setRefreshing(true);
    try {
      const loaded = await fetchAcpAgents();
      setAgents(loaded);
      const currentLogins = await fetchAcpLogins();
      const pending = loaded.filter(
        (agent) => agent.status === 'ready' && !isLoginActive(currentLogins[agent.id])
      );
      setProbes((previous) => ({
        ...previous,
        ...Object.fromEntries(pending.map((agent) => [agent.id, { status: 'probing' as const }])),
      }));
      setLoading(false);
      const checkConnections = async (): Promise<void> => {
        let agent: AcpAgentDescriptor | undefined;
        while ((agent = pending.shift())) await handleProbe(agent);
      };
      const checks = Promise.all([checkConnections(), checkConnections()]);
      // Load per-agent session counts in the background.
      const counts: Record<string, { saved: number; active: number }> = {};
      await Promise.allSettled(
        loaded
          .filter((a) => a.status === 'ready')
          .map(async (a) => {
            try {
              const { saved, active } = await fetchAcpSessions(a.id);
              counts[a.id] = { saved: saved.length, active };
            } catch {
              /* skip */
            }
          })
      );
      setSessionCounts(counts);
      await checks;
    } catch (e) {
      console.error('Failed to fetch agents', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [handleProbe]);

  const handleAuthenticate = async (id: string, methodId?: string): Promise<void> => {
    setAuthenticating((prev) => ({ ...prev, [id]: true }));
    try {
      const data = await startAcpLogin(id, methodId);
      setLogins((prev) => ({ ...prev, [id]: data }));
      setProbes((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    } catch {
      setLoginError(true);
    } finally {
      setAuthenticating((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleCancelLogin = async (id: string): Promise<void> => {
    try {
      const data = await cancelAcpLogin(id);
      setLogins((prev) => ({ ...prev, [id]: data }));
    } catch {
      setLoginError(true);
    }
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId((prev) => (prev === id ? null : prev)), 1500);
  };

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

  const isReady = (agent: AcpAgentDescriptor) => agent.status === 'ready';

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.acp.title')} subtitle={t('settings.acp.subtitle')} />
      <AcpConnections />

      <SettingsCard className="space-y-3">
        <SectionCardHeader
          title={t('settings.acp.registeredTitle')}
          description={t('settings.acp.registeredDesc')}
          actions={
            <BrutalButton
              size="sm"
              disabled={loading || refreshing}
              onClick={() => void loadAgents()}
            >
              {t('common.refresh')}
            </BrutalButton>
          }
        />
        {loginError && (
          <p
            role="alert"
            className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
          >
            {t('settings.acp.loginRequestError')}
          </p>
        )}
        <SettingsHelp title={t('settings.acp.agentHelp')}>
          <p>{t('settings.acp.probeHelp')}</p>
          <p>
            {t('settings.acp.customHelp')} <code>~/.suzent/acp_agents.json</code>
          </p>
        </SettingsHelp>

        {loading ? (
          <div className="p-8 text-center font-bold uppercase text-neutral-500">
            {t('common.loading')}
          </div>
        ) : agents.length === 0 ? (
          <div className="text-center py-8 text-neutral-600 dark:text-neutral-300 font-bold uppercase">
            {t('settings.acp.noAgents')}
          </div>
        ) : (
          <div className="space-y-4">
            {agents.map((agent) => {
              const probe = probes[agent.id];
              const login = logins[agent.id];
              const busy = authenticating[agent.id] || isLoginActive(login);
              const authMethods =
                probe?.status === 'ok'
                  ? probe.data.authMethods.filter((method) =>
                      ['agent', 'terminal'].includes(method.type)
                    )
                  : [];
              const ready = isReady(agent);
              const signedIn =
                ready &&
                !busy &&
                (probe
                  ? probe.status === 'ok' && probe.data.status === 'ready'
                  : agent.auth_status === 'ok');
              const counts = sessionCounts[agent.id];
              const activeSessions = counts?.active ?? 0;
              const savedSessions = counts?.saved ?? 0;
              const adapter = agent.adapter_package;
              const customInstall = agent.install_command?.join(' ');
              // The adapter is Suzent's own requirement; a custom agent's
              // install_command is whatever its author wrote. Never both.
              const setupCommand = adapter ? `npm install -g ${adapter}` : customInstall;
              const needsSetup = !ready && (agent.docs_url || setupCommand);
              return (
                <SettingsListItem key={agent.id}>
                  {/* Identity and status — the two things scanned first */}
                  <div className="flex items-start gap-3 p-4 border-b-2 border-brutal-black">
                    <div
                      className={`w-10 h-10 border-2 border-brutal-black flex items-center justify-center shrink-0 ${
                        ready
                          ? 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black'
                          : 'text-neutral-400 dark:text-neutral-500'
                      }`}
                    >
                      <AcpAgentIcon id={agent.id} />
                    </div>
                    <div className="min-w-0 flex-1">
                      {/* Badges wrap under the name rather than crushing it:
                          the settings pane gets narrow. */}
                      <div className="flex items-start justify-between gap-2 flex-wrap">
                        <div className="font-black uppercase tracking-wide text-base text-brutal-black dark:text-white break-words">
                          {agent.name}
                        </div>
                        <div className="flex items-center gap-2">
                          {ready && !signedIn && agent.auth_status && !probe && (
                            <AuthBadge status={agent.auth_status} t={t} />
                          )}
                          <Badge tone={ready ? 'green' : 'amber'}>
                            {signedIn
                              ? t('settings.acp.authOk')
                              : ready
                                ? t('settings.acp.ready')
                                : t('settings.acp.notInstalled')}
                          </Badge>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Where it lives, who defined it, what it's running */}
                  <details className="px-4 py-2 border-b border-brutal-black/10 dark:border-white/10 text-xs">
                    <summary className="cursor-pointer text-neutral-600 dark:text-neutral-300">
                      {t('settings.acp.agentDetails')}
                    </summary>
                    {agent.description && (
                      <p className="mt-2 text-neutral-600 dark:text-neutral-300">
                        {agent.description}
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span
                        className="font-mono text-[10px] text-neutral-600 dark:text-neutral-300 truncate min-w-0 flex-1 basis-48"
                        title={agent.executable_path || agent.id}
                      >
                        {agent.executable_path || agent.id}
                      </span>
                      <span className="text-[10px] font-bold uppercase tracking-wide text-neutral-400 dark:text-neutral-500 shrink-0">
                        {agent.builtin ? t('settings.acp.builtIn') : t('settings.acp.custom')}
                      </span>
                      {ready && (
                        // "Active" means a live agent process; a chat bound to
                        // this agent with nothing running is only "saved".
                        <Badge tone={activeSessions > 0 ? 'blue' : 'neutral'} className="shrink-0">
                          {activeSessions > 0
                            ? t('settings.acp.activeSessions').replace(
                                '{count}',
                                String(activeSessions)
                              )
                            : savedSessions > 0
                              ? t('settings.acp.savedSessions').replace(
                                  '{count}',
                                  String(savedSessions)
                                )
                              : t('settings.acp.noSessions')}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {ready && agent.login_command && (
                        <BrutalButton
                          size="sm"
                          onClick={() =>
                            handleCopy(`login-${agent.id}`, agent.login_command!.join(' '))
                          }
                        >
                          {copiedId === `login-${agent.id}`
                            ? t('settings.acp.copied')
                            : t('settings.acp.copyLogin')}
                        </BrutalButton>
                      )}
                      {agent.docs_url && (
                        <ExternalAction href={agent.docs_url} label={t('settings.acp.docs')} />
                      )}
                    </div>
                  </details>

                  {/* The fix, in place of the status it explains */}
                  {needsSetup && (
                    <details className="border-b border-brutal-black/10 dark:border-white/10">
                      <summary className="cursor-pointer px-4 py-3 text-xs font-bold text-neutral-600 dark:text-neutral-300">
                        {t('settings.acp.setupTitle')}
                      </summary>
                      <div className="p-4 space-y-3">
                        {agent.docs_url && (
                          <div className="space-y-2">
                            <p className="text-[11px] text-neutral-600 dark:text-neutral-300">
                              {t('settings.acp.installHint')}
                            </p>
                            <ExternalAction
                              href={agent.docs_url}
                              label={t('settings.acp.installGuide')}
                              primary
                            />
                          </div>
                        )}
                        {setupCommand && (
                          <div className="space-y-1.5">
                            <div className="text-[10px] font-black uppercase tracking-wide text-neutral-600 dark:text-neutral-300">
                              {adapter
                                ? t('settings.acp.adapterTitle')
                                : t('settings.acp.copyInstall')}
                            </div>
                            {adapter && (
                              <p className="text-[11px] text-neutral-600 dark:text-neutral-300">
                                {t('settings.acp.adapterHint')}
                              </p>
                            )}
                            <CommandChip
                              command={setupCommand}
                              copied={copiedId === `install-${agent.id}`}
                              onCopy={() => handleCopy(`install-${agent.id}`, setupCommand)}
                              t={t}
                            />
                          </div>
                        )}
                      </div>
                    </details>
                  )}

                  {/* Actions — the probe result reads on the line it came from */}
                  {ready && (
                    <div className="flex flex-wrap items-center gap-2 p-4">
                      <BrutalButton
                        size="sm"
                        onClick={() => handleProbe(agent)}
                        disabled={probe?.status === 'probing' || busy}
                      >
                        {probe?.status === 'probing'
                          ? t('settings.acp.probing')
                          : t('settings.acp.probe')}
                      </BrutalButton>
                      {!signedIn && authMethods.length > 1 && (
                        <BrutalSelect
                          disabled={busy}
                          value={methods[agent.id] || ''}
                          onChange={(value) =>
                            setMethods((prev) => ({ ...prev, [agent.id]: value }))
                          }
                          options={[
                            { value: '', label: t('settings.acp.loginAutomatic') },
                            ...authMethods.map((method) => ({
                              value: method.id,
                              label: method.name,
                            })),
                          ]}
                          className="max-w-full"
                          buttonClassName="text-xs"
                        />
                      )}
                      <BrutalButton
                        size="sm"
                        variant={signedIn ? 'default' : 'primary'}
                        disabled={busy || probe?.status === 'probing'}
                        onClick={() =>
                          void handleAuthenticate(agent.id, methods[agent.id] || undefined)
                        }
                      >
                        {busy
                          ? t('settings.acp.loggingIn')
                          : t(signedIn ? 'settings.acp.signInAgain' : 'settings.acp.login')}
                      </BrutalButton>
                      {isLoginActive(login) && (
                        <BrutalButton size="sm" onClick={() => void handleCancelLogin(agent.id)}>
                          {t('common.cancel')}
                        </BrutalButton>
                      )}
                      {probe && !signedIn && (
                        <div className="ml-auto shrink-0">
                          {probe.status === 'probing' ? (
                            <span className="text-[10px] font-bold uppercase text-neutral-500">
                              {t('settings.acp.probing')}
                            </span>
                          ) : probe.status === 'ok' ? (
                            <Badge tone={probe.data.status === 'auth_required' ? 'amber' : 'green'}>
                              {t(
                                probe.data.status === 'auth_required'
                                  ? 'settings.acp.authMissing'
                                  : 'settings.acp.probeOk'
                              )}
                            </Badge>
                          ) : (
                            <Badge tone="red" title={probe.message}>
                              {t('settings.acp.probeFailed')}
                            </Badge>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  {login && !signedIn && login.status !== 'idle' && login.status !== 'ready' && (
                    <p
                      role={login.status === 'failed' ? 'alert' : 'status'}
                      className={`mx-4 mb-4 rounded border p-3 text-sm ${login.status === 'failed' ? 'border-red-300 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200' : 'border-neutral-300 bg-white text-neutral-800 dark:border-zinc-600 dark:bg-zinc-800 dark:text-neutral-100'}`}
                    >
                      {t(`settings.acp.loginStates.${login.status}`)}
                      {login.error && <> {t(`settings.acp.loginErrors.${login.error}`)}</>}
                    </p>
                  )}
                  {probe?.status === 'error' && (
                    <p
                      role="alert"
                      className="px-4 pb-4 text-xs text-red-600 dark:text-red-400 break-words"
                    >
                      {probe.message}
                    </p>
                  )}
                </SettingsListItem>
              );
            })}
          </div>
        )}
      </SettingsCard>
    </SettingsPage>
  );
}

// ---------------------------------------------------------------------------
// Setup helpers
// ---------------------------------------------------------------------------

function ExternalAction({
  href,
  label,
  primary = false,
}: {
  href: string;
  label: string;
  primary?: boolean;
}): React.ReactElement {
  const content = (
    <>
      {label}
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2.5}
          d="M14 5h5v5M19 5l-8 8M17 14v4a1 1 0 01-1 1H6a1 1 0 01-1-1V8a1 1 0 011-1h4"
        />
      </svg>
    </>
  );

  return (
    <BrutalLink
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      variant={primary ? 'primary' : 'default'}
      size="sm"
    >
      {content}
    </BrutalLink>
  );
}

/** A terminal-looking command with the copy button attached to it. */
function CommandChip({
  command,
  copied,
  onCopy,
  t,
}: {
  command: string;
  copied: boolean;
  onCopy: () => void;
  t: (k: string) => string;
}): React.ReactElement {
  return (
    <div className="flex items-stretch border-2 border-brutal-black bg-white dark:bg-zinc-800">
      <code className="flex-1 min-w-0 px-2.5 py-1.5 font-mono text-[11px] text-brutal-black dark:text-white overflow-x-auto whitespace-nowrap">
        <span className="text-neutral-400 select-none">$ </span>
        {command}
      </code>
      <button
        type="button"
        onClick={onCopy}
        className={`shrink-0 border-l-2 border-brutal-black px-2.5 text-[10px] font-black uppercase transition-colors ${
          copied
            ? 'bg-brutal-green text-brutal-black'
            : 'text-brutal-black dark:text-white hover:bg-brutal-yellow hover:text-brutal-black'
        }`}
      >
        {copied ? t('settings.acp.copied') : t('settings.acp.copyCommand')}
      </button>
    </div>
  );
}
