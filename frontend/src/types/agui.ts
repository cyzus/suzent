import type { A2UISurface } from './a2ui';
import type { CitationSource } from '../lib/streamEvents';

export interface AGUIPart {
  type: 'text' | 'reasoning' | 'tool' | 'a2ui' | 'citation-sources' | 'acp-permission' | 'acp-notice';
  text?: string;
  messageId?: string;
  toolCallId?: string;
  toolName?: string;
  args?: string;
  argsReplayPending?: boolean;
  output?: string;
  state?: 'running' | 'completed' | 'error' | 'approval-requested';
  approvalId?: string;
  permission?: PermissionPrompt;
  permissionDecision?: ToolPermissionDecision;
  permissionResolution?: ToolPermissionResolution;
  displayData?: unknown;
  surface?: A2UISurface & { target?: string };
  /** For 'citation-sources' parts: the sources registered during this run. */
  citationSources?: CitationSource[];
  /** For 'acp-permission' parts: an external ACP agent awaiting approval. */
  acpPermission?: AcpPermissionRequest;
  /** For 'acp-notice' parts: an out-of-band ACP runtime notice. */
  acpNotice?: AcpNotice;
}

export interface AcpPermissionOption {
  optionId: string;
  name: string;
  kind: 'allow_once' | 'allow_always' | 'reject_once' | 'reject_always';
}

export interface AcpPermissionRequest {
  requestId: string;
  chatId: string;
  sessionId: string;
  toolCall: {
    toolCallId?: string;
    title?: string;
    kind?: string;
    rawInput?: unknown;
  };
  options: AcpPermissionOption[];
  createdAt?: number;
  /** Set once answered, so the prompt renders its outcome instead of buttons. */
  resolved?: 'approved' | 'denied';
}

export interface AcpNotice {
  kind: 'session_reset';
  agentId?: string;
  requestedSessionId?: string;
  sessionId?: string;
  reason?: string;
}

export type ApprovalRememberScope = 'session' | 'global' | null;
export type PermissionDecisionSource = 'policy' | 'rule' | 'auto_classifier' | 'full_access';
export type PermissionRisk = 'safe' | 'low' | 'medium' | 'high' | 'critical';

export interface PermissionAction {
  id: string;
  label: string;
  behavior: 'allow' | 'deny';
  scope: 'once' | 'session' | 'global';
  feedbackKind?: 'accept' | 'reject';
  permissionUpdates?: Array<{
    type: 'add_rule' | 'set_mode';
    destination: 'session' | 'global';
    payload: Record<string, unknown>;
  }>;
}

export interface PermissionPrompt {
  behavior: 'allow' | 'ask' | 'deny';
  reason: string;
  reasonCode: string;
  risk: PermissionRisk;
  source?: PermissionDecisionSource;
  actions: PermissionAction[];
  metadata?: Record<string, unknown>;
}

export interface ToolPermissionDecision {
  toolCallId: string;
  toolName: string;
  behavior: 'allow' | 'ask' | 'deny';
  source: PermissionDecisionSource;
  reason: string;
  reasonCode: string;
  risk: PermissionRisk;
  confidence?: 'low' | 'medium' | 'high' | number | null;
  riskCategories: string[];
  reviewerModel?: string | null;
}

export interface ToolPermissionResolution {
  toolCallId: string;
  behavior: 'allow' | 'deny';
  source: 'user';
  actionId: string;
  scope: 'once' | 'session' | 'global';
}
