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
  path: string;           // Virtual path: /workspace/uploads/filename
  size: number;           // Bytes
  mime_type: string;
  uploaded_at?: string;
  // Client-only: base64 image data captured at upload time so the optimistic
  // bubble can render instantly instead of flickering while the sandbox-serve
  // URL loads. Not persisted; absent after reload (serve URL is used then).
  preview_data?: string;
}

export interface Message {
  role: 'user' | 'assistant' | 'notice' | 'canvas_action' | 'system_triggered';
  content: string;
  timestamp?: string;         // ISO 8601 timestamp when the message was created
  model?: string;             // Model used to produce an assistant message
  stepInfo?: string; // Step metadata like "Step: 1 | Input tokens: 100 | Output tokens: 50"
  parts?: AGUIPart[]; // Structured assistant display parts; content remains as fallback.
  _streaming_draft?: boolean; // Backend recovery snapshot for in-progress streams.
  _streaming_run_id?: string;
  images?: ImageAttachment[]; // Optional image attachments
  files?: FileAttachment[];   // Optional file attachments
}
export interface ChatConfig {
  model: string;
  agent: string;
  tools: string[];
  mcp_urls?: string[] | Record<string, string>;
  mcp_enabled?: Record<string, boolean>;
  memory_enabled?: boolean;
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
}

export type PermissionMode =
  | 'default'
  | 'accept_edits'
  | 'plan'
  | 'auto'
  | 'strict_readonly';

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
  tools: string[];        // full list of tool options
  defaultTools: string[]; // default enabled tools
  toolGroups?: { label: string; tools: string[] }[];
  codeTag: string;        // CODE_TAG (e.g. <code>) so frontend can parse blocks consistently
  userId?: string;        // backend-provided user identifier for memory system alignment
  globalSandboxVolumes?: string[];  // global volumes from config file
  sandboxEnabled?: boolean;         // global sandbox enable setting
  defaultPermissionMode?: PermissionMode; // default permission mode for new chats
  maxContextTokens?: number;        // max context window size in tokens
  userPreferences?: {     // saved user preferences from database
    model: string;
    agent: string;
    tools: string[];
    memory_enabled: boolean;
    sandbox_enabled?: boolean;
    sandbox_volumes?: string[];
    embedding_model?: string;
    extraction_model?: string;
  };
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
