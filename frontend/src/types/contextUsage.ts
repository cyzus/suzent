export type ContextCategoryId =
  | 'messages'
  | 'tool_results'
  | 'system_tools'
  | 'mcp_tools'
  | 'system_prompt'
  | 'skills'
  | 'memory'
  | 'repository'
  | 'other';

export interface ContextCategory {
  id: ContextCategoryId;
  tokens: number;
  items: { name: string; tokens: number }[];
}

export interface ContextBreakdown {
  method: 'character_estimate';
  categories: ContextCategory[];
  deferred: ContextCategory[];
  estimated_tokens: number;
  reserve_tokens: number;
  measured_input_tokens: number | null;
  overhead_estimate?: number;
  has_unmeasured_media: boolean;
}
