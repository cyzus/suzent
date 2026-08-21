import type { AcpAgentDescriptor } from '../types/api';

/** An option in the chat input's engine picker. */
export interface EngineOption {
  value: string;
  label: string;
  group?: string;
  disabled?: boolean;
  hint?: string;
}

export type EngineSelection =
  | { kind: 'model'; model: string }
  | { kind: 'acp'; agentId: string };

const MODEL_PREFIX = 'model:';
const ACP_PREFIX = 'acp:';

export interface EngineLabels {
  models: string;
  acp: string;
  notInstalled: string;
  installHint: string;
}

/**
 * Build the combined "what answers this chat" option list.
 *
 * Native models come first; ACP agents follow in their own group. Agents that
 * aren't installed are left out entirely rather than shown greyed out — the
 * list is a menu of what you can actually run, and Settings › ACP Agents is
 * where you go to see the ones you don't have yet. The one exception is the
 * agent a chat is already bound to: it stays visible (disabled, with a hint)
 * so an existing ACP chat renders its agent's name instead of a bare key and
 * explains why it can't send.
 */
export function buildEngineOptions(params: {
  models: string[];
  agents: AcpAgentDescriptor[];
  canChooseRuntime: boolean;
  selectedAgentId?: string;
  labels: EngineLabels;
}): EngineOption[] {
  const { models, agents, canChooseRuntime, selectedAgentId, labels } = params;

  const modelOptions: EngineOption[] = models.map(model => ({
    value: `${MODEL_PREFIX}${model}`,
    label: model,
    group: labels.models,
  }));

  const isInstalled = (agent: AcpAgentDescriptor) => agent.status !== 'not_installed';

  const visible = canChooseRuntime
    ? agents.filter(agent => isInstalled(agent) || agent.id === selectedAgentId)
    : agents.filter(agent => agent.id === selectedAgentId);

  const agentOptions: EngineOption[] = visible.map(agent => {
    const unavailable = !isInstalled(agent);
    return {
      value: `${ACP_PREFIX}${agent.id}`,
      label: `ACP · ${agent.name || agent.id}`,
      group: labels.acp,
      disabled: unavailable,
      hint: unavailable
        ? (agent.docs_url || agent.install_command?.length ? labels.installHint : labels.notInstalled)
        : undefined,
    };
  });

  return [...modelOptions, ...agentOptions];
}

export function engineValue(params: {
  isAcpRuntime: boolean;
  acpAgentId?: string;
  model?: string;
}): string {
  if (params.isAcpRuntime && params.acpAgentId) {
    return `${ACP_PREFIX}${params.acpAgentId}`;
  }
  return `${MODEL_PREFIX}${params.model ?? ''}`;
}

export function parseEngineValue(value: string): EngineSelection {
  if (value.startsWith(ACP_PREFIX)) {
    return { kind: 'acp', agentId: value.slice(ACP_PREFIX.length) };
  }
  return { kind: 'model', model: value.slice(MODEL_PREFIX.length) };
}
