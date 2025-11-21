/**
 * Memory system types for frontend
 */

// Dynamic core memory blocks - supports any number of labels
export type CoreMemoryBlocks = Record<string, string>;

export type CoreMemoryLabel = string;

export interface ArchivalMemory {
  id: string;
  content: string;
  created_at: string;
  importance: number;
  access_count: number;
  metadata: Record<string, any>;
  similarity?: number;
}

export interface MemoryStats {
  total_memories: number;
  avg_importance: number;
  max_importance: number;
  min_importance: number;
  total_accesses: number;
  avg_access_count: number;
  importance_distribution: {
    high?: number;
    medium?: number;
    low?: number;
  };
}

export interface MemorySearchResponse {
  memories: ArchivalMemory[];
  count: number;
  offset: number;
  limit: number;
}
