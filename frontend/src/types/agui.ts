import type { A2UISurface } from './a2ui';

export interface AGUIPart {
  type: 'text' | 'reasoning' | 'tool' | 'a2ui';
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
  displayData?: unknown;
  surface?: A2UISurface & { target?: string };
}

export type ApprovalRememberScope = 'session' | 'global' | null;

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
  risk: 'safe' | 'low' | 'medium' | 'high' | 'critical';
  actions: PermissionAction[];
  metadata?: Record<string, unknown>;
}
