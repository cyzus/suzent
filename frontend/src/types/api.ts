export interface Message { role: 'user' | 'assistant'; content: string; }
export interface ChatConfig { model: string; agent: string; tools: string[]; mcp_urls?: string[] }

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
  tasks: PlanTask[];
  createdAt?: string;
  updatedAt?: string;
  versionKey: string;
}

export interface PlanHistoryResponse {
  current: Plan | null;
  history: Plan[];
}

// Added: configuration options exposed by backend (derived from suzent.config.Config)
export interface ConfigOptions {
  title: string;
  models: string[];
  agents: string[];
  tools: string[];        // full list of tool options
  defaultTools: string[]; // default enabled tools
  codeTag: string;        // CODE_TAG (e.g. <code>) so frontend can parse blocks consistently
}
