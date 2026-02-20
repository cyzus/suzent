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
  path: string;           // Virtual path: /persistence/uploads/filename
  size: number;           // Bytes
  mime_type: string;
  uploaded_at?: string;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  stepInfo?: string; // Step metadata like "Step: 1 | Input tokens: 100 | Output tokens: 50"
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
}

export interface Chat {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: Message[];
  config: ChatConfig;
}

export interface ChatSummary {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  lastMessage?: string;
  platform?: string;
}

export type PlanPhaseStatus = 'pending' | 'in_progress' | 'completed';

export interface PlanPhase {
  id?: number;
  number: number;
  title: string;
  description: string;
  status: PlanPhaseStatus;
  note?: string;
  capabilities?: Record<string, any>;
  createdAt?: string;
  updatedAt?: string;
}

export interface Plan {
  id?: number;
  chatId?: string | null;
  objective: string;
  title?: string;
  phases: PlanPhase[];
  createdAt?: string;
  updatedAt?: string;
  versionKey: string;
}

// Added: configuration options exposed by backend (derived from suzent.config.Config)
export interface ConfigOptions {
  title: string;
  models: string[];
  agents: string[];
  tools: string[];        // full list of tool options
  defaultTools: string[]; // default enabled tools
  codeTag: string;        // CODE_TAG (e.g. <code>) so frontend can parse blocks consistently
  userId?: string;        // backend-provided user identifier for memory system alignment
  globalSandboxVolumes?: string[];  // global volumes from config file (read-only)
  sandboxEnabled?: boolean;         // global sandbox enable setting
  userPreferences?: {     // saved user preferences from database
    model: string;
    agent: string;
    tools: string[];
    memory_enabled: boolean;
    sandbox_enabled?: boolean;
    sandbox_volumes?: string[];
  };
}

// Stream event types from backend
export type StreamEventType =
  | 'stream_delta'    // Token streaming (both agents)
  | 'action'          // Action step completed with full metadata (both agents)
  | 'action_output'   // Action output (both agents)
  | 'tool_output'     // Tool execution result (ToolCallingAgent)
  | 'final_answer'    // Final answer (both agents)
  | 'planning'        // Planning step (both agents)
  | 'plan_refresh'    // Plan state update (both agents)
  | 'error'           // Error occurred (both agents)
  | 'stopped';        // Stream stopped by user (both agents)

export interface StreamEvent {
  type: StreamEventType;
  data: any;
}
