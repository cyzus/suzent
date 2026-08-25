import React, { useCallback, useEffect, useState } from 'react';
import {
  addA2AAgent,
  cancelA2AOutboundTask,
  fetchA2AAgents,
  fetchA2AInboundTasks,
  fetchA2AOutboundTasks,
  fetchA2AStatus,
  fetchPeers,
  refreshA2AAgent,
  refreshA2AOutboundTask,
  removeA2AAgent,
  saveA2AStatus,
  sendToA2AAgent,
  setA2AAgentEnabled,
  type A2AAgent,
  type A2AInboundTask,
  type A2AOutboundTask,
  type A2AStatus,
  type A2ATaskState,
  type ControlledPeer,
} from '../../lib/api';
import { BrutalButton } from '../BrutalButton';
import { BrutalOnOff } from '../BrutalOnOff';
import { SettingsHeader } from './SettingsHeader';
import {
  SectionCardHeader,
  SettingsCard,
  SettingsPage,
  SettingsListAction,
  SettingsListItem,
} from './SettingsCard';
import { relativeTime } from '../../lib/chatUtils';
import { NetworkAccessCard } from './NetworkAccessCard';

const POLL_MS = 4000;

/**
 * How each mesh member was reached. Suzent peers come from the pairing ritual
 * (mDNS / Tailscale discovery + an operator-approved grant); A2A agents come
 * from a URL and the open standard. Showing this is the point of a unified tab:
 * both are agents you can delegate to, but they are trusted by different means.
 */
type Reach = 'suzent' | 'a2a';

const STATE_TONE: Record<A2ATaskState, string> = {
  submitted: 'bg-neutral-400',
  working: 'bg-brutal-blue',
  'input-required': 'bg-amber-400',
  'auth-required': 'bg-amber-400',
  completed: 'bg-brutal-green',
  canceled: 'bg-neutral-400',
  failed: 'bg-brutal-red',
  rejected: 'bg-brutal-red',
  unknown: 'bg-neutral-400',
};

/** States where the task is still ours to act on — never auto-hidden. */
function isLive(state: A2ATaskState): boolean {
  return ['submitted', 'working', 'input-required', 'auth-required'].includes(state);
}

function ReachBadge({ reach }: { reach: Reach }): React.ReactElement {
  const isSuzent = reach === 'suzent';
  return (
    <span
      className={`px-2 py-0.5 text-[10px] font-bold uppercase border-2 border-brutal-black ${
        isSuzent ? 'bg-brutal-blue text-white' : 'bg-brutal-yellow text-brutal-black'
      }`}
      title={
        isSuzent
          ? 'A paired Suzent device, found by LAN/Tailscale discovery and approved by you'
          : 'An external agent reached over the open A2A protocol'
      }
    >
      {isSuzent ? 'Suzent peer' : 'A2A'}
    </span>
  );
}

function StatePill({ state }: { state: A2ATaskState }): React.ReactElement {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase">
      <span className={`w-2.5 h-2.5 border border-brutal-black ${STATE_TONE[state]}`} />
      {state}
    </span>
  );
}

/** A task paused on `input-required`: the remote agent asked us something. */
function AnswerPrompt({
  task,
  busy,
  onAnswer,
}: {
  task: A2AOutboundTask;
  busy: boolean;
  onAnswer: (text: string) => void;
}): React.ReactElement {
  const [draft, setDraft] = useState('');
  return (
    <div className="mt-2 border-2 border-amber-400 bg-amber-50 dark:bg-amber-900/20 p-3">
      <p className="text-sm mb-2">
        <span className="font-bold uppercase text-[11px] mr-2">Needs your answer</span>
        {task.message || '(the agent did not say what it needs)'}
      </p>
      <div className="flex gap-2">
        <input
          className="flex-1 px-2 py-1 border-2 border-brutal-black bg-white dark:bg-zinc-900 text-sm"
          placeholder="Answer the agent…"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && draft.trim()) onAnswer(draft.trim());
          }}
        />
        <SettingsListAction
          tone="blue"
          disabled={busy || !draft.trim()}
          onClick={() => draft.trim() && onAnswer(draft.trim())}
        >
          Send
        </SettingsListAction>
      </div>
    </div>
  );
}

export function MeshTab(): React.ReactElement {
  const [status, setStatus] = useState<A2AStatus | null>(null);
  const [agents, setAgents] = useState<A2AAgent[]>([]);
  const [peers, setPeers] = useState<ControlledPeer[]>([]);
  const [outbound, setOutbound] = useState<A2AOutboundTask[]>([]);
  const [inbound, setInbound] = useState<A2AInboundTask[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [addUrl, setAddUrl] = useState('');
  const [addToken, setAddToken] = useState('');
  const [showCard, setShowCard] = useState(false);
  const [delegateTo, setDelegateTo] = useState<string | null>(null);
  const [delegateText, setDelegateText] = useState('');

  const refresh = useCallback(async () => {
    const [s, a, p, o, i] = await Promise.all([
      fetchA2AStatus(),
      fetchA2AAgents(),
      fetchPeers(),
      fetchA2AOutboundTasks(),
      fetchA2AInboundTasks(),
    ]);
    setStatus(s);
    setAgents(a);
    setPeers(p);
    setOutbound(o);
    setInbound(i);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const act = useCallback(
    async (key: string, fn: () => Promise<void>) => {
      setBusy(key);
      setError(null);
      try {
        await fn();
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(null);
      }
    },
    [refresh]
  );

  const handleAdd = () =>
    act('add', async () => {
      await addA2AAgent(addUrl.trim(), addToken.trim());
      setAddUrl('');
      setAddToken('');
    });

  const handleDelegate = (agentId: string) =>
    act(`send:${agentId}`, async () => {
      await sendToA2AAgent(agentId, delegateText.trim());
      setDelegateText('');
      setDelegateTo(null);
    });

  const handleAnswer = (task: A2AOutboundTask, text: string) =>
    act(`answer:${task.task_id}`, async () => {
      await sendToA2AAgent(task.agent_id, text, { taskId: task.task_id });
    });

  const liveTasks = outbound.filter((t) => isLive(t.state));
  const settledTasks = outbound.filter((t) => !isLive(t.state)).slice(0, 8);

  return (
    <SettingsPage>
      <SettingsHeader
        title="Mesh"
        subtitle="Every agent this device can reach — your paired Suzent devices and any external agent that speaks A2A."
      />

      {error && (
        <div className="border-2 border-brutal-red bg-red-50 p-3 text-sm dark:bg-red-900/20">
          {error}
        </div>
      )}

      {/* ─── Network access (canonical home) ────────────────────── */}
      <NetworkAccessCard />

      {/* ─── This device's identity ─────────────────────────────── */}
      <SettingsCard>
        <SectionCardHeader
          iconTone="black"
          title="This device"
          description={
            status ? `${status.name} · ${status.environment}` : 'Loading this device’s agent card…'
          }
          actions={
            <BrutalOnOff
              checked={!!status?.enabled}
              disabled={busy === 'publish'}
              onChange={(enabled) =>
                act('publish', async () => {
                  setStatus(await saveA2AStatus({ enabled }));
                })
              }
            />
          }
        />
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          {status?.enabled ? (
            <>
              Published. Any agent that can reach this address can read your card and discover that
              this device exists — it still needs a grant you approve before it can actually do
              anything.
            </>
          ) : (
            <>
              Not published. Your agent card is hidden and the well-known path returns 404, so this
              device is indistinguishable from one that never spoke A2A. You can still delegate{' '}
              <em>out</em> to other agents.
            </>
          )}
        </p>

        {status && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <code className="text-xs break-all text-neutral-500">{status.card_url}</code>
              <SettingsListAction onClick={() => setShowCard((v) => !v)}>
                {showCard ? 'Hide card' : 'View card'}
              </SettingsListAction>
            </div>
            {showCard && (
              <pre className="text-[11px] leading-relaxed overflow-x-auto bg-neutral-50 dark:bg-zinc-900 border-2 border-brutal-black p-3">
                {JSON.stringify(status.card, null, 2)}
              </pre>
            )}
          </div>
        )}
      </SettingsCard>

      {/* ─── Live delegated tasks ───────────────────────────────── */}
      {(liveTasks.length > 0 || settledTasks.length > 0) && (
        <SettingsCard>
          <SectionCardHeader
            iconTone="blue"
            title="Delegated work"
            description="Tasks you handed to another agent, and what they are doing with them."
          />
          <div className="space-y-3">
            {liveTasks.map((task) => (
              <SettingsListItem key={`${task.agent_id}:${task.task_id}`}>
                <div className="p-3">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <StatePill state={task.state} />
                        <span className="font-bold text-sm truncate">{task.agent_name}</span>
                      </div>
                      {task.prompt && (
                        <p className="text-xs text-neutral-500 mt-1 truncate">{task.prompt}</p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <SettingsListAction
                        disabled={busy === `refresh:${task.task_id}`}
                        onClick={() =>
                          act(`refresh:${task.task_id}`, async () => {
                            await refreshA2AOutboundTask(task.agent_id, task.task_id);
                          })
                        }
                      >
                        Refresh
                      </SettingsListAction>
                      <SettingsListAction
                        tone="red"
                        disabled={busy === `cancel:${task.task_id}`}
                        onClick={() =>
                          act(`cancel:${task.task_id}`, async () => {
                            await cancelA2AOutboundTask(task.agent_id, task.task_id);
                          })
                        }
                      >
                        Cancel
                      </SettingsListAction>
                    </div>
                  </div>
                  {(task.state === 'input-required' || task.state === 'auth-required') && (
                    <AnswerPrompt
                      task={task}
                      busy={busy === `answer:${task.task_id}`}
                      onAnswer={(text) => handleAnswer(task, text)}
                    />
                  )}
                </div>
              </SettingsListItem>
            ))}

            {settledTasks.map((task) => (
              <div
                key={`${task.agent_id}:${task.task_id}`}
                className="flex items-center justify-between gap-3 px-3 py-2 border-2 border-brutal-black/10 dark:border-white/10"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <StatePill state={task.state} />
                  <span className="text-sm truncate">{task.agent_name}</span>
                  <span className="text-xs text-neutral-500 truncate">{task.prompt}</span>
                </div>
                <span className="text-[11px] text-neutral-500 shrink-0">
                  {relativeTime(task.updated_at)}
                </span>
              </div>
            ))}
          </div>
        </SettingsCard>
      )}

      {/* ─── Mesh members ───────────────────────────────────────── */}
      <SettingsCard>
        <SectionCardHeader
          iconTone="blue"
          title="Agents in your mesh"
          description="Suzent peers are found automatically on your LAN or tailnet. External agents are added by URL — A2A has no public directory, so someone has to give you the address."
        />

        <div className="space-y-3">
          {peers.map((peer) => (
            <div
              key={peer.peer_id}
              className="flex items-center justify-between gap-3 px-3 py-2 border-2 border-brutal-black/15 dark:border-white/10"
            >
              <div className="flex items-center gap-2 min-w-0">
                <ReachBadge reach="suzent" />
                <span className="font-bold text-sm truncate">{peer.name || peer.base_url}</span>
                <code className="text-[11px] text-neutral-500 truncate">{peer.base_url}</code>
              </div>
              <span className="text-[11px] uppercase font-bold text-neutral-500 shrink-0">
                {peer.mode === 'trigger' ? 'ready' : peer.mode}
              </span>
            </div>
          ))}

          {agents.map((agent) => (
            <SettingsListItem key={agent.agent_id}>
              <div className="p-3">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <ReachBadge reach="a2a" />
                      <span className="font-bold text-sm truncate">{agent.name}</span>
                      {agent.has_token && (
                        <span className="text-[10px] uppercase font-bold text-neutral-500">
                          keyed
                        </span>
                      )}
                    </div>
                    <code className="text-[11px] text-neutral-500 break-all">{agent.base_url}</code>
                    {agent.card?.skills?.length ? (
                      <p className="text-xs text-neutral-500 mt-1">
                        Skills: {agent.card.skills.map((s) => s.name).join(', ')}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <BrutalOnOff
                      size="sm"
                      checked={agent.enabled}
                      disabled={busy === `toggle:${agent.agent_id}`}
                      onChange={(enabled) =>
                        act(`toggle:${agent.agent_id}`, async () => {
                          await setA2AAgentEnabled(agent.agent_id, enabled);
                        })
                      }
                    />
                    <SettingsListAction
                      tone="blue"
                      onClick={() =>
                        setDelegateTo(delegateTo === agent.agent_id ? null : agent.agent_id)
                      }
                    >
                      Delegate
                    </SettingsListAction>
                    <SettingsListAction
                      disabled={busy === `refresh-agent:${agent.agent_id}`}
                      onClick={() =>
                        act(`refresh-agent:${agent.agent_id}`, async () => {
                          await refreshA2AAgent(agent.agent_id);
                        })
                      }
                    >
                      Refresh
                    </SettingsListAction>
                    <SettingsListAction
                      tone="red"
                      disabled={busy === `remove:${agent.agent_id}`}
                      onClick={() =>
                        act(`remove:${agent.agent_id}`, async () => {
                          await removeA2AAgent(agent.agent_id);
                        })
                      }
                    >
                      Remove
                    </SettingsListAction>
                  </div>
                </div>

                {delegateTo === agent.agent_id && (
                  <div className="mt-3 flex gap-2">
                    <input
                      className="flex-1 px-2 py-1 border-2 border-brutal-black bg-white dark:bg-zinc-900 text-sm"
                      placeholder="What should this agent do?"
                      value={delegateText}
                      disabled={busy === `send:${agent.agent_id}`}
                      onChange={(e) => setDelegateText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && delegateText.trim()) {
                          handleDelegate(agent.agent_id);
                        }
                      }}
                    />
                    <SettingsListAction
                      tone="blue"
                      disabled={busy === `send:${agent.agent_id}` || !delegateText.trim()}
                      onClick={() => handleDelegate(agent.agent_id)}
                    >
                      Send
                    </SettingsListAction>
                  </div>
                )}
              </div>
            </SettingsListItem>
          ))}

          {peers.length === 0 && agents.length === 0 && (
            <p className="text-sm text-neutral-500">
              Nothing in the mesh yet. Pair a Suzent device from the Devices tab, or add an external
              agent below.
            </p>
          )}
        </div>

        {/* Add by URL — A2A's only universal discovery path. */}
        <div className="mt-6 pt-4 border-t-2 border-brutal-black/10 dark:border-white/10">
          <p className="text-[11px] font-bold uppercase mb-2">Add an external agent</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              className="flex-1 px-2 py-1 border-2 border-brutal-black bg-white dark:bg-zinc-900 text-sm"
              placeholder="https://agent.example.com"
              value={addUrl}
              disabled={busy === 'add'}
              onChange={(e) => setAddUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && addUrl.trim()) handleAdd();
              }}
            />
            <input
              className="sm:w-56 px-2 py-1 border-2 border-brutal-black bg-white dark:bg-zinc-900 text-sm"
              placeholder="Token (if required)"
              value={addToken}
              disabled={busy === 'add'}
              onChange={(e) => setAddToken(e.target.value)}
            />
            <BrutalButton disabled={busy === 'add' || !addUrl.trim()} onClick={handleAdd}>
              {busy === 'add' ? 'Fetching card…' : 'Add'}
            </BrutalButton>
          </div>
          <p className="text-xs text-neutral-500 mt-2">
            We fetch <code>/.well-known/agent-card.json</code> to confirm the address is a real A2A
            agent before saving it.
          </p>
        </div>
      </SettingsCard>

      {/* ─── Inbound work ───────────────────────────────────────── */}
      {inbound.length > 0 && (
        <SettingsCard>
          <SectionCardHeader
            iconTone="green"
            title="Work given to you"
            description="Tasks other agents have sent to this device."
          />
          <div className="space-y-2">
            {inbound.slice(0, 10).map((task) => (
              <div
                key={task.id}
                className="flex items-center justify-between gap-3 px-3 py-2 border-2 border-brutal-black/10 dark:border-white/10"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <StatePill state={task.state} />
                  <span className="text-xs text-neutral-500 truncate">{task.message}</span>
                </div>
                <code className="text-[11px] text-neutral-500 shrink-0">{task.context_id}</code>
              </div>
            ))}
          </div>
        </SettingsCard>
      )}
    </SettingsPage>
  );
}
