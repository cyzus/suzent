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

// --- Session & Transcript types (Phase 6: Frontend Integration) ---

export interface TranscriptEntry {
  ts: string;
  role: string;
  content: string;
  actions?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
}

export interface TranscriptResponse {
  session_id: string;
  entries: TranscriptEntry[];
  count: number;
}

export interface SessionStateResponse {
  session_id: string;
  state: Record<string, unknown>;
}

export interface DailyLogResponse {
  date: string;
  content: string;
  size_bytes: number;
}

export interface DailyLogListResponse {
  dates: string[];
  count: number;
}

export interface MemoryFileResponse {
  content: string;
  size_bytes: number;
}

export interface ReindexResponse {
  success: boolean;
  stats: Record<string, unknown>;
}
