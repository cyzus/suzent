/**
 * Memory Card Component
 * Displays a single archival memory with metadata and enhanced visual design
 */

import React, { useState } from 'react';
import type { ArchivalMemory } from '../../types/memory';
import { BrutalDeleteButton } from '../BrutalDeleteButton';
import { BrutalDeleteOverlay } from '../BrutalDeleteOverlay';
import { useI18n } from '../../i18n';

interface MemoryCardProps {
  memory: ArchivalMemory;
  onDelete: (memoryId: string) => Promise<void>;
  searchQuery?: string;
  compact?: boolean;
}

export const MemoryCard: React.FC<MemoryCardProps> = ({ memory, onDelete, searchQuery, compact = false }) => {
  const { t } = useI18n();
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

      if (diffDays === 0) return t('memoryCard.today');
      if (diffDays === 1) return t('memoryCard.yesterday');
      if (diffDays < 7) return t('memoryCard.daysAgo', { count: String(diffDays) });

      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const getImportanceLabel = (importance: number) => {
    if (importance >= 0.8) return t('memoryCard.importance.highShort');
    if (importance >= 0.5) return t('memoryCard.importance.medShort');
    return t('memoryCard.importance.lowShort');
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

  if (compact) {
    return (
      <div className="border-2 border-brutal-black bg-white shadow-brutal-sm hover:bg-neutral-50 transition-all group relative">
        {/* Inline delete confirmation overlay */}
        {showConfirm && (
          <BrutalDeleteOverlay
            onConfirm={handleDelete}
            onCancel={() => setShowConfirm(false)}
            isDeleting={isDeleting}
            title={t('memoryCard.delete.confirmTitleCompact')}
            confirmText={t('memoryCard.delete.confirmYes')}
            layout="vertical"
          />
        )}

        <div className="p-2 flex items-center gap-3">
          {/* Importance Indicator */}
          <div className={`w-1.5 h-8 flex-shrink-0 ${memory.importance >= 0.8 ? 'bg-brutal-black' :
            memory.importance >= 0.5 ? 'bg-neutral-400' : 'bg-neutral-200'
            }`} title={t('memoryCard.importance.tooltip', { value: memory.importance.toFixed(2) })}></div>

          {/* Content Preview */}
          <div className="flex-1 min-w-0">
            <p className="text-sm text-neutral-800 truncate font-mono">
              {highlightText(memory.content, searchQuery)}
            </p>
            <div className="flex items-center gap-2 text-[10px] text-neutral-500 mt-0.5">
              <span className="font-bold uppercase">{formatDate(memory.created_at)}</span>
              {category && <span>• {category}</span>}
              {tags.length > 0 && <span>• #{tags[0]}</span>}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <BrutalDeleteButton
              onClick={() => setShowConfirm(true)}
              className="w-6 h-6 border opacity-0 group-hover:opacity-100 transition-opacity"
              title={t('memoryCard.delete.button')}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="border-3 border-brutal-black bg-white shadow-[2px_2px_0_0_#000] brutal-btn transition-all relative group">
      {/* Delete confirmation overlay */}
      {showConfirm && (
        <BrutalDeleteOverlay
          onConfirm={handleDelete}
          onCancel={() => setShowConfirm(false)}
          isDeleting={isDeleting}
          title={t('memoryCard.delete.confirmTitle')}
          confirmText={t('memoryCard.delete.confirmDelete')}
          cancelText={t('memoryCard.delete.cancel')}
          layout="vertical"
        />
      )}

      <div className="p-4">
        {/* Header with badges */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex gap-2 flex-wrap items-center">
            {/* Importance text indicator */}
            <span className="text-xs font-bold uppercase text-brutal-black bg-neutral-100 px-2 py-0.5 border border-brutal-black">
              {getImportanceLabel(memory.importance)} {memory.importance.toFixed(2)}
            </span>

            {/* Category badge */}
            {category && (
              <span className="px-2 py-0.5 border border-brutal-black bg-white text-brutal-black text-xs font-bold uppercase">
                {category}
              </span>
            )}

            {/* Recent indicator */}
            {isRecent() && (
              <span className="text-xs font-bold uppercase text-brutal-black border border-brutal-black px-1 bg-yellow-200">
                {t('memoryCard.badges.new')}
              </span>
            )}

            {/* Frequently accessed indicator */}
            {isFrequentlyAccessed && (
              <span className="text-xs font-bold uppercase text-white bg-brutal-black px-1">
                {t('memoryCard.badges.hot')}
              </span>
            )}
          </div>

          {/* Delete button - only visible on hover */}
          <BrutalDeleteButton
            onClick={() => setShowConfirm(true)}
            className="flex-shrink-0 w-7 h-7 opacity-0 group-hover:opacity-100 transition-opacity"
            title={t('memoryCard.delete.buttonTitle')}
          />
        </div>

        {/* Content */}
        <div className="mb-3">
          <p className="text-sm text-neutral-800 leading-relaxed break-words font-mono">
            {highlightText(displayContent, searchQuery)}
          </p>
          {shouldTruncate && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-2 text-xs font-bold text-brutal-black hover:underline uppercase border-b-2 border-transparent hover:border-brutal-black inline-block"
            >
              {isExpanded ? `▲ ${t('memoryCard.showLess')}` : `▼ ${t('memoryCard.showMore')}`}
            </button>
          )}
        </div>

        {/* Metadata row */}
        <div className="flex items-center gap-4 text-xs text-neutral-600 flex-wrap mb-2 border-t-2 border-neutral-100 pt-2">
          <span className="flex items-center gap-1">
            <span className="font-bold">{t('memoryCard.meta.created')}</span>
            {formatDate(memory.created_at)}
          </span>

          <span className="flex items-center gap-1">
            <span className="font-bold">{t('memoryCard.meta.views')}</span>
            {memory.access_count}
          </span>

          {memory.similarity !== undefined && (
            <span className="flex items-center gap-1 text-brutal-black font-bold bg-yellow-100 px-1">
              <span className="font-bold">{t('memoryCard.meta.match')}</span>
              {(memory.similarity * 100).toFixed(0)}%
            </span>
          )}
        </div>

        {/* Tags */}
        {tags.length > 0 && (
          <div className="flex gap-2 flex-wrap mt-2">
            {tags.map((tag: string, idx: number) => (
              <span
                key={idx}
                className="px-2 py-0.5 border border-brutal-black bg-neutral-50 text-brutal-black text-[10px] font-bold uppercase cursor-default"
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
