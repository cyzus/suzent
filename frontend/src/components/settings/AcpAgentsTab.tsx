import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, probeAcpAgent } from '../../lib/api';
import { AcpAgentDescriptor } from '../../types/api';
import { SettingsCard, SectionCardHeader, SettingsListItem, SettingsListAction, Badge } from './SettingsCard';
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
        />
        {loading ? (
          <div className="p-8 text-center font-bold uppercase text-neutral-500">{t('common.loading')}</div>
        ) : (
          <div className="space-y-3">
            {agents.map(agent => (
              <SettingsListItem key={agent.id}>
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <h3 className="font-black uppercase tracking-wide text-brutal-black dark:text-white truncate">
                        {agent.name}
                      </h3>
                      <Badge>ACP Agent</Badge>
                    </div>
                    <div className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400 mt-1">
                      {agent.id}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 shrink-0">
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
                {probeResults[agent.id] !== undefined && (
                  <div className="px-4 pb-4">
                    <pre className="text-[10px] font-mono bg-neutral-100 dark:bg-black p-2 border border-brutal-black/10 overflow-x-auto">
                      {JSON.stringify(probeResults[agent.id], null, 2)}
                    </pre>
                  </div>
                )}
              </SettingsListItem>
            ))}
          </div>
        )}
      </SettingsCard>
    </div>
  );
}
