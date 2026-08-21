import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, fetchAcpSessions, probeAcpAgent } from '../../lib/api';
import type { AcpAgentDescriptor } from '../../types/api';
import { SettingsCard, SectionCardHeader, SettingsListItem, SettingsListAction, Badge } from './SettingsCard';
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

      <SettingsCard>
        <SectionCardHeader
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
              return (
                <SettingsListItem key={agent.id}>
                  <div className="p-4 md:p-5 space-y-3">
                    {/* Row 1: icon + status dot + name + badges */}
                    <div className="flex items-center gap-3 flex-wrap">
                      <span className={ready ? 'text-brutal-black dark:text-white' : 'text-neutral-400 dark:text-neutral-500'}>
                        <AcpAgentIcon id={agent.id} />
                      </span>
                      <div
                        className={`w-2.5 h-2.5 rounded-full border-2 border-brutal-black shrink-0 ${
                          ready ? 'bg-brutal-green' : 'bg-neutral-300 dark:bg-neutral-600'
                        }`}
                      />
                      <span className="font-black uppercase tracking-wide text-brutal-black dark:text-white text-base">
                        {agent.name}
                      </span>
                      <Badge tone={ready ? 'green' : 'amber'}>
                        {ready ? t('settings.acp.ready') : t('settings.acp.notInstalled')}
                      </Badge>
                      <Badge tone="neutral">
                        {agent.builtin ? t('settings.acp.builtIn') : t('settings.acp.custom')}
                      </Badge>
                      {ready && agent.auth_status && (
                        <AuthBadge status={agent.auth_status} t={t} />
                      )}
                    </div>

                    {/* Row 2: description */}
                    {agent.description && (
                      <div className="text-xs text-neutral-500 dark:text-neutral-400 pl-8">
                        {agent.description}
                      </div>
                    )}

                    {/* Row 3: executable path + session counts */}
                    <div className="flex items-center gap-4 pl-8 min-w-0">
                      <span
                        className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400 truncate min-w-0 flex-1"
                        title={agent.executable_path || agent.id}
                      >
                        {agent.executable_path || agent.id}
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

                    {/* Row 4: probe result (if any) */}
                    {probe && (
                      <div className="pl-8">
                        {probe.status === 'probing' ? (
                          <span className="text-[10px] font-bold uppercase text-neutral-500">
                            {t('settings.acp.probing')}
                          </span>
                        ) : probe.status === 'ok' ? (
                          <Badge tone="green">{t('settings.acp.probeOk')}</Badge>
                        ) : (
                          <Badge tone="red">
                            {t('settings.acp.probeFailed')}
                          </Badge>
                        )}
                      </div>
                    )}

                    {/* Row 5: actions — status checks and clipboard helpers only */}
                    <div className="flex flex-wrap gap-2 pt-1 pl-8">
                      <SettingsListAction
                        onClick={() => handleProbe(agent)}
                        disabled={!ready || probe?.status === 'probing'}
                      >
                        {probe?.status === 'probing'
                          ? t('settings.acp.probing')
                          : t('settings.acp.probe')}
                      </SettingsListAction>
                      {agent.install_command && (
                        <SettingsListAction
                          onClick={() =>
                            handleCopy(
                              `install-${agent.id}`,
                              agent.install_command!.join(' '),
                            )
                          }
                        >
                          {copiedId === `install-${agent.id}`
                            ? t('settings.acp.copied')
                            : t('settings.acp.copyInstall')}
                        </SettingsListAction>
                      )}
                      {agent.login_command && (
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
                    </div>
                  </div>
                </SettingsListItem>
              );
            })}
          </div>
        )}
      </SettingsCard>
    </div>
  );
}
