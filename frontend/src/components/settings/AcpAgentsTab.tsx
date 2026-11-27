import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, installAcpAgentAdapter, probeAcpAgent } from '../../lib/api';
import type { AcpProbeResult } from '../../lib/api';
import type { AcpAgentDescriptor } from '../../types/api';
import { BrutalSelect } from '../BrutalSelect';
import { RefreshButton } from '../RefreshButton';
import { BrutalButton, BrutalLink } from '../BrutalButton';
import {
  SectionCardHeader,
  SettingsCard,
  SettingsListItem,
  Badge,
  SettingsPage,
} from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';
import { AcpAgentIcon } from '../AcpAgentIcon';
import { AcpConnections } from './AcpConnections';
import { fetchAcpLogins, startAcpLogin, cancelAcpLogin, isLoginActive } from '../../lib/acpLogin';
import type { AcpLoginState } from '../../lib/acpLogin';
import { hoverText } from '../../lib/hoverText';
import { invalidateAcpAgents } from '../../hooks/useAcpAgents';

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
// Tab component — clean, single-layer cards without session noise
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
  const [searchQuery, setSearchQuery] = useState('');
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [installing, setInstalling] = useState<Record<string, boolean>>({});
  const [installErrors, setInstallErrors] = useState<Record<string, string>>({});
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
      setProbes(
        Object.fromEntries(pending.map((agent) => [agent.id, { status: 'probing' as const }]))
      );
      setLoading(false);
      const checkConnections = async (): Promise<void> => {
        let agent: AcpAgentDescriptor | undefined;
        while ((agent = pending.shift())) await handleProbe(agent);
      };
      await Promise.all([checkConnections(), checkConnections()]);
    } catch (e) {
      console.error('Failed to fetch agents', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [handleProbe]);

  const handleInstallAdapter = async (agent: AcpAgentDescriptor): Promise<void> => {
    setInstalling((prev) => ({ ...prev, [agent.id]: true }));
    setInstallErrors((prev) => {
      const next = { ...prev };
      delete next[agent.id];
      return next;
    });
    try {
      const res = await installAcpAgentAdapter(agent.id);
      invalidateAcpAgents();
      if (res.agent) {
        setAgents((prev) => prev.map((a) => (a.id === agent.id ? { ...a, ...res.agent } : a)));
        await handleProbe({ ...agent, ...res.agent });
      } else {
        await loadAgents();
      }
    } catch (e) {
      setInstallErrors((prev) => ({ ...prev, [agent.id]: String(e) }));
    } finally {
      setInstalling((prev) => ({ ...prev, [agent.id]: false }));
    }
  };

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

  const filteredAgents = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.id.toLowerCase().includes(q) ||
        (a.description && a.description.toLowerCase().includes(q))
    );
  }, [agents, searchQuery]);

  const installedAgents = useMemo(() => filteredAgents.filter((a) => isReady(a)), [filteredAgents]);
  const catalogAgents = useMemo(() => filteredAgents.filter((a) => !isReady(a)), [filteredAgents]);

  const renderAgentCard = (agent: AcpAgentDescriptor) => {
    const probe = probes[agent.id];
    const login = logins[agent.id];
    const isInstalling = !!installing[agent.id];
    const installErr = installErrors[agent.id];
    const busy = authenticating[agent.id] || isLoginActive(login) || isInstalling;
    const authMethods =
      probe?.status === 'ok'
        ? probe.data.authMethods.filter((method) => ['agent', 'terminal'].includes(method.type))
        : [];
    const ready = isReady(agent);
    const signedIn =
      ready &&
      !busy &&
      (probe ? probe.status === 'ok' && probe.data.status === 'ready' : agent.auth_status === 'ok');
    const adapter = agent.adapter_package;
    const customInstall = agent.install_command?.join(' ');

    return (
      <SettingsListItem key={agent.id}>
        <div className="p-4 space-y-3">
          {/* Header Row: Icon + Name + Description + Status Badges */}
          <div className="flex items-start gap-3">
            <div
              className={`w-10 h-10 border-2 border-brutal-black flex items-center justify-center shrink-0 ${
                ready
                  ? 'bg-brutal-black text-white dark:bg-emerald-400/10 dark:text-emerald-300 dark:border-emerald-400/25'
                  : 'text-neutral-400 dark:text-neutral-500'
              }`}
            >
              <AcpAgentIcon id={agent.id} />
            </div>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-start justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-black uppercase tracking-wide text-base text-brutal-black dark:text-white break-words">
                    {agent.name}
                  </span>
                  <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 border border-brutal-black/20 dark:border-white/20 text-neutral-500 dark:text-neutral-400">
                    {agent.builtin ? t('settings.acp.builtIn') : t('settings.acp.custom')}
                  </span>
                  {agent.usage_summary && <Badge tone="blue">{agent.usage_summary}</Badge>}
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {ready && !signedIn && agent.auth_status && !probe && (
                    <AuthBadge status={agent.auth_status} t={t} />
                  )}
                  {probe && !signedIn && (
                    <>
                      {probe.status === 'probing' ? (
                        <span className="text-[10px] font-bold uppercase text-neutral-500 dark:text-neutral-400">
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
                        <Badge tone="red" title={hoverText(probe.message)}>
                          {t('settings.acp.probeFailed')}
                        </Badge>
                      )}
                    </>
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

              {agent.description && (
                <p className="text-xs text-neutral-600 dark:text-neutral-300">
                  {agent.description}
                </p>
              )}

              {/* Compact meta strip: binary/adapter identifier */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400">
                <code
                  className="font-mono text-[10px] truncate max-w-md"
                  title={agent.executable_path || adapter || agent.id}
                >
                  {agent.executable_path || adapter || agent.id}
                </code>
                {!ready && adapter && (
                  <span className="text-[10px] text-neutral-500 dark:text-neutral-400">
                    · {t('settings.acp.adapterAutoHint')}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Custom install command chip only when a non-adapter custom command is specified */}
          {!ready && !adapter && customInstall && (
            <CommandChip
              command={customInstall}
              copied={copiedId === `install-${agent.id}`}
              onCopy={() => handleCopy(`install-${agent.id}`, customInstall)}
              t={t}
            />
          )}

          {/* Action Toolbar */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {ready ? (
              <>
                <BrutalButton
                  size="sm"
                  onClick={() => void handleProbe(agent)}
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
                    onChange={(value) => setMethods((prev) => ({ ...prev, [agent.id]: value }))}
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
                  onClick={() => void handleAuthenticate(agent.id, methods[agent.id] || undefined)}
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
                {agent.login_command && (
                  <BrutalButton
                    size="sm"
                    onClick={() => handleCopy(`login-${agent.id}`, agent.login_command!.join(' '))}
                  >
                    {copiedId === `login-${agent.id}`
                      ? t('settings.acp.copied')
                      : t('settings.acp.copyLogin')}
                  </BrutalButton>
                )}
              </>
            ) : (
              <>
                {adapter && (
                  <BrutalButton
                    size="sm"
                    variant="primary"
                    disabled={isInstalling}
                    onClick={() => void handleInstallAdapter(agent)}
                  >
                    {isInstalling
                      ? t('settings.acp.installingAdapter')
                      : t('settings.acp.installAdapter')}
                  </BrutalButton>
                )}
                {agent.docs_url && (
                  <ExternalAction
                    href={agent.docs_url}
                    label={t('settings.acp.installGuide')}
                    primary={!adapter}
                  />
                )}
              </>
            )}
            {ready && agent.docs_url && (
              <ExternalAction href={agent.docs_url} label={t('settings.acp.docs')} />
            )}
          </div>

          {/* Login / Probe / Install status & error feedback */}
          {login && !signedIn && login.status !== 'idle' && login.status !== 'ready' && (
            <p
              role={login.status === 'failed' ? 'alert' : 'status'}
              className={`rounded border p-2.5 text-xs ${
                login.status === 'failed'
                  ? 'border-red-300 bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200'
                  : 'border-neutral-300 bg-white text-neutral-800 dark:border-zinc-600 dark:bg-zinc-800 dark:text-neutral-100'
              }`}
            >
              {t(`settings.acp.loginStates.${login.status}`)}
              {login.error && <> {t(`settings.acp.loginErrors.${login.error}`)}</>}
            </p>
          )}
          {probe?.status === 'error' && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400 break-words">
              {probe.message}
            </p>
          )}
          {installErr && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400 break-words">
              {installErr}
            </p>
          )}
        </div>
      </SettingsListItem>
    );
  };

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.acp.title')} subtitle={t('settings.acp.subtitle')} />

      {/* Outbound: External ACP Coding Agents */}
      <SettingsCard className="space-y-4">
        <SectionCardHeader
          title={t('settings.acp.registeredTitle')}
          description={t('settings.acp.registeredDesc')}
          actions={
            <RefreshButton
              spinning={loading || refreshing}
              disabled={loading || refreshing}
              onClick={() => void loadAgents()}
            />
          }
        />

        {agents.length > 3 && (
          <div>
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('settings.acp.searchPlaceholder')}
              className="w-full px-3 py-2 text-xs font-medium border-2 border-brutal-black bg-white dark:bg-zinc-800 text-brutal-black dark:text-white placeholder:text-neutral-400 focus:outline-none"
            />
          </div>
        )}

        {loginError && (
          <p
            role="alert"
            className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
          >
            {t('settings.acp.loginRequestError')}
          </p>
        )}

        {loading ? (
          <div className="p-8 text-center font-bold uppercase text-neutral-500 dark:text-neutral-400">
            {t('common.loading')}
          </div>
        ) : agents.length === 0 ? (
          <div className="text-center py-8 text-neutral-600 dark:text-neutral-300 font-bold uppercase">
            {t('settings.acp.noAgents')}
          </div>
        ) : filteredAgents.length === 0 ? (
          <div className="text-center py-6 text-neutral-500 dark:text-neutral-400 text-xs font-bold uppercase">
            {t('settings.acp.noMatchingAgents')}
          </div>
        ) : (
          <div className="space-y-5">
            {installedAgents.length > 0 && (
              <div className="space-y-2.5">
                <div className="flex items-center justify-between text-[11px] font-black uppercase tracking-wider text-neutral-600 dark:text-neutral-300">
                  <span>{t('settings.acp.installedSection')}</span>
                  <span>{installedAgents.length}</span>
                </div>
                <div className="space-y-3">{installedAgents.map(renderAgentCard)}</div>
              </div>
            )}

            {catalogAgents.length > 0 && (
              <div className="space-y-2.5">
                <div className="flex items-center justify-between text-[11px] font-black uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
                  <span>{t('settings.acp.catalogSection')}</span>
                  <span>{catalogAgents.length}</span>
                </div>
                <div className="space-y-3">{catalogAgents.map(renderAgentCard)}</div>
              </div>
            )}
          </div>
        )}
      </SettingsCard>

      {/* Inbound: Editor Connections (suzent acp) */}
      <AcpConnections />
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
            : 'text-brutal-black dark:text-white hover:bg-neutral-100 dark:hover:bg-zinc-700'
        }`}
      >
        {copied ? t('settings.acp.copied') : t('settings.acp.copyCommand')}
      </button>
    </div>
  );
}
