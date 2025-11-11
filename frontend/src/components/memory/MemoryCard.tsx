/**
 * Memory Card Component
 * Displays a single archival memory with metadata
 */

import React, { useState } from 'react';
import type { ArchivalMemory } from '../../types/memory';

interface MemoryCardProps {
  memory: ArchivalMemory;
  onDelete: (memoryId: string) => Promise<void>;
}

export const MemoryCard: React.FC<MemoryCardProps> = ({ memory, onDelete }) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(memory.id);
    } catch (error) {
      console.error('Failed to delete memory:', error);
      setIsDeleting(false);
      setShowConfirm(false);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const getImportanceColor = (importance: number) => {
    if (importance >= 0.8) return 'bg-red-500';
    if (importance >= 0.5) return 'bg-yellow-500';
    return 'bg-neutral-400';
  };

  const tags = memory.metadata?.tags || [];

  return (
    <div className="border-3 border-brutal-black bg-white shadow-[4px_4px_0_0_#000000] rounded-none p-4 hover:translate-x-[-2px] hover:translate-y-[-2px] hover:shadow-[6px_6px_0_0_#000000] transition-all">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1">
          <p className="text-sm text-neutral-800 leading-relaxed">{memory.content}</p>
        </div>
        {!showConfirm ? (
          <button
            onClick={() => setShowConfirm(true)}
            className="flex-shrink-0 w-6 h-6 border-2 border-brutal-black hover:bg-red-500 hover:text-white flex items-center justify-center font-bold text-brutal-black transition-colors"
            title="Delete memory"
          >
            ×
          </button>
        ) : (
          <div className="flex gap-1">
            <button
              onClick={() => setShowConfirm(false)}
              disabled={isDeleting}
              className="px-2 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 text-xs font-bold"
            >
              No
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="px-2 py-1 border-2 border-brutal-black bg-red-500 hover:bg-red-600 text-white text-xs font-bold"
            >
              {isDeleting ? '...' : 'Yes'}
            </button>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3 text-xs text-neutral-600 flex-wrap">
        <span className="flex items-center gap-1">
          <span className="font-bold">Date:</span>
          {formatDate(memory.created_at)}
        </span>

        <span className="flex items-center gap-1">
          <span className="font-bold">Importance:</span>
          <div
            className={`w-12 h-2 border border-brutal-black ${getImportanceColor(memory.importance)}`}
            style={{ width: `${memory.importance * 48}px` }}
            title={memory.importance.toFixed(2)}
          />
          <span>{memory.importance.toFixed(2)}</span>
        </span>

        <span className="flex items-center gap-1">
          <span className="font-bold">Accessed:</span>
          {memory.access_count}×
        </span>

        {memory.similarity !== undefined && (
          <span className="flex items-center gap-1">
            <span className="font-bold">Relevance:</span>
            {memory.similarity.toFixed(2)}
          </span>
        )}
      </div>

      {tags.length > 0 && (
        <div className="flex gap-2 mt-2 flex-wrap">
          {tags.map((tag: string, idx: number) => (
            <span
              key={idx}
              className="px-2 py-1 border-2 border-brutal-black bg-yellow-200 text-xs font-bold uppercase"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
