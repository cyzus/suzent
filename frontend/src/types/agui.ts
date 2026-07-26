import type { A2UISurface } from './a2ui';
import type { CitationSource } from '../lib/streamEvents';

export interface AGUIPart {
  type: 'text' | 'reasoning' | 'tool' | 'a2ui' | 'citation-sources';
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
