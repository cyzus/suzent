/**
 * Core Memory Block Editor Component
 * Displays and allows editing of individual core memory blocks
 */

import React, { useState, useEffect } from 'react';
import type { CoreMemoryLabel } from '../../types/memory';

interface CoreMemoryBlockProps {
  label: CoreMemoryLabel;
  content: string;
  onUpdate: (label: CoreMemoryLabel, content: string) => Promise<void>;
  maxLength?: number;
}

// Default labels with descriptions (can be extended dynamically)
const DEFAULT_LABEL_INFO: Record<string, { title: string; description: string }> = {
  persona: {
    title: 'Persona',
    description: 'Your identity, role, and capabilities',
  },
  user: {
    title: 'User',
    description: 'Information about the current user',
  },
  facts: {
    title: 'Facts',
    description: 'Key facts to always remember',
  },
  context: {
    title: 'Context',
    description: 'Current session context and goals',
  },
};

// Helper to get label info with fallback for unknown labels
const getLabelInfo = (label: string): { title: string; description: string } => {
  if (DEFAULT_LABEL_INFO[label]) {
    return DEFAULT_LABEL_INFO[label];
  }
  // Fallback for unknown labels - capitalize first letter
  const title = label.charAt(0).toUpperCase() + label.slice(1);
  return {
    title,
    description: `Custom memory block: ${title}`,
  };
};

export const CoreMemoryBlock: React.FC<CoreMemoryBlockProps> = ({
  label,
  content,
  onUpdate,
  maxLength = 2048,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(content);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setEditContent(content);
    setHasUnsavedChanges(false);
  }, [content]);

  useEffect(() => {
    setHasUnsavedChanges(editContent !== content);
  }, [editContent, content]);

  const handleSave = async () => {
    if (editContent === content) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      await onUpdate(label, editContent);
      setIsEditing(false);
      setHasUnsavedChanges(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setEditContent(content);
    setIsEditing(false);
    setError(null);
    setHasUnsavedChanges(false);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const { title, description } = getLabelInfo(label);
  const characterCount = editContent.length;
  const isOverLimit = characterCount > maxLength;
  const usagePercent = (characterCount / maxLength) * 100;

  const getProgressColor = () => {
    if (usagePercent >= 90) return 'bg-brutal-black';
    if (usagePercent >= 70) return 'bg-brutal-gray';
    return 'bg-brutal-black';
  };

  return (
    <div className={`border-3 border-brutal-black bg-white shadow-brutal rounded-none p-4 transition-all ${hasUnsavedChanges && isEditing ? 'ring-4 ring-brutal-black' : ''
      } hover:translate-x-[-1px] hover:translate-y-[-1px] hover:shadow-brutal-lg`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-brutal text-lg uppercase tracking-tight text-brutal-black">
              {title}
            </h3>
            {hasUnsavedChanges && isEditing && (
              <span className="px-2 py-0.5 border-2 border-brutal-black bg-brutal-black text-white text-xs font-bold uppercase animate-brutal-blink">
                Unsaved
              </span>
            )}
          </div>
          <p className="text-sm text-neutral-600 mt-1">{description}</p>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          {!isEditing ? (
            <>
              <button
                onClick={handleCopy}
                className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none shadow-[2px_2px_0_0_#000000] font-bold text-xs uppercase transition-all"
              >
                {copied ? '✓ Copied' : 'Copy'}
              </button>
              <button
                onClick={() => setIsEditing(true)}
                className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none shadow-[2px_2px_0_0_#000000] font-bold text-xs uppercase transition-all"
              >
                Edit
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleCancel}
                disabled={isSaving}
                className="px-3 py-1 border-2 border-brutal-black bg-white hover:bg-neutral-100 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none shadow-[2px_2px_0_0_#000000] font-bold text-xs uppercase transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving || isOverLimit || !hasUnsavedChanges}
                className="px-3 py-1 border-2 border-brutal-black bg-brutal-black text-brutal-white hover:bg-neutral-800 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none shadow-[2px_2px_0_0_#000000] font-bold text-xs uppercase transition-all disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-3 p-3 border-3 border-brutal-black bg-white text-brutal-black text-sm flex items-start gap-2">
          <span className="text-lg">⚠️</span>
          <div>
            <p className="font-bold text-brutal-black">Save Failed</p>
            <p className="text-xs mt-1">{error}</p>
          </div>
        </div>
      )}

      {isEditing ? (
        <div>
          <textarea
            value={editContent}
            onChange={(e) => {
              setEditContent(e.target.value);
              // Auto-resize
              e.target.style.height = 'auto';
              e.target.style.height = e.target.scrollHeight + 'px';
            }}
            className={`w-full min-h-[150px] p-3 border-3 rounded-none font-mono text-sm resize-y focus:outline-none focus:ring-4 transition-all scrollbar-thin ${isOverLimit
              ? 'border-brutal-black focus:ring-brutal-black'
              : 'border-brutal-black focus:ring-brutal-black'
              }`}
            style={{ backgroundColor: '#ffffff', color: '#000000' }}
            placeholder={`Enter ${title.toLowerCase()}...`}
            autoFocus
            onFocus={(e) => {
              e.target.style.height = 'auto';
              e.target.style.height = e.target.scrollHeight + 'px';
            }}
          />

          {/* Character count with progress bar */}
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className={isOverLimit ? 'text-brutal-black font-bold' : 'text-neutral-500'}>
                {characterCount} / {maxLength} characters
                {isOverLimit && ' ⚠️ Over limit!'}
              </span>
              <span className="text-neutral-500">{usagePercent.toFixed(0)}% used</span>
            </div>
            <div className="h-1.5 bg-white border-3 border-brutal-black">
              <div
                className={`h-full transition-all duration-300 ${getProgressColor()}`}
                style={{ width: `${Math.min(usagePercent, 100)}%` }}
              />
            </div>
          </div>
        </div>
      ) : (
        <div className="prose prose-sm max-w-none">
          <pre
            className="whitespace-pre-wrap font-mono text-sm p-3 border-3 border-brutal-black rounded-none break-words max-h-[400px] overflow-y-auto scrollbar-thin"
            style={{ backgroundColor: '#f9fafb', color: '#000000' }}
          >
            {content || (
              <span className="text-neutral-400 italic flex items-center gap-2">
                <span>📝</span>
                No content yet - click Edit to add
              </span>
            )}
          </pre>
          {content && (
            <div className="text-xs text-neutral-500 mt-2 flex items-center gap-3">
              <span>{characterCount} characters</span>
              <span>•</span>
              <span>{Math.ceil(characterCount / 5)} words (approx)</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
