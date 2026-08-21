import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, probeAcpAgent } from '../../lib/api';
import { AcpAgentDescriptor } from '../../types/api';
import { SettingsCard, SectionCardHeader, SettingsListItem, SettingsListAction, Badge } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

interface AcpAgentsTabProps {
  onNewSession: (agentId: string) => void;
}

type ProbeState = { status: 'probing' } | { status: 'ok'; data: Record<string, unknown> } | { status: 'error'; message: string };

export function AcpAgentsTab({ onNewSession }: AcpAgentsTabProps): React.ReactElement {
  const { t } = useI18n();
  const [agents, setAgents] = useState<AcpAgentDescriptor[]>([]);
  const [loading, setLoading] = useState(true);
  const [probes, setProbes] = useState<Record<string, ProbeState>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadAgents = async () => {
    setLoading(true);
    try {
      setAgents(await fetchAcpAgents());
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
          [agent.id]: ok ? { status: 'ok', data: {} } : { status: 'error', message: 'probe returned false' },
        }));
        return;
      }
      const data = await probeAcpAgent(agent.id);
      setProbes(prev => ({ ...prev, [agent.id]: { status: 'ok', data } }));
    } catch (e) {
      setProbes(prev => ({ ...prev, [agent.id]: { status: 'error', message: String(e) } }));
    }
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(prev => prev === id ? null : prev), 1500);
  };

  useEffect(() => { loadAgents(); }, []);

  const isReady = (agent: AcpAgentDescriptor) => agent.status === 'ready';

  return (
    <div className="space-y-6">
      <SettingsHeader title={t('settings.acp.title')} subtitle={t('settings.acp.subtitle')} />

      <SettingsCard>
        <SectionCardHeader
          iconTone="black"
          icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>}
          title={t('settings.acp.registeredTitle')}
          description={t('settings.acp.registeredDesc')}
        />

        {loading ? (
          <div className="p-8 text-center font-bold uppercase text-neutral-500">{t('common.loading')}</div>
        ) : agents.length === 0 ? (
          <div className="text-center py-8 text-neutral-500 dark:text-neutral-400 font-bold uppercase">
            {t('settings.acp.noAgents')}
          </div>
        ) : (
          <div className="space-y-4">
            {agents.map(agent => {
              const probe = probes[agent.id];
              const ready = isReady(agent);
              return (
                <SettingsListItem key={agent.id}>
                  <div className="flex flex-col md:flex-row items-start md:items-center gap-4 p-4 md:p-5">
                    {/* Status dot */}
                    <div className="shrink-0 mt-1 md:mt-0">
                      <div className={`w-4 h-4 rounded-full border-2 border-brutal-black ${ready ? 'bg-brutal-green' : 'bg-neutral-300 dark:bg-neutral-600'}`} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0 w-full">
                      <div className="flex items-center gap-3 flex-wrap">
                        <h3 className="font-black uppercase tracking-wide text-brutal-black dark:text-white truncate">
                          {agent.name}
                        </h3>
                        <Badge tone={ready ? 'green' : 'amber'}>
                          {ready ? t('settings.acp.ready') : t('settings.acp.notInstalled')}
                        </Badge>
                        {agent.status !== undefined && (
                          <Badge tone="neutral">
                            {agent.executable_path ? t('settings.acp.custom') : t('settings.acp.builtIn')}
                          </Badge>
                        )}
                      </div>

                      {agent.description && (
                        <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">{agent.description}</p>
                      )}

                      <div className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400 mt-1.5 truncate" title={agent.executable_path || agent.id}>
                        {agent.executable_path || agent.id}
                      </div>

                      {/* Probe results */}
                      {probe && (
                        <div className="mt-2">
                          {probe.status === 'probing' ? (
                            <div className="text-[10px] font-bold uppercase text-neutral-500">
                              {t('settings.acp.probing')}
                            </div>
                          ) : probe.status === 'ok' ? (
                            <Badge tone="green">{t('settings.acp.probeOk')}</Badge>
                          ) : (
                            <Badge tone="red">{t('settings.acp.probeFailed')}: {probe.message}</Badge>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex flex-wrap gap-2 shrink-0 w-full md:w-auto mt-2 md:mt-0 justify-end md:self-start md:ml-4">
                      <SettingsListAction
                        tone="blue"
                        onClick={() => onNewSession(agent.id)}
                        disabled={!ready}
                      >
                        {t('settings.acp.newSession')}
                      </SettingsListAction>
                      <SettingsListAction
                        onClick={() => handleProbe(agent)}
                        disabled={!ready || probe?.status === 'probing'}
                      >
                        {probe?.status === 'probing' ? t('settings.acp.probing') : t('settings.acp.probe')}
                      </SettingsListAction>
                      {agent.install_command && (
                        <SettingsListAction
                          onClick={() => handleCopy(`install-${agent.id}`, agent.install_command!.join(' '))}
                        >
                          {copiedId === `install-${agent.id}` ? t('settings.acp.copied') : t('settings.acp.copyInstall')}
                        </SettingsListAction>
                      )}
                      {agent.login_command && (
                        <SettingsListAction
                          onClick={() => handleCopy(`login-${agent.id}`, agent.login_command!.join(' '))}
                        >
                          {copiedId === `login-${agent.id}` ? t('settings.acp.copied') : t('settings.acp.copyLogin')}
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
