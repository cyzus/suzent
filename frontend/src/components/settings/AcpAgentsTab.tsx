import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, probeAcpAgent } from '../../lib/api';
import { AcpAgentDescriptor } from '../../types/api';
import { SettingsCard, SectionCardHeader, SettingsListItem, SettingsListAction } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

interface AcpAgentsTabProps {
  onNewSession: (agentId: string) => void;
}

export function AcpAgentsTab({ onNewSession }: AcpAgentsTabProps): React.ReactElement {
  const { t } = useI18n();
  const [agents, setAgents] = useState<AcpAgentDescriptor[]>([]);
  const [loading, setLoading] = useState(false);
  const [probeResults, setProbeResults] = useState<Record<string, any>>({});

  const loadAgents = async () => {
    setLoading(true);
    try {
      const data: AcpAgentDescriptor[] = await fetchAcpAgents();
      setAgents(data);
    } catch (e) {
      console.error('Failed to fetch agents', e);
    } finally {
      setLoading(false);
    }
  };

  const handleProbe = async (agent: AcpAgentDescriptor) => {
    if (agent.probe) {
        const result = await agent.probe();
        setProbeResults(prev => ({ ...prev, [agent.id]: result }));
        return;
    }
    try {
      const data = await probeAcpAgent(agent.id);
      setProbeResults(prev => ({ ...prev, [agent.id]: data }));
    } catch (e) {
      console.error('Probe failed', e);
    }
  };

  useEffect(() => {
    loadAgents();
  }, []);

  return (
    <div className="space-y-6">
      <SettingsHeader title={t('settings.acp.title')} subtitle={t('settings.acp.subtitle')} />
      <SettingsCard>
        <SectionCardHeader
          iconTone="black"
          icon={<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>}
          title={t('settings.acp.title')}
          description={t('settings.acp.subtitle')}
        />
        {loading ? (
          <div className="p-8 text-center font-bold uppercase text-neutral-500">{t('common.loading')}</div>
        ) : (
          <div className="space-y-4">
            {agents.map(agent => (
              <SettingsListItem key={agent.id}>
                <div className="flex flex-col md:flex-row items-start md:items-center gap-4 p-5">
                  <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-1">
                        <h3 className="text-lg font-black uppercase tracking-wide text-brutal-black dark:text-white truncate">
                          {agent.name}
                        </h3>
                        <span className="text-[10px] font-bold px-2 py-0.5 border-2 border-brutal-black shadow-[1px_1px_0_0_#000] uppercase bg-neutral-100 dark:bg-zinc-800">
                          ACP Agent
                        </span>
                      </div>
                      <div className="font-mono text-xs text-neutral-500 dark:text-neutral-400">
                        {agent.id}
                      </div>
                      {probeResults[agent.id] !== undefined && (
                        <div className="mt-2 text-[10px] font-mono border-2 border-brutal-black/20 p-2 bg-neutral-50 dark:bg-zinc-900 truncate">
                          {JSON.stringify(probeResults[agent.id])}
                        </div>
                      )}
                  </div>
                  <div className="flex flex-wrap gap-2 shrink-0">
                      <SettingsListAction tone="blue" onClick={() => onNewSession(agent.id)}>New Session</SettingsListAction>
                      <SettingsListAction onClick={() => handleProbe(agent)}>Probe</SettingsListAction>
                      {agent.install_command && (
                        <SettingsListAction onClick={() => navigator.clipboard.writeText(agent.install_command!.join(' '))}>Copy Install</SettingsListAction>
                      )}
                      {agent.login_command && (
                        <SettingsListAction onClick={() => navigator.clipboard.writeText(agent.login_command!.join(' '))}>Copy Login</SettingsListAction>
                      )}
                  </div>
                </div>
              </SettingsListItem>
            ))}
          </div>
        )}
      </SettingsCard>
    </div>
  );
}
