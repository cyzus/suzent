/**
 * Memory API client functions
 */

import type {
  CoreMemoryBlocks,
  CoreMemoryLabel,
  ArchivalMemory,
  MemoryStats,
  MemorySearchResponse,
  TranscriptResponse,
  SessionStateResponse,
  DailyLogResponse,
  DailyLogListResponse,
  MemoryFileResponse,
  ReindexResponse,
  DreamConsolidateResponse,
  DreamStatus,
} from '../types/memory';
import { getApiBase } from './api';

const memoryEndpoint = () => `${getApiBase()}/memory`;

export const memoryApi = {
  /**
   * Get all core memory blocks
   */
  async getCoreMemory(userId: string = 'default-user', chatId?: string | null): Promise<CoreMemoryBlocks> {
    const params = new URLSearchParams({ user_id: userId });
    if (chatId) {
      params.set('chat_id', chatId);
    }
    const response = await fetch(`${memoryEndpoint()}/core?${params}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch core memory: ${response.statusText}`);
    }
    const data = await response.json();
    return data.blocks;
  },

  /**
   * Update a specific core memory block
   */
  async updateCoreMemoryBlock(
    label: CoreMemoryLabel,
    content: string,
    userId: string = 'default-user'
  ): Promise<void> {
    const response = await fetch(`${memoryEndpoint()}/core`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        label,
        content,
        user_id: userId,
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || 'Failed to update core memory block');
    }
  },

  /**
   * Search archival memories
   */
  async searchArchivalMemory(
    query: string = '',
    userId: string = 'default-user',
    limit: number = 20,
    offset: number = 0
  ): Promise<MemorySearchResponse> {
    const params = new URLSearchParams({
      user_id: userId,
      limit: limit.toString(),
      offset: offset.toString(),
    });

    if (query) {
      params.set('query', query);
    }

    const response = await fetch(`${memoryEndpoint()}/archival?${params}`);
    if (!response.ok) {
      throw new Error(`Failed to search archival memory: ${response.statusText}`);
    }

    return await response.json();
  },

  /**
   * Delete an archival memory by ID
   */
  async deleteArchivalMemory(memoryId: string): Promise<void> {
    const response = await fetch(`${memoryEndpoint()}/archival/${encodeURIComponent(memoryId)}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete memory: ${response.statusText}`);
    }
  },

  /**
   * Get memory statistics
   */
  async getMemoryStats(userId: string = 'default-user'): Promise<MemoryStats> {
    const response = await fetch(`${memoryEndpoint()}/stats?user_id=${encodeURIComponent(userId)}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch memory stats: ${response.statusText}`);
    }

    return await response.json();
  },

  // --- Session & Memory File APIs (Phase 6) ---

  /**
   * List all available daily memory log dates
   */
  async listDailyLogs(): Promise<DailyLogListResponse> {
    const response = await fetch(`${memoryEndpoint()}/daily`);
    if (!response.ok) {
      throw new Error(`Failed to list daily logs: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Get a specific daily memory log by date
   */
  async getDailyLog(date: string): Promise<DailyLogResponse> {
    const response = await fetch(`${memoryEndpoint()}/daily/${encodeURIComponent(date)}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch daily log: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Get the curated MEMORY.md content
   */
  async getMemoryFile(): Promise<MemoryFileResponse> {
    const response = await fetch(`${memoryEndpoint()}/file`);
    if (!response.ok) {
      throw new Error(`Failed to fetch MEMORY.md: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Get session transcript entries
   */
  async getSessionTranscript(sessionId: string, lastN?: number): Promise<TranscriptResponse> {
    const params = new URLSearchParams();
    if (lastN !== undefined) {
      params.set('last_n', lastN.toString());
    }
    const url = `${getApiBase()}/session/${encodeURIComponent(sessionId)}/transcript`;
    const qs = params.toString();
    const response = await fetch(qs ? `${url}?${qs}` : url);
    if (!response.ok) {
      throw new Error(`Failed to fetch transcript: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Get mirrored agent state for a session
   */
  async getSessionState(sessionId: string): Promise<SessionStateResponse> {
    const response = await fetch(`${getApiBase()}/session/${encodeURIComponent(sessionId)}/state`);
    if (!response.ok) {
      throw new Error(`Failed to fetch session state: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Trigger re-index of markdown memories into LanceDB
   */
  async reindexMemories(clearExisting: boolean = false): Promise<ReindexResponse> {
    const response = await fetch(`${memoryEndpoint()}/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clear_existing: clearExisting }),
    });
    if (!response.ok) {
      throw new Error(`Failed to reindex memories: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Get background dream consolidation status
   */
  async getDreamStatus(): Promise<DreamStatus> {
    const response = await fetch(`${memoryEndpoint()}/dream/status`);
    if (!response.ok) {
      throw new Error(`Failed to fetch dream status: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Trigger dream consolidation now
   */
  async consolidateMemory(): Promise<DreamConsolidateResponse> {
    const response = await fetch(`${memoryEndpoint()}/consolidate`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`Failed to consolidate memory: ${response.statusText}`);
    }
    return await response.json();
  },

  /**
   * Trigger dream lint now
   */
  async lintMemory(): Promise<DreamConsolidateResponse> {
    const response = await fetch(`${memoryEndpoint()}/lint`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`Failed to lint memory: ${response.statusText}`);
    }
    return await response.json();
  },
};
