export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  files?: FileMetadata[];
}

export interface FileMetadata {
  name: string;
  content_type: string;
  size?: number;
}

export interface ChatSession {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface NodeCapability {
  name: string;
  description: string;
  params_schema: Record<string, string>;
}

export interface NodeInfo {
  node_id: string;
  display_name: string;
  platform: string;
  status: string;
  connected_at: string;
  capabilities: NodeCapability[];
}

export type NodeStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface StreamEvent {
  type: string;
  delta?: string;
  content?: string;
  name?: string;
  data?: unknown;
  error?: string;
}
