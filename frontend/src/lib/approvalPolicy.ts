import type { ChatConfig } from '../types/api';

export function stripDenyApprovalPolicies(config: ChatConfig): ChatConfig {
  if (!config.tool_approval_policy) return config;

  const toolApprovalPolicy = Object.fromEntries(
    Object.entries(config.tool_approval_policy).filter(([, value]) => value !== 'always_deny'),
  );

  return {
    ...config,
    tool_approval_policy: Object.keys(toolApprovalPolicy).length ? toolApprovalPolicy : undefined,
  };
}
