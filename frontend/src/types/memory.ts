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
  utilized_memories?: number;
  utilization_rate?: number;
  recently_accessed_memories_7d?: number;
  recent_activity_rate_7d?: number;
  cold_memories?: number;
  cold_memory_ratio?: number;
  access_distribution?: {
    unaccessed?: number;
    light?: number;
    engaged?: number;
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

export interface DreamRunResult {
  ran?: boolean;
  started?: boolean;
  changed?: boolean;
  advanced?: boolean;
  skipped?: boolean;
  watermark?: string | null;
  target?: string | null;
  reason?: string;
}

export interface DreamStatus {
  active: boolean;
  available: boolean;
  enabled: boolean;
  running: boolean;
  phase?: 'idle' | 'queued' | 'preparing' | 'running_agent' | 'finalizing' | string;
  reason?: string;
  watermark?: string | null;
  pending_dates?: string[];
  pending_count?: number;
  pending_facts?: number;
  archive_count?: number;
  consolidated_count?: number;
  progress_percent?: number;
  next_batch_end?: string | null;
  last_attempt_at?: number | null;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_result?: DreamRunResult | null;
  failures?: Record<string, number>;
  min_facts?: number;
  min_hours?: number;
  max_days?: number;
}

export interface DreamConsolidateResponse {
  success: boolean;
  result: DreamRunResult;
}
