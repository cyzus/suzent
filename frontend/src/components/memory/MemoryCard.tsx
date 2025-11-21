/**
 * Memory Card Component
 * Displays a single archival memory with metadata and enhanced visual design
 */

import React, { useState } from 'react';
import type { ArchivalMemory } from '../../types/memory';

interface MemoryCardProps {
  memory: ArchivalMemory;
  onDelete: (memoryId: string) => Promise<void>;
  searchQuery?: string;
}

export const MemoryCard: React.FC<MemoryCardProps> = ({ memory, onDelete, searchQuery }) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

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
      const date = new Date(dateString);
      const now = new Date();
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

      if (diffDays === 0) return 'Today';
      if (diffDays === 1) return 'Yesterday';
      if (diffDays < 7) return `${diffDays} days ago`;

      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const getImportanceColor = (importance: number) => {
    if (importance >= 0.8) return 'bg-brutal-red';
    if (importance >= 0.5) return 'bg-brutal-yellow';
    return 'bg-brutal-gray';
  };

  const getImportanceLabel = (importance: number) => {
    if (importance >= 0.8) return 'HIGH';
    if (importance >= 0.5) return 'MEDIUM';
    return 'LOW';
  };

  const isRecent = () => {
    try {
      const date = new Date(memory.created_at);
      const now = new Date();
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
      return diffDays < 7;
    } catch {
      return false;
    }
  };

  const isFrequentlyAccessed = memory.access_count >= 5;

  const highlightText = (text: string, query?: string) => {
    if (!query || query.trim() === '') return text;

    const parts = text.split(new RegExp(`(${query})`, 'gi'));
    return (
      <>
        {parts.map((part, i) =>
          part.toLowerCase() === query.toLowerCase() ? (
            <mark key={i} className="bg-brutal-black text-white font-bold px-1">
              {part}
            </mark>
          ) : (
            part
          )
        )}
      </>
    );
  };

  const tags = memory.metadata?.tags || [];
  const category = memory.metadata?.category;
  const shouldTruncate = memory.content.length > 200;
  const displayContent = !isExpanded && shouldTruncate
    ? memory.content.slice(0, 200) + '...'
    : memory.content;

  return (
    <div className="border-3 border-brutal-black bg-white shadow-brutal hover:translate-x-[-2px] hover:translate-y-[-2px] hover:shadow-brutal-lg transition-all animate-brutal-drop">
      <div className="p-4">
        {/* Header with badges */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex gap-2 flex-wrap items-center">
            {/* Importance text indicator */}
            <span className="text-xs font-bold uppercase text-brutal-black">
              {getImportanceLabel(memory.importance)} [{memory.importance.toFixed(2)}]
            </span>

            {/* Category badge */}
            {category && (
              <span className="px-2 py-0.5 border-2 border-brutal-black bg-white text-brutal-black text-xs font-bold uppercase">
                {category}
              </span>
            )}

            {/* Recent indicator */}
            {isRecent() && (
              <span className="text-xs font-bold uppercase text-brutal-black">
                NEW
              </span>
            )}

            {/* Frequently accessed indicator */}
            {isFrequentlyAccessed && (
              <span className="text-xs font-bold uppercase text-brutal-black">
                HOT
              </span>
            )}
          </div>

          {/* Delete button */}
          {!showConfirm ? (
            <button
              onClick={() => setShowConfirm(true)}
              className="flex-shrink-0 w-7 h-7 border-2 border-brutal-black hover:bg-brutal-black hover:text-white flex items-center justify-center font-bold text-brutal-black transition-all active:translate-x-[1px] active:translate-y-[1px] shadow-[2px_2px_0_0_#000000] active:shadow-none"
              title="Delete memory"
            >
              ×
            </button>
          ) : (
            <div className="flex gap-1">
              <button
                onClick={() => setShowConfirm(false)}
                disabled={isDeleting}
                className="px-2 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 text-xs font-bold shadow-[2px_2px_0_0_#000000] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
              >
                No
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="px-2 py-1 border-2 border-brutal-black bg-brutal-black hover:bg-brutal-gray text-white text-xs font-bold shadow-[2px_2px_0_0_#000000] active:translate-x-[1px] active:translate-y-[1px] active:shadow-none transition-all"
              >
                {isDeleting ? '...' : 'Yes'}
              </button>
            </div>
          )}
        </div>

        {/* Content */}
        <div className="mb-3">
          <p className="text-sm text-neutral-800 leading-relaxed break-words">
            {highlightText(displayContent, searchQuery)}
          </p>
          {shouldTruncate && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-2 text-xs font-bold text-brutal-blue hover:underline uppercase"
            >
              {isExpanded ? '▲ Show Less' : '▼ Show More'}
            </button>
          )}
        </div>

        {/* Metadata row */}
        <div className="flex items-center gap-4 text-xs text-neutral-600 flex-wrap mb-2">
          <span className="flex items-center gap-1">
            <span className="font-bold">Date:</span>
            {formatDate(memory.created_at)}
          </span>

          <span className="flex items-center gap-1">
            <span className="font-bold">Imp:</span>
            {memory.importance.toFixed(2)}
          </span>

          <span className="flex items-center gap-1">
            <span className="font-bold">Views:</span>
            {memory.access_count}
          </span>

          {memory.similarity !== undefined && (
            <span className="flex items-center gap-1 text-brutal-black font-bold">
              <span className="font-bold">Match:</span>
              {(memory.similarity * 100).toFixed(0)}%
            </span>
          )}
        </div>

        {/* Tags */}
        {tags.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {tags.map((tag: string, idx: number) => (
              <span
                key={idx}
                className="px-2 py-1 border-2 border-brutal-black bg-white text-brutal-black text-xs font-bold uppercase cursor-default"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
