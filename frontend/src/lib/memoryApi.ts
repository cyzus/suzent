/**
 * Memory API client functions
 */

import type {
  CoreMemoryBlocks,
  CoreMemoryLabel,
  ArchivalMemory,
  MemoryStats,
  MemorySearchResponse,
} from '../types/memory';

const API_BASE = '/api/memory';

export const memoryApi = {
  /**
   * Get all core memory blocks
   */
  async getCoreMemory(userId: string = 'default-user'): Promise<CoreMemoryBlocks> {
    const response = await fetch(`${API_BASE}/core?user_id=${encodeURIComponent(userId)}`);
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
    const response = await fetch(`${API_BASE}/core`, {
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

    const response = await fetch(`${API_BASE}/archival?${params}`);
    if (!response.ok) {
      throw new Error(`Failed to search archival memory: ${response.statusText}`);
    }

    return await response.json();
  },

  /**
   * Delete an archival memory by ID
   */
  async deleteArchivalMemory(memoryId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/archival/${encodeURIComponent(memoryId)}`, {
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
    const response = await fetch(`${API_BASE}/stats?user_id=${encodeURIComponent(userId)}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch memory stats: ${response.statusText}`);
    }

    return await response.json();
  },
};
