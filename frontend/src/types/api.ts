import type { AGUIPart } from './agui';

export interface ImageAttachment {
  id: string;
  data: string; // base64 encoded
  mime_type: string;
  filename: string;
  width?: number;
  height?: number;
}

export interface FileAttachment {
  id: string;
  filename: string;
  path: string; // Virtual path: /workspace/uploads/filename
  size: number; // Bytes
  mime_type: string;
  uploaded_at?: string;
  // Client-only: base64 image data captured at upload time so the optimistic
  // bubble can render instantly instead of flickering while the sandbox-serve
  // URL loads. Not persisted; absent after reload (serve URL is used then).
  preview_data?: string;
}

export interface MessageFileChange {
  path: string;
  display_path?: string;
  diff: string;
  additions: number;
  deletions: number;
}

export interface Message {
  role: 'user' | 'assistant' | 'notice' | 'canvas_action' | 'system_triggered';
  content: string;
  timestamp?: string; // ISO 8601 timestamp when the message was created
  model?: string; // Model used to produce an assistant message
  stepInfo?: string; // Step metadata like "Step: 1 | Input tokens: 100 | Output tokens: 50"
  parts?: AGUIPart[]; // Structured assistant display parts; content remains as fallback.
  _streaming_draft?: boolean; // Backend recovery snapshot for in-progress streams.
  _streaming_run_id?: string;
  images?: ImageAttachment[]; // Optional image attachments
  files?: FileAttachment[]; // Optional file attachments
  file_changes?: MessageFileChange[]; // Persisted file snapshot for this assistant turn
  file_changes_undone?: boolean; // Whether this message-scoped snapshot was restored
  file_change_message_index?: number; // Raw backend index used for message-scoped undo
  raw_message_end_index?: number; // End-exclusive backend boundary for this rendered message
  // Latest timestamp of any server row folded into this bubble (tool results and
  // merged follow-up responses). `timestamp` marks when the turn's first model
  // response *began*, so it alone cannot measure how long the turn worked.
  turn_last_activity_at?: string;
}
export interface ChatConfig {
  model: string;
  agent: string;
  tools: string[];
  mcp_urls?: string[] | Record<string, string>;
  mcp_enabled?: Record<string, boolean>;
  memory_enabled?: boolean;
  thinking?: ThinkingEffort;
  sandbox_enabled?: boolean;
  sandbox_volumes?: string[];
  tool_approval_policy?: Record<string, string>;
  permission_policies?: Record<string, Record<string, unknown>>;
  permission_mode?: PermissionMode;
  heartbeat_enabled?: boolean;
  heartbeat_interval_minutes?: number;
  heartbeat_instructions?: string;
  heartbeat_last_run_at?: string;
  platform?: string;
  cron_job_id?: number;
  forked_from_chat_id?: string;
  forked_from_chat_title?: string;
  forked_from_message_index?: number;
  acp_agent_id?: string;
  acp_agent_name?: string;
  acp_session_id?: string;
  runtime?: 'native' | 'acp';
}

export type PermissionMode = 'default' | 'auto' | 'full_access';

export function normalizePermissionMode(value: unknown): PermissionMode {
  return value === 'auto' || value === 'full_access' ? value : 'default';
}

/**
 * How hard the model should think before answering. 'auto' keeps whatever the
 * model does by default; the backend maps the rest onto pydantic-ai's unified
 * `thinking` setting and silently ignores it on models without reasoning.
 */
export type ThinkingEffort = 'auto' | 'off' | 'low' | 'medium' | 'high' | 'xhigh';

/** Ordered low-to-high; 'auto' leads as the "no opinion" end of the ramp. */
export const THINKING_EFFORTS: ThinkingEffort[] = ['auto', 'off', 'low', 'medium', 'high', 'xhigh'];

export function normalizeThinkingEffort(value: unknown): ThinkingEffort {
  return THINKING_EFFORTS.includes(value as ThinkingEffort) ? (value as ThinkingEffort) : 'auto';
}

export interface Chat {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: Message[];
  config: ChatConfig;
  contextTokens?: number;
  contextUsage?: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    context_tokens?: number | null;
    context_limit?: number | null;
    cache_write_tokens?: number;
    cache_read_tokens?: number;
    requests?: number;
    details?: Record<string, number>;
  };
}

export interface ChatSummary {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  lastMessage?: string;
  platform?: string;
  heartbeatEnabled?: boolean;
  lastResultAt?: string;
  isRunning?: boolean;
  unreadCount?: number;
  projectId?: string | null;
  projectSlug?: string | null;
  projectName?: string | null;
  parentChatId?: string | null;
  forkedFromChatId?: string | null;
  forkedFromChatTitle?: string | null;
  forkedFromMessageIndex?: number | null;
  acpAgentId?: string | null;
  acpAgentName?: string | null;
  acpSessionId?: string | null;
}

export interface ChatKindCounts {
  you: number;
  scheduled: number;
  all: number;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  createdAt: string;
  archived: boolean;
  chatCount: number;
}

export type GoalStatus = 'active' | 'paused' | 'completed' | 'cancelled';
// 'blocked' is derived on the backend from blockedBy being non-empty — not stored as a DB status
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'blocked' | 'cancelled';

export interface Goal {
  id: number;
  projectId: string;
  chatId?: string | null;
  objective: string;
  status: GoalStatus;
  subgoals: string[];
  maxTurns?: number | null;
  turnsElapsed: number;
  createdAt?: string;
  updatedAt?: string;
  completedAt?: string | null;
}

export interface Task {
  id: number;
  projectId: string;
  chatId?: string | null;
  title: string;
  description: string;
  activeForm?: string | null;
  status: TaskStatus;
  assignee?: string | null;
  blocks: number[];
  blockedBy: number[];
  createdAt?: string;
  updatedAt?: string;
  completedAt?: string | null;
}

// Added: configuration options exposed by backend (derived from suzent.config.Config)
export interface ConfigOptions {
  title: string;
  models: string[];
  defaultModel?: string | null; // first model from a provider with credentials; null if none configured
  agents: string[];
  tools: string[]; // full list of tool options
  defaultTools: string[]; // default enabled tools
  toolCapabilities?: ToolCapabilityOption[];
  codeTag: string; // CODE_TAG (e.g. <code>) so frontend can parse blocks consistently
  userId?: string; // backend-provided user identifier for memory system alignment
  globalSandboxVolumes?: string[]; // global volumes from config file
  sandboxEnabled?: boolean; // global sandbox enable setting
  defaultPermissionMode?: PermissionMode; // default permission mode for new chats
  contextWindows?: Record<string, number>; // context budget per enabled model id
  maxContextTokens?: number; // last-resort fallback when the selected model is unknown
  userPreferences?: {
    // saved user preferences from database
    model: string;
    agent: string;
    tools: string[];
    memory_enabled: boolean;
    thinking?: ThinkingEffort;
    sandbox_enabled?: boolean;
    sandbox_volumes?: string[];
    embedding_model?: string;
    extraction_model?: string;
  };
}

export interface ToolOption {
  id: string;
  name: string;
  description: string;
  runtimeName: string;
  requiresApproval: boolean;
}

export interface ToolCapabilityOption {
  id: string;
  label: string;
  description: string;
  tools: ToolOption[];
}

export interface AcpAgentDescriptor {
  id: string;
  name: string;
  description?: string;
  probe?: () => Promise<boolean>;
  install_command?: string[];
  login_command?: string[];
  /** Vendor install documentation — install routes are too plural to hardcode. */
  docs_url?: string | null;
  /** npm adapter this agent is launched through, when it runs via npx. */
  adapter_package?: string | null;
  /** 'ready' when the executable was found on PATH, else 'not_installed'. */
  status?: 'ready' | 'not_installed';
  executable_path?: string | null;
  /** True for agents shipped in the built-in registry. */
  builtin?: boolean;
  /** Auth status reported by the registry (e.g. 'unknown', 'ok', 'missing'). */
  auth_status?: string;
}

export interface ChatGPTStatusResponse {
  connected: boolean;
  status: 'connected' | 'not_logged_in' | 'token_expired';
  account_id?: string | null;
  error?: string;
}

export interface ChatGPTLoginResponse {
  success: boolean;
  verify_url?: string;
  user_code?: string;
  device_auth_id?: string;
  interval?: string;
  error?: string;
}

// Note: Stream event types removed — the frontend now uses AG-UI protocol
// via the useAGUI hook instead of manual SSE parsing.
