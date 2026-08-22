import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, fetchAcpSessions, probeAcpAgent } from '../../lib/api';
import type { AcpAgentDescriptor } from '../../types/api';
import { BrutalLink } from '../BrutalButton';
import { SectionCardHeader, SettingsListItem, SettingsListAction, Badge } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';
import { AcpAgentIcon } from '../AcpAgentIcon';

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
  | { status: 'ok'; data: Record<string, unknown> }
  | { status: 'error'; message: string };

export function AcpAgentsTab(): React.ReactElement {
  const { t } = useI18n();
  const [agents, setAgents] = useState<AcpAgentDescriptor[]>([]);
  const [loading, setLoading] = useState(true);
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [sessionCounts, setSessionCounts] = useState<
    Record<string, { saved: number; active: number }>
  >({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadAgents = async () => {
    setLoading(true);
    try {
      const loaded = await fetchAcpAgents();
      setAgents(loaded);
      // Load per-agent session counts in the background.
      const counts: Record<string, { saved: number; active: number }> = {};
      await Promise.allSettled(
        loaded
          .filter(a => a.status === 'ready')
          .map(async a => {
            try {
              const { saved, active } = await fetchAcpSessions(a.id);
              counts[a.id] = { saved: saved.length, active };
            } catch {
              /* skip */
            }
          }),
      );
      setSessionCounts(counts);
    } catch (e) {
      console.error('Failed to fetch agents', e);
    } finally {
      setLoading(false);
    }
  };

  const handleProbe = async (agent: AcpAgentDescriptor) => {
    setProbes(prev => ({ ...prev, [agent.id]: { status: 'probing' } }));
    try {
      if (agent.probe) {
        const ok = await agent.probe();
        setProbes(prev => ({
          ...prev,
          [agent.id]: ok
            ? { status: 'ok', data: {} }
            : { status: 'error', message: 'probe returned false' },
        }));
        return;
      }
      const data = await probeAcpAgent(agent.id);
      setProbes(prev => ({ ...prev, [agent.id]: { status: 'ok', data } }));
    } catch (e) {
      setProbes(prev => ({
        ...prev,
        [agent.id]: { status: 'error', message: String(e) },
      }));
    }
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(prev => (prev === id ? null : prev)), 1500);
  };

  useEffect(() => {
    loadAgents();
  }, []);

  const isReady = (agent: AcpAgentDescriptor) => agent.status === 'ready';

  return (
    <div className="space-y-6">
      <SettingsHeader
        title={t('settings.acp.title')}
        subtitle={t('settings.acp.subtitle')}
      />

      <section>
        <SectionCardHeader
          className="border-l-4 border-brutal-black bg-white p-4 dark:border-white dark:bg-zinc-800"
          iconTone="black"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          }
          title={t('settings.acp.registeredTitle')}
          description={t('settings.acp.registeredDesc')}
        />

        {loading ? (
          <div className="p-8 text-center font-bold uppercase text-neutral-500">
            {t('common.loading')}
          </div>
        ) : agents.length === 0 ? (
          <div className="text-center py-8 text-neutral-500 dark:text-neutral-400 font-bold uppercase">
            {t('settings.acp.noAgents')}
          </div>
        ) : (
          <div className="space-y-4">
            {agents.map(agent => {
              const probe = probes[agent.id];
              const ready = isReady(agent);
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
                          {ready && agent.auth_status && (
                            <AuthBadge status={agent.auth_status} t={t} />
                          )}
                          <Badge tone={ready ? 'green' : 'amber'}>
                            {ready ? t('settings.acp.ready') : t('settings.acp.notInstalled')}
                          </Badge>
                        </div>
                      </div>
                      {agent.description && (
                        <div className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                          {agent.description}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Where it lives, who defined it, what it's running */}
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 border-b-2 border-brutal-black/10 dark:border-white/10">
                    <span
                      className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400 truncate min-w-0 flex-1 basis-48"
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
                      <Badge
                        tone={activeSessions > 0 ? 'blue' : 'neutral'}
                        className="shrink-0"
                      >
                        {activeSessions > 0
                          ? t('settings.acp.activeSessions').replace(
                              '{count}',
                              String(activeSessions),
                            )
                          : savedSessions > 0
                            ? t('settings.acp.savedSessions').replace(
                                '{count}',
                                String(savedSessions),
                              )
                            : t('settings.acp.noSessions')}
                      </Badge>
                    )}
                  </div>

                  {/* The fix, in place of the status it explains */}
                  {needsSetup && (
                    <div className="border-b-2 border-brutal-black">
                      <div className="border-b-2 border-brutal-black bg-amber-400 text-brutal-black px-4 py-1.5 text-[11px] font-black uppercase tracking-wide">
                        {t('settings.acp.setupTitle')}
                      </div>
                      <div className="p-4 space-y-3">
                        {agent.docs_url && (
                          <div className="space-y-2">
                            <p className="text-[11px] text-neutral-600 dark:text-neutral-400">
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
                            <div className="text-[10px] font-black uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                              {adapter
                                ? t('settings.acp.adapterTitle')
                                : t('settings.acp.copyInstall')}
                            </div>
                            {adapter && (
                              <p className="text-[11px] text-neutral-600 dark:text-neutral-400">
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
                    </div>
                  )}

                  {/* Actions — the probe result reads on the line it came from */}
                  <div className="flex flex-wrap items-center gap-2 p-4">
                    <SettingsListAction
                      onClick={() => handleProbe(agent)}
                      disabled={!ready || probe?.status === 'probing'}
                    >
                      {probe?.status === 'probing'
                        ? t('settings.acp.probing')
                        : t('settings.acp.probe')}
                    </SettingsListAction>
                    {/* Logging in before the CLI exists is a dead end; the
                        setup panel is the only useful action until then. */}
                    {ready && agent.login_command && (
                      <SettingsListAction
                        onClick={() =>
                          handleCopy(
                            `login-${agent.id}`,
                            agent.login_command!.join(' '),
                          )
                        }
                      >
                        {copiedId === `login-${agent.id}`
                          ? t('settings.acp.copied')
                          : t('settings.acp.copyLogin')}
                      </SettingsListAction>
                    )}
                    {ready && agent.docs_url && (
                      <ExternalAction href={agent.docs_url} label={t('settings.acp.docs')} />
                    )}
                    {probe && (
                      <div className="ml-auto shrink-0">
                        {probe.status === 'probing' ? (
                          <span className="text-[10px] font-bold uppercase text-neutral-500">
                            {t('settings.acp.probing')}
                          </span>
                        ) : probe.status === 'ok' ? (
                          <Badge tone="green">{t('settings.acp.probeOk')}</Badge>
                        ) : (
                          <Badge tone="red" title={probe.message}>
                            {t('settings.acp.probeFailed')}
                          </Badge>
                        )}
                      </div>
                    )}
                  </div>
                </SettingsListItem>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Setup helpers
// ---------------------------------------------------------------------------

/**
 * Link styled to match `SettingsListAction` so an outbound link sits in the
 * same action row as the buttons without reading as a different control.
 */
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

  if (primary) {
    return (
      <BrutalLink
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        variant="primary"
        size="sm"
        className="uppercase"
      >
        {content}
      </BrutalLink>
    );
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex items-center gap-1.5 rounded-sm border border-brutal-black/20 px-3 py-1 text-[11px] font-bold uppercase text-neutral-500 transition-colors hover:border-brutal-black hover:bg-neutral-100 hover:text-brutal-black dark:border-white/10 dark:text-neutral-400 dark:hover:border-white dark:hover:bg-zinc-800 dark:hover:text-white"
    >
      {content}
    </a>
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
