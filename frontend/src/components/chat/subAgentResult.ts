import type { SubAgentStatus } from './SubAgentCallBlock';

export interface SubAgentResultInfo {
  taskId?: string;
  /** The task's state as of the moment the tool returned, not necessarily now. */
  status?: SubAgentStatus;
  resultSummary?: string;
  error?: string;
  /** Which model ran it -- the agent's identity, not just its outcome. */
  model?: string;
  /** The profile it was spawned as: 'verify', 'explore', 'plan', … */
  subagentType?: string;
}

const SUB_AGENT_STATUSES = new Set<SubAgentStatus>([
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled',
]);

/**
 * The agent tool returns a JSON envelope whose `metadata` already carries the
 * task id and status, so read those rather than pattern-matching the prose
 * beside them. The old ID-only pattern matched just the "spawned (ID: x)"
 * wording and missed "Sub-agent x completed", which is why a reloaded chat
 * mostly lost its task ids -- and with them the button that opens the sidebar.
 *
 * The fallback still matters: a tool call that timed out carries no id at all,
 * and a result can reach us as a non-JSON payload.
 */
export function parseSubAgentResult(output: string | undefined): SubAgentResultInfo {
  if (!output) return {};
  const trimmed = output.trim();

  if (trimmed.startsWith('{')) {
    try {
      const envelope = JSON.parse(trimmed);
      const metadata = envelope?.metadata;
      if (metadata && typeof metadata === 'object') {
        const status = metadata.status;
        // A call that never spawned anything — an unknown subagent_type, an
        // unrecognized tool list — comes back as a failure envelope with an
        // empty metadata object. Reading metadata alone found no status, and
        // the caller's fallback treats any output at all as success, so a
        // rejected call rendered as DONE beside the ones that really ran.
        // `metadata.status` still wins where it exists: a timed-out call
        // deliberately reports 'running', because its sub-agent may well be.
        const failed = envelope?.success === false;
        const message = typeof envelope?.message === 'string' ? envelope.message : undefined;
        return {
          taskId: typeof metadata.task_id === 'string' ? metadata.task_id : undefined,
          status: SUB_AGENT_STATUSES.has(status) ? status : failed ? 'failed' : undefined,
          resultSummary:
            typeof metadata.result_summary === 'string' ? metadata.result_summary : undefined,
          error: typeof metadata.error === 'string' ? metadata.error : failed ? message : undefined,
          model: typeof metadata.model_override === 'string' ? metadata.model_override : undefined,
          subagentType:
            typeof metadata.subagent_type === 'string' ? metadata.subagent_type : undefined,
        };
      }
    } catch {
      // Not valid JSON. Fall through to the prose scan below.
    }
  }

  const match = trimmed.match(/sub_[a-z0-9]+/);
  return match ? { taskId: match[0] } : {};
}
