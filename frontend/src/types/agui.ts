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
  displayData?: unknown;
  surface?: A2UISurface & { target?: string };
}

export type ApprovalRememberScope = 'session' | 'global' | null;
