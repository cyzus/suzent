import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchAcpAgents, probeAcpAgent } from '../../lib/api';
import { AcpAgentDescriptor } from '../../types/api';
import { SettingsCard, SectionCardHeader, SettingsListItem, SettingsListAction, Badge } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

interface AcpAgentsTabProps {
  onNewSession: (agentId: string) => void;
}

type ProbeState =
  | { status: 'probing' }
  | { status: 'ok'; data: Record<string, unknown> }
  | { status: 'error'; message: string };

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
              return (
                <SettingsListItem key={agent.id}>
                  <div className="p-4 md:p-5 space-y-3">
                    {/* Row 1: name + badges */}
                    <div className="flex items-center gap-3 flex-wrap">
                      <div
                        className={`w-3 h-3 rounded-full border-2 border-brutal-black shrink-0 ${
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
                        {agent.executable_path ? t('settings.acp.custom') : t('settings.acp.builtIn')}
                      </Badge>
                    </div>

                    {/* Row 2: path / id */}
                    <div
                      className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400 truncate"
                      title={agent.executable_path || agent.id}
                    >
                      {agent.executable_path || agent.id}
                    </div>

                    {/* Row 3: probe result (if any) */}
                    {probe && (
                      <div>
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

                    {/* Row 4: actions */}
                    <div className="flex flex-wrap gap-2 pt-1">
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
