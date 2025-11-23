export interface ImageAttachment {
  id: string;
  data: string; // base64 encoded
  mime_type: string;
  filename: string;
  width?: number;
  height?: number;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  stepInfo?: string; // Step metadata like "Step: 1 | Input tokens: 100 | Output tokens: 50"
  images?: ImageAttachment[]; // Optional image attachments
}
export interface ChatConfig {
  model: string;
  agent: string;
  tools: string[];
  mcp_urls?: string[];
  memory_enabled?: boolean;
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
}

export type PlanTaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface PlanTask {
  id?: number;
  number: number;
  description: string;
  status: PlanTaskStatus;
  note?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface Plan {
  id?: number;
  chatId?: string | null;
  objective: string;
  title?: string;
  tasks: PlanTask[];
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
